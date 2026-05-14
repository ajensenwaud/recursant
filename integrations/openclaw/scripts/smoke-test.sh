#!/usr/bin/env bash
# End-to-end smoke test:
#   1. Send a message through the OpenClaw agent CLI (gateway path)
#   2. Wait for the plugin's audit queue to flush
#   3. Verify a fresh openclaw.llm_call row landed in the Recursant registry
#
# Assumes the gateway is already running with the recursant plugin loaded.
set -euo pipefail

REGISTRY_URL="${REGISTRY_URL:-http://localhost:8050}"
OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw}"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
ENV_FILE="${ENV_FILE:-$HOME/.env}"
MESSAGE="${MESSAGE:-Quick check: what is 6 plus 7? Reply with just the number.}"
TO_NUMBER="${TO_NUMBER:-+15555550123}"
TENANT_ID="${TENANT_ID:-default}"
WAIT_FLUSH_SECONDS="${WAIT_FLUSH_SECONDS:-15}"

# Line-buffered output so piping to tee/log file streams in real time.
exec 1> >(stdbuf -oL cat) 2>&1

log() { printf '\033[1;36m[smoke-test]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[smoke-test FAIL]\033[0m %s\n' "$*"; exit 1; }
pass() { printf '\033[1;32m[smoke-test PASS]\033[0m %s\n' "$*"; }

[[ -f "$ENV_FILE" ]] || fail "env file not found: $ENV_FILE"
set -a; source "$ENV_FILE"; set +a

if [[ -z "${ADMIN_USERNAME:-}" || -z "${ADMIN_PASSWORD:-}" ]]; then
  if command -v kubectl >/dev/null; then
    POD="$(kubectl get pod -n recursant -l app=recursant-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    if [[ -n "$POD" ]]; then
      ADMIN_USERNAME="${ADMIN_USERNAME:-$(kubectl exec -n recursant "$POD" -c registry -- printenv ADMIN_USERNAME 2>/dev/null || true)}"
      ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(kubectl exec -n recursant "$POD" -c registry -- printenv ADMIN_PASSWORD 2>/dev/null || true)}"
    fi
  fi
fi
: "${ADMIN_USERNAME:?ADMIN_USERNAME not in $ENV_FILE and could not pull from registry pod}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD not in $ENV_FILE and could not pull from registry pod}"

# Gateway must be running
if ! ss -tln 2>/dev/null | grep -q '127.0.0.1:18789 '; then
  fail "gateway is not listening on 127.0.0.1:18789 — run start-gateway.sh first"
fi

# ---------------------------------------------------------------------------
# 1. Capture baseline audit count
# ---------------------------------------------------------------------------
log "logging in as admin"
ADMIN_JWT="$(
  curl -sS --fail \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$REGISTRY_URL/v1/auth/login" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
)"

before_count() {
  curl -sS --fail \
    -H "Authorization: Bearer $ADMIN_JWT" \
    -H "X-Tenant-ID: $TENANT_ID" \
    "$REGISTRY_URL/v1/audit-logs?action=openclaw.llm_call&per_page=100" \
    | python3 -c 'import sys,json; print(len(json.load(sys.stdin).get("logs", [])))'
}

BEFORE="$(before_count)"
log "baseline openclaw.llm_call rows for tenant=$TENANT_ID: $BEFORE"

# ---------------------------------------------------------------------------
# 2. Send a message via the agent CLI
# ---------------------------------------------------------------------------
GATEWAY_TOKEN="$(python3 -c "
import json, sys
with open('$OPENCLAW_HOME/openclaw.json') as f:
    cfg = json.load(f)
print(cfg.get('gateway', {}).get('auth', {}).get('token', ''))
")"
[[ -n "$GATEWAY_TOKEN" ]] || fail "no gateway.auth.token in $OPENCLAW_HOME/openclaw.json"

log "sending message via agent CLI: $MESSAGE"
AGENT_OUT="$(mktemp)"
trap 'rm -f "$AGENT_OUT"' EXIT
(
  cd "$OPENCLAW_DIR"
  OPENCLAW_GATEWAY_TOKEN="$GATEWAY_TOKEN" \
    timeout 90 node openclaw.mjs agent --message "$MESSAGE" --to "$TO_NUMBER"
) >"$AGENT_OUT" 2>&1 || log "agent CLI exited non-zero (may still have produced output)"
log "agent reply (last 3 lines):"
tail -3 "$AGENT_OUT" | sed 's/^/    /'

# ---------------------------------------------------------------------------
# 3. Wait for plugin audit queue to flush, then re-check count
# ---------------------------------------------------------------------------
log "waiting ${WAIT_FLUSH_SECONDS}s for plugin audit flush"
sleep "$WAIT_FLUSH_SECONDS"

AFTER="$(before_count)"
log "post-message openclaw.llm_call rows: $AFTER"

if [[ "$AFTER" -le "$BEFORE" ]]; then
  fail "no new openclaw.llm_call audit row landed (before=$BEFORE after=$AFTER)"
fi

DELTA=$((AFTER - BEFORE))
pass "$DELTA new openclaw.llm_call audit row(s) landed"
