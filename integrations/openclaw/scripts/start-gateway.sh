#!/usr/bin/env bash
# Stop any running gateway then start a fresh one with API keys sourced from
# $ENV_FILE so the openrouter:default keyRef resolves.
set -euo pipefail

OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw}"
ENV_FILE="${ENV_FILE:-$HOME/.env}"
LOG_FILE="${LOG_FILE:-/tmp/openclaw-gateway.log}"

log() { printf '\033[1;36m[start-gateway]\033[0m %s\n' "$*" >&2; }

[[ -f "$ENV_FILE" ]] || { echo "env file not found: $ENV_FILE"; exit 1; }
[[ -d "$OPENCLAW_DIR" ]] || { echo "openclaw dir not found: $OPENCLAW_DIR"; exit 1; }

cd "$OPENCLAW_DIR"

# Stop any running gateway (best-effort)
log "stopping any running gateway"
node openclaw.mjs gateway stop >/dev/null 2>&1 || true

# Wait for loopback port to be free
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! ss -tln 2>/dev/null | grep -q '127.0.0.1:18789 '; then break; fi
  sleep 1
done

log "starting gateway (logs → $LOG_FILE)"
set -a; source "$ENV_FILE"; set +a
nohup node openclaw.mjs gateway --force >"$LOG_FILE" 2>&1 &
GW_PID=$!

# Wait until loopback bind appears
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if ss -tln 2>/dev/null | grep -q '127.0.0.1:18789 '; then break; fi
  sleep 1
done

if ! ss -tln 2>/dev/null | grep -q '127.0.0.1:18789 '; then
  echo "gateway failed to listen on 127.0.0.1:18789 — see $LOG_FILE"
  tail -30 "$LOG_FILE" || true
  exit 1
fi

log "gateway listening (pid=$GW_PID)"
sleep 4
grep -E 'recursant' "$LOG_FILE" | tail -3 || true
