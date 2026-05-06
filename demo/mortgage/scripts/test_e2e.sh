#!/usr/bin/env bash
# End-to-end test for the Mortgage Origination Demo (kind/k8s).
#
# Thin wrapper that executes test_e2e.py with a Python interpreter that
# has the `websockets` package available. The customer agent now serves
# its UI over WebSockets only, so the test must speak the WS protocol.
#
# Prerequisites: make mortgage-up
# Usage: ./demo/mortgage/scripts/test_e2e.sh [WS_URL]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/demo/mortgage/scripts/test_e2e.py"

# Pick a Python interpreter with `websockets` installed. Prefer registry's
# venv since the registry already depends on websockets via Flask-Sock.
PY=""
for candidate in \
    "$REPO_ROOT/registry/.venv/bin/python" \
    "$REPO_ROOT/mesh/.venv/bin/python" \
    "python3" \
    "python"; do
    if "$candidate" -c "import websockets" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "ERROR: no Python interpreter with the 'websockets' package found." >&2
    echo "Install it with: pip install websockets" >&2
    exit 1
fi

exec "$PY" "$SCRIPT" "$@"
