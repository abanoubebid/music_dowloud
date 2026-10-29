#!/usr/bin/env bash
# One-time setup on macOS. After this the app runs in the background, starts at login, and updates itself.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"; APP="$SRC"; D="$HOME/.vdd"; UIDN="$(id -u)"
case "$SRC" in "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
  # macOS blocks background jobs from reading these folders, so the app lives in ~/vdd instead.
  APP="$HOME/vdd"; mkdir -p "$APP"
  rsync -a --exclude .venv --exclude node_modules --exclude dist --exclude __pycache__ "$SRC/" "$APP/"
  echo ">> Project copied to $APP. Edit the code THERE from now on." ;;
esac
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
for t in python3 node ffmpeg; do command -v $t >/dev/null || brew install ${t/python3/python}; done

mkdir -p "$D"
if [ ! -f "$D/env" ]; then
  printf 'VD_ACCESS_KEY=%s\nVD_WORKERS=2\n# TUNNEL_TOKEN=   (optional: Cloudflare named tunnel token)\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')" > "$D/env"
  chmod 600 "$D/env"
fi
set -a; . "$D/env"; set +a

echo ">> Installing Python packages"
cd "$APP/backend"; [ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate && pip install -q -r requirements.txt && pip install -q -U "yt-dlp[default]" && touch "$D/ytdlp.stamp"
chmod +x "$APP"/deploy/*.sh

plist(){ # label, script, interval(optional)
  f="$HOME/Library/LaunchAgents/$1.plist"; mkdir -p "$HOME/Library/LaunchAgents"
  { echo "<?xml version=\"1.0\" encoding=\"UTF-8\"?><!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\"><plist version=\"1.0\"><dict>"
    echo "<key>Label</key><string>$1</string><key>ProgramArguments</key><array><string>/bin/bash</string><string>$APP/deploy/$2</string></array>"
    echo "<key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>"
    echo "<key>RunAtLoad</key><true/><key>StandardOutPath</key><string>$D/$1.log</string><key>StandardErrorPath</key><string>$D/$1.log</string>"
    if [ -n "$3" ]; then echo "<key>StartInterval</key><integer>$3</integer>"; else echo "<key>KeepAlive</key><true/>"; fi
    echo "</dict></plist>"; } > "$f"
  launchctl bootout "gui/$UIDN" "$f" 2>/dev/null || true
  launchctl bootstrap "gui/$UIDN" "$f"
}
plist com.vdd.server run-server.sh
echo ">> Building the web app (first time takes a minute)"; bash "$APP/deploy/update.sh"
plist com.vdd.updater update.sh 60      # then checks for changes every minute
if [ -n "$TUNNEL_TOKEN" ]; then command -v cloudflared >/dev/null || brew install cloudflared; plist com.vdd.tunnel run-tunnel.sh; fi
sleep 3

LINK=""
if [ -n "$TUNNEL_TOKEN" ]; then
  echo ">> Cloudflare tunnel is running. Your link is the hostname you set in the Cloudflare dashboard."
  LINK="https://YOUR-HOSTNAME/?key=$VD_ACCESS_KEY"
else
  TS="$(command -v tailscale || true)"; [ -z "$TS" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  if [ -z "$TS" ]; then
    echo "!! Tailscale not found. Install it (https://tailscale.com/download), sign in, then run this script again."
  else
    "$TS" funnel --bg 8000 || echo "!! If it asked you to enable Funnel, open the link it printed, approve, then run this script again."
    HOST="$("$TS" status --json | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
    [ -n "$HOST" ] && LINK="https://$HOST/?key=$VD_ACCESS_KEY"
  fi
fi
echo; echo "============================================"
echo " Your permanent link:  ${LINK:-<see above>}"
echo "============================================"
[ -n "$LINK" ] && echo "$LINK" > "$D/LINK.txt" && echo "(saved in $D/LINK.txt)"
echo "Logs: $D/update.log  $D/com.vdd.server.log"
