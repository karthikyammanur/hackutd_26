#!/bin/bash
# Publishes the service through a Cloudflare quick tunnel and records its URL. Docker restarts this if it exits.
# Quick-tunnel URLs change when the tunnel restarts; the latest is always in app-tunnel-url.
cd /sf || exit 1
./cloudflared tunnel --no-autoupdate --url http://localhost:8765 > app-tunnel.log 2>&1 &
pid=$!
for _ in $(seq 1 60); do
  url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' app-tunnel.log | grep -v 'api\.' | head -1)
  [ -n "$url" ] && { echo "$url" > app-tunnel-url; break; }
  sleep 1
done
wait $pid
