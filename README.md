# SM Simple Sub

Minimal Stremio/Nuvio subtitle addon — Malayalam subtitles from
**Team GOAT** + **Movie Mirror**. Built after the Oct 2026 TV investigation.

## Why this exists

The merged addon's subtitle endpoints did not show up on the Hisense
Google TV (Nuvio), while the official Msone addon did. Learnings applied:

- Manifest at **root** `/manifest.json` (not a subpath like `/sub/...`).
- **One** subtitle entry per source, `"lang": "mal"` (like official Msone).
- `/subtitles` answers from an **in-memory index** — no slow external
  calls in the request path.
- SRT files proxied with a **browser User-Agent** (Movie Mirror blocks
  non-browser agents) and cached on disk.
- CORS `*` on every response.

## Install (phone/TV)

Add this URL in Stremio/Nuvio → Addons:

```
https://<your-render-service>/manifest.json
```

## Deploy on Render

1. Push this folder to a GitHub repo (e.g. `4mytv-max/SM-SIMPLE-SUB`).
2. Render dashboard → **New +** → **Web Service** → connect the repo.
3. Settings:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Plan: Free
4. Wait for deploy, then use `https://<service>.onrender.com/manifest.json`.

## Refresh subtitle data

`data/goat_data.json` and `data/mm_data.json` are snapshots. To refresh,
copy the latest files from the main pipeline (`~/workspace/sm_merged/data/`
or the `mal-sub-by-sm` repo's `data/`), commit, and push — Render redeploys
automatically.

## Endpoints

| URL | Purpose |
|---|---|
| `/manifest.json` | Addon manifest (root) |
| `/subtitles/<movie\|series>/<ttID>.json` | Subtitle list for a title |
| `/srt/<key>.srt` | Subtitle file (downloaded once, then cached) |
