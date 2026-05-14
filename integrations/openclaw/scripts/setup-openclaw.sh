#!/usr/bin/env bash
# Provision an OpenClaw instance with the openclaw-recursant plugin linked,
# enrolled with a fresh token, and configured for openrouter/auto.
#
# Assumes:
#   - Recursant registry is reachable at $REGISTRY_URL (default
#     http://localhost:8050) and admin credentials are in $ENV_FILE.
#   - OpenClaw source checkout lives at $OPENCLAW_DIR (default ~/openclaw)
#     and has been built (`pnpm install && pnpm build`) at least once.
#   - $ENV_FILE (default ~/.env) contains OPENROUTER_API_KEY,
#     ADMIN_USERNAME, ADMIN_PASSWORD.
#
# This script is idempotent: rerunning re-issues a token and rewrites the
# plugin config; previously cached credentials at
# ~/.recursant/openclaw-credentials.json are wiped so the plugin re-enrolls
# cleanly on next gateway start.
set -euo pipefail

REGISTRY_URL="${REGISTRY_URL:-http://localhost:8050}"
TENANT_ID="${TENANT_ID:-default}"
OPENCLAW_DIR="${OPENCLAW_DIR:-$HOME/openclaw}"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
ENV_FILE="${ENV_FILE:-$HOME/.env}"
PLUGIN_DIR="${PLUGIN_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CRED_PATH="${HOME}/.recursant/openclaw-credentials.json"

log() { printf '\033[1;36m[openclaw-setup]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[openclaw-setup error]\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"

# Source env file privately so OPENROUTER_API_KEY etc. are available
set -a; source "$ENV_FILE"; set +a

# Admin credentials may live in the env file OR in the K8s registry pod's
# environment (Helm-injected from --set). Fall back to kubectl when missing.
if [[ -z "${ADMIN_USERNAME:-}" || -z "${ADMIN_PASSWORD:-}" ]]; then
  if command -v kubectl >/dev/null; then
    log "ADMIN_USERNAME/PASSWORD missing from $ENV_FILE, pulling from registry pod"
    POD="$(kubectl get pod -n recursant -l app=recursant-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    if [[ -n "$POD" ]]; then
      ADMIN_USERNAME="${ADMIN_USERNAME:-$(kubectl exec -n recursant "$POD" -c registry -- printenv ADMIN_USERNAME 2>/dev/null || true)}"
      ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(kubectl exec -n recursant "$POD" -c registry -- printenv ADMIN_PASSWORD 2>/dev/null || true)}"
    fi
  fi
fi

: "${ADMIN_USERNAME:?ADMIN_USERNAME not in $ENV_FILE and could not pull from registry pod}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD not in $ENV_FILE and could not pull from registry pod}"
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY not set in $ENV_FILE}"

command -v node >/dev/null || die "node not found in PATH"
[[ -d "$OPENCLAW_DIR" ]] || die "OpenClaw checkout not found: $OPENCLAW_DIR"
[[ -d "$PLUGIN_DIR" ]] || die "plugin dir not found: $PLUGIN_DIR"

# ---------------------------------------------------------------------------
# 1. Admin login
# ---------------------------------------------------------------------------
log "logging in as admin against $REGISTRY_URL"
ADMIN_JWT="$(
  curl -sS --fail \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$REGISTRY_URL/v1/auth/login" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
)"

# ---------------------------------------------------------------------------
# 2. Issue enrollment token
# ---------------------------------------------------------------------------
log "issuing enrollment token (tenant=$TENANT_ID)"
ENROLL_TOKEN="$(
  curl -sS --fail \
    -H "Authorization: Bearer $ADMIN_JWT" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H 'Content-Type: application/json' \
    -d '{"ttl_seconds":3600}' \
    "$REGISTRY_URL/v1/openclaw/enrollment-tokens" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
)"

# ---------------------------------------------------------------------------
# 3. Link the plugin into OpenClaw
# ---------------------------------------------------------------------------
log "linking plugin at $PLUGIN_DIR into $OPENCLAW_DIR"
(
  cd "$OPENCLAW_DIR"
  node openclaw.mjs plugins install --link "$PLUGIN_DIR" >/dev/null 2>&1 || true
)

# ---------------------------------------------------------------------------
# 4. Patch ~/.openclaw/openclaw.json
# ---------------------------------------------------------------------------
log "patching $OPENCLAW_HOME/openclaw.json"
CFG="$OPENCLAW_HOME/openclaw.json"
[[ -f "$CFG" ]] || die "openclaw config not found at $CFG"
cp "$CFG" "$CFG.bak.$(date +%s)"

python3 - "$CFG" "$REGISTRY_URL" "$TENANT_ID" "$ENROLL_TOKEN" <<'PY'
import json, sys
cfg_path, registry_url, tenant_id, enroll_token = sys.argv[1:5]
with open(cfg_path) as f:
    cfg = json.load(f)

plugins = cfg.setdefault('plugins', {})
allow = plugins.setdefault('allow', [])
for name in ('recursant', 'openrouter'):
    if name not in allow:
        allow.append(name)
entries = plugins.setdefault('entries', {})
entries['recursant'] = {
    'enabled': True,
    'config': {
        'registryUrl': registry_url,
        'enrollmentToken': enroll_token,
        'tenantId': tenant_id,
        'heartbeatIntervalMs': 30000,
        'auditBatchSize': 50,
    },
}

agents_defaults = cfg.setdefault('agents', {}).setdefault('defaults', {})
agents_defaults.setdefault('model', {})['primary'] = 'openrouter/auto'
agents_defaults.setdefault('models', {})['openrouter/auto'] = {'alias': 'AUTO'}

secrets = cfg.setdefault('secrets', {})
secrets.setdefault('providers', {})['default'] = {'source': 'env'}

with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print('updated config')
PY

# ---------------------------------------------------------------------------
# 5. Add openrouter:default auth profile using a keyRef (no key inlined)
# ---------------------------------------------------------------------------
AUTH_PATH="$OPENCLAW_HOME/agents/main/agent/auth-profiles.json"
[[ -f "$AUTH_PATH" ]] || die "auth-profiles.json not found at $AUTH_PATH (run openclaw onboard first)"
log "adding openrouter:default profile (keyRef → env OPENROUTER_API_KEY)"
cp "$AUTH_PATH" "$AUTH_PATH.bak.$(date +%s)"

python3 - "$AUTH_PATH" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    ap = json.load(f)
ap.setdefault('version', 1)
profiles = ap.setdefault('profiles', {})
profiles['openrouter:default'] = {
    'type': 'api_key',
    'provider': 'openrouter',
    'keyRef': {'source': 'env', 'provider': 'default', 'id': 'OPENROUTER_API_KEY'},
}
with open(path, 'w') as f:
    json.dump(ap, f, indent=2)
print('updated', path)
PY

# ---------------------------------------------------------------------------
# 6. Clear stale plugin credentials so next gateway start enrolls cleanly
# ---------------------------------------------------------------------------
if [[ -f "$CRED_PATH" ]]; then
  log "removing stale plugin credentials at $CRED_PATH"
  rm -f "$CRED_PATH"
fi

log "setup complete"
log "next: start the gateway with OPENROUTER_API_KEY in env, e.g."
log "  set -a; source $ENV_FILE; set +a"
log "  cd $OPENCLAW_DIR && node openclaw.mjs gateway --force"
log "or run: $(dirname "$0")/start-gateway.sh"
