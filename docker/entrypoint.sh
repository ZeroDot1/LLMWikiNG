#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${PORT:-8080}"
APP_HOST="${HOST:-0.0.0.0}"
TS_STATE_DIR="${TS_STATE_DIR:-/var/lib/tailscale}"
TS_SERVE_CONFIG="${TS_SERVE_CONFIG:-/config/tailscale/serve.json}"
TS_AUTHKEY="${TS_AUTHKEY:-}"
TS_HOSTNAME="${TS_HOSTNAME:-}"

mkdir -p "$TS_STATE_DIR" "$(dirname "$TS_SERVE_CONFIG")"

# Start tailscaled daemon in background
if [ -c /dev/net/tun ]; then
  tailscaled --state="$TS_STATE_DIR/tailscaled.state" \
             --statedir="$TS_STATE_DIR" &
else
  # Userspace fallback if TUN device is unavailable
  tailscaled --tun=userspace-networking \
             --state="$TS_STATE_DIR/tailscaled.state" \
             --statedir="$TS_STATE_DIR" &
fi

sleep 2

# Initial Tailscale authentication if TS_AUTHKEY environment variable is provided
if [ -n "$TS_AUTHKEY" ]; then
  TS_UP_CMD=(tailscale up --authkey="$TS_AUTHKEY" --accept-dns=true)
  if [ -n "$TS_HOSTNAME" ]; then
    TS_UP_CMD+=(--hostname="$TS_HOSTNAME")
  fi
  if [ -n "${TS_EXTRA_ARGS:-}" ]; then
    TS_UP_CMD+=(${TS_EXTRA_ARGS:-})
  fi
  "${TS_UP_CMD[@]}" || true
fi

# Execute application if passed as arguments, or default entry point
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec python run.py --port "$APP_PORT" --host "$APP_HOST"
fi
