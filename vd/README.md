# Video Downloader (YouTube)
Stack: React + Vite + TypeScript (frontend), FastAPI + yt-dlp (backend). Requires FFmpeg on PATH and a JS runtime (Deno or Node) for yt-dlp's YouTube support.

## Run
    cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    uvicorn app.main:app --reload          # API docs at /docs
    cd frontend && npm install && npm run dev
## Test
    cd backend && pytest        # frontend: npm run build (tsc + vite)
## Add a platform
Subclass `platforms/base.py:Adapter`, register it in `platforms/registry.py`. Nothing else changes.
## Config: see backend/.env.example (exported as env vars). Downloads stream directly to the browser (yt-dlp → FFmpeg → HTTP), so the browser shows native progress and asks where to save. Not production-hardened (no auth/rate limits).

## Fast start + loading popup
`/api/analyze` keeps yt-dlp's result on disk (temp dir `vd-info`), and the download reuses it (`--load-info-json`) instead of extracting the video a second time; if that fails it falls back to the plain URL.
`/api/stream/{token}?dl=<id>` sets a short-lived `vd_<id>` cookie when the response starts; the frontend watches it to close the "Preparing your download…" popup.

## Always-on link (macOS)
    cd vd && ./deploy/install.sh
Installs three background jobs (launchd): the server (starts at login, restarts if it crashes), an updater, and optionally a tunnel.
- **Permanent link**: Tailscale Funnel (free, stable `https://<mac>.<tailnet>.ts.net`), or a Cloudflare named tunnel if you put `TUNNEL_TOKEN=...` in `~/.vdd/env` before installing. The access key lives in `~/.vdd/env`, so the link never changes.
- **Auto-update**: every minute the updater runs `git pull` (if the folder is a git repo with a remote) and compares a fingerprint of the code. Frontend changed -> rebuilds (old version stays online if the build fails). Backend changed -> `pip install` + restart. yt-dlp is upgraded daily.
- Logs: `~/.vdd/update.log`, `~/.vdd/com.vdd.server.log`. Remove everything: `./deploy/uninstall.sh`.
- The Mac must be on and awake (plugged in, lid open or external display). YouTube blocks cloud-server IPs, so the app runs from a home connection.
- `share.sh` is the old manual one-off tunnel.
