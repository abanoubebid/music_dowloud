#!/usr/bin/env bash
# Runs every minute (launchd com.vdd.updater). Picks up code changes from `git push` (pull) or from edits in
# this folder, rebuilds what changed, restarts the server, and refreshes yt-dlp once a day.
APP="$(cd "$(dirname "$0")/.." && pwd)"
D="$HOME/.vdd"; LOG="$D/update.log"; mkdir -p "$D"
mkdir "$D/lock" 2>/dev/null || { [ -n "$(find "$D/lock" -mmin +30 2>/dev/null)" ] && rmdir "$D/lock"; exit 0; }
trap 'rmdir "$D/lock"' EXIT
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; }
cd "$APP" || exit 1

if [ -d .git ] && [ -n "$(git remote)" ]; then
  git fetch -q 2>>"$LOG" && git merge --ff-only -q '@{u}' >>"$LOG" 2>&1 || true
fi

fp(){ find "$@" -type f ! -path '*/node_modules/*' ! -path '*/__pycache__/*' ! -path '*/dist/*' ! -path '*/dist.new/*' ! -name .DS_Store -print0 2>/dev/null \
      | sort -z | xargs -0 shasum 2>/dev/null | shasum | cut -d' ' -f1; }
FE="$(fp frontend)"; BE="$(fp backend/app backend/requirements.txt)"
restart=0

if [ "$FE" != "$(cat "$D/state.fe" 2>/dev/null)" ]; then
  log "frontend changed: building"
  if (cd frontend && npm install --silent && npx vite build --outDir dist.new --emptyOutDir) >>"$LOG" 2>&1; then
    rm -rf frontend/dist && mv frontend/dist.new frontend/dist && echo "$FE" > "$D/state.fe" && log "frontend live"
  else log "frontend build FAILED (old version stays online)"; rm -rf frontend/dist.new; fi
fi

if [ "$BE" != "$(cat "$D/state.be" 2>/dev/null)" ]; then
  log "backend changed"
  if (cd backend && . .venv/bin/activate && pip install -q -r requirements.txt) >>"$LOG" 2>&1; then
    echo "$BE" > "$D/state.be"; restart=1
  else log "pip install FAILED"; fi
fi

# YouTube changes often; keep yt-dlp fresh (once a day).
if [ -z "$(find "$D/ytdlp.stamp" -mtime -1 2>/dev/null)" ]; then
  (cd backend && . .venv/bin/activate && pip install -q -U "yt-dlp[default]") >>"$LOG" 2>&1 && touch "$D/ytdlp.stamp" && log "yt-dlp refreshed" && restart=1
fi

# A new frontend build is served immediately; the Python server needs a restart only for backend/yt-dlp changes.
[ "$restart" = 1 ] && launchctl kickstart -k "gui/$(id -u)/com.vdd.server" >>"$LOG" 2>&1 && log "server restarted"
exit 0
