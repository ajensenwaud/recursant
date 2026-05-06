#!/usr/bin/env bash
# One-shot installer for Recursant.
#
# Brings up a local Kind cluster, builds all Docker images, loads them into
# the cluster, deploys the Helm chart, and runs the smoke test. Reads
# secrets and LLM API keys from .env (you must create this first; see
# .env.sample).
#
# Usage:
#   ./scripts/install.sh                 # full install (k8s-down + up + build + load + install + smoke)
#   ./scripts/install.sh --skip-prereqs  # don't validate prerequisites first
#   ./scripts/install.sh --no-cluster    # skip cluster creation; assume one is already up

set -euo pipefail

cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { printf "\n%b==>%b %s\n" "$GREEN" "$NC" "$1"; }
warn() { printf "%b!%b %s\n" "$YELLOW" "$NC" "$1"; }
fail() { printf "%b✗%b %s\n" "$RED" "$NC" "$1" >&2; exit 1; }

SKIP_PREREQS=0
NO_CLUSTER=0
for arg in "$@"; do
    case "$arg" in
        --skip-prereqs) SKIP_PREREQS=1 ;;
        --no-cluster)   NO_CLUSTER=1 ;;
        -h|--help)
            sed -n '2,15p' "$0"; exit 0 ;;
        *)  fail "Unknown argument: $arg" ;;
    esac
done

# 1. Prereqs.
if [ "$SKIP_PREREQS" -eq 0 ]; then
    step "Checking prerequisites"
    "$(dirname "$0")/check-prereqs.sh"
fi

# 2. .env present?
step "Validating configuration"
if [ ! -f .env ]; then
    fail ".env not found. Run: cp .env.sample .env && \$EDITOR .env"
fi

# At minimum, one LLM API key must be set or the eval / guardrails won't work.
if ! grep -qE '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY|MOONSHOT_API_KEY)=[^[:space:]]+' .env; then
    warn "No LLM API key set in .env. Evaluation and guardrails will fail at runtime."
    warn "Set at least one of: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY."
    read -rp "Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

# 3. Cluster + build + load + install + smoke test.
if [ "$NO_CLUSTER" -eq 1 ]; then
    step "Skipping cluster creation (--no-cluster). Building and deploying onto existing cluster."
    make k8s-build
    make k8s-load
    make k8s-install
    make k8s-smoke-test
else
    step "Bringing up Kind cluster + building + deploying (this takes 5–15 minutes)"
    make k8s-all
fi

step "Done."
echo
echo "Open the registry UI:    http://localhost:8030"
echo "Open the mortgage demo:  http://localhost:8031"
echo "Registry API:            http://localhost:8050"
echo
echo "Login:  username 'admin' (or whatever ADMIN_USERNAME you set in .env)"
echo "        password from ADMIN_PASSWORD in .env"
echo
echo "Try the demo:"
echo "  python3 demo/mortgage/scripts/test_e2e.py"
echo
echo "Tear down:"
echo "  ./scripts/teardown.sh"
