#!/usr/bin/env python3
"""SM Simple Sub — minimal Stremio subtitle addon (Team GOAT + Movie Mirror).

Design notes (from TV investigation, Oct 2026):
- Manifest served at ROOT (/manifest.json), not a subpath — TV clients
  handle root manifests more reliably.
- Subtitle entries use descriptive lang labels "Malayalam (Team GOAT)" /
  "Malayalam (Movie Mirror)" (same style as the TV-working third-party
  addon). Key order id/url/lang matches it too.
- JSON responses carry "Content-Type: application/json; charset=utf-8"
  (like the TV-working addon), not bare "application/json".
- /subtitles answers from a prebuilt in-memory index — no external HTTP
  calls in the hot path, so responses are fast (<100ms warm).
- SRT files are proxied through /srt/<key>.srt with a browser User-Agent
  (Movie Mirror blocks non-browser agents), normalized to CRLF line
  endings (strict TV SRT parsers expect CRLF), and cached to disk.
- CORS: Access-Control-Allow-Origin: * on every response.
"""
import json
import os
import re
import urllib.request

from flask import Flask, Response, request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
CACHE_DIR = os.path.join(APP_DIR, "srt_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Movie Mirror's host rejects non-browser User-Agents with empty replies.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# imdb_id -> list of entries ; key -> entry (for /srt lookup)
BY_IMDB = {}
BY_KEY = {}


def _load_data():
    for src, fname in (("goat", "goat_data.json"), ("mm", "mm_data.json")):
        path = os.path.join(DATA_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f"[init] failed to load {fname}: {exc}", flush=True)
            continue
        items = data.get("items", []) if isinstance(data, dict) else data
        count = 0
        for it in items:
            imdb = (it.get("imdb_id") or "").strip()
            url = (it.get("sub_url") or "").strip()
            if not imdb or not url:
                continue
            key = f"{src}_{imdb}"
            entry = {
                "src": src,
                "key": key,
                "name": it.get("name_en") or it.get("name_ml") or "",
                "url": url,
            }
            BY_IMDB.setdefault(imdb, []).append(entry)
            BY_KEY[key] = entry
            count += 1
        print(f"[init] {src}: {count} entries", flush=True)
    print(f"[init] total imdb ids: {len(BY_IMDB)}", flush=True)


_load_data()

app = Flask(__name__)

IMDB_RE = re.compile(r"^(tt\d+)")


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _json(data, status=200):
    """JSON response with explicit charset (matches TV-working addon)."""
    resp = Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json; charset=utf-8",
    )
    return _cors(resp)


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        resp = Response("")
        return _cors(resp)


@app.route("/manifest.json")
def manifest():
    return _json({
        "id": "community.sm.goatmm.subtitles",
        "version": "1.0.4",
        "name": "SM SUB FRESH",
        "description": "Malayalam subtitles: Team GOAT + Movie Mirror.",
        "resources": ["subtitles"],
        "types": ["movie", "series"],
        "catalogs": [],
        "idPrefixes": ["tt"],
        "behaviorHints": {"configurable": False},
    })


@app.route("/subtitles/<vtype>/<rid>.json")
def subtitles(vtype, rid):
    # rid may be "tt1234567" or "tt1234567:1:2" (series) — take the imdb part.
    m = IMDB_RE.match(rid or "")
    imdb = m.group(1) if m else ""
    base = request.url_root.rstrip("/")
    out = []
    for e in BY_IMDB.get(imdb, []):
        # Match third-party ID/label format exactly: goat-tt123 /
        # "Malayalam (Team GOAT)", moviemirror-tt123 / "Malayalam (Movie Mirror)"
        prefix = "goat" if e['src'] == "goat" else "moviemirror"
        label = ("Malayalam (Team GOAT)" if e['src'] == "goat"
                 else "Malayalam (Movie Mirror)")
        out.append({
            "id": f"{prefix}-{imdb}",
            "url": f"{base}/srt/{e['key']}.srt",
            "lang": label,
        })
    return _json({"subtitles": out})


def _download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def _to_crlf(data: bytes) -> bytes:
    """Normalize subtitle line endings to CRLF.

    Strict SRT parsers (some TV players) expect CRLF; sources sometimes
    serve lone LF. Normalize lone LF -> CRLF without doubling existing CRLF.
    """
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


@app.route("/srt/<key>.srt")
def serve_srt(key):
    entry = BY_KEY.get(key)
    if not entry:
        return _json({"error": "not found"}, status=404)
    cache_path = os.path.join(CACHE_DIR, key + ".srt")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
    else:
        try:
            data = _download(entry["url"])
        except Exception as exc:  # noqa: BLE001
            print(f"[srt] download failed {key}: {exc}", flush=True)
            return _json({"error": "download failed"}, status=502)
        head = data[:200]
        if b"-->" not in head and b"WEBVTT" not in head:
            print(f"[srt] bad content {key}: {head[:60]!r}", flush=True)
            return _json({"error": "bad subtitle file"}, status=502)
        data = _to_crlf(data)
        try:
            with open(cache_path, "wb") as f:
                f.write(data)
        except OSError:
            pass
    return _cors(Response(data, content_type="application/x-subrip;charset=utf-8"))


@app.route("/")
def index():
    base = request.host_url.rstrip("/")
    return Response(
        "<h2>SM Simple Sub</h2>"
        f"<p>Install in Stremio/Nuvio:<br><code>{base}/manifest.json</code></p>",
        mimetype="text/html",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
