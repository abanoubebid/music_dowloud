#!/usr/bin/env bash
for l in com.vdd.server com.vdd.updater com.vdd.tunnel; do
  f="$HOME/Library/LaunchAgents/$l.plist"; [ -f "$f" ] && launchctl bootout "gui/$(id -u)" "$f" 2>/dev/null; rm -f "$f"
done
(command -v tailscale >/dev/null && tailscale funnel reset) 2>/dev/null
echo "Stopped and removed. Settings/key remain in ~/.vdd"
