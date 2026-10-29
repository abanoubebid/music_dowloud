#!/usr/bin/env bash
# Started by launchd (com.vdd.tunnel) when TUNNEL_TOKEN is set in ~/.vdd/env (Cloudflare named tunnel).
set -a; . "$HOME/.vdd/env"; set +a
exec cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"
