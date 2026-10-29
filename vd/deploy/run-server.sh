#!/usr/bin/env bash
# Started by launchd (com.vdd.server). Keeps the Mac awake while the server runs.
set -e
APP="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$HOME/.vdd/env"; set +a
cd "$APP/backend" && . .venv/bin/activate
exec caffeinate -i uvicorn app.main:app --host 127.0.0.1 --port 8000
