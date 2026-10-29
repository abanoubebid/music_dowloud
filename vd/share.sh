#!/usr/bin/env bash
# Starts the app on this Mac and gives you a public link (Cloudflare quick tunnel). Stop with Ctrl+C.
set -e
cd "$(dirname "$0")"
command -v cloudflared >/dev/null || { echo "Install it first: brew install cloudflared"; exit 1; }
KEY="${VD_ACCESS_KEY:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')}"
(cd frontend && npm install --silent && npx vite build)
cd backend && source .venv/bin/activate
export VD_ACCESS_KEY="$KEY" VD_WORKERS="${VD_WORKERS:-2}"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
trap 'kill $! 2>/dev/null' EXIT
sleep 2
echo
echo "=== Access key: $KEY"
echo "=== Share link = (the https://...trycloudflare.com address printed below) + /?key=$KEY"
echo
caffeinate -i cloudflared tunnel --url http://127.0.0.1:8000
