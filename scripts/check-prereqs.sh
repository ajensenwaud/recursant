#!/usr/bin/env bash
# Check that all prerequisites for Recursant are installed.
# Exits 0 if everything is present, non-zero with a list of missing tools
# otherwise.
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Print a status line with coloured marker.
status() {
    local mark="$1" colour="$2" name="$3" version="${4:-}"
    if [ -n "$version" ]; then
        printf "  %b%s%b %s (%s)\n" "$colour" "$mark" "$NC" "$name" "$version"
    else
        printf "  %b%s%b %s\n" "$colour" "$mark" "$NC" "$name"
    fi
}

# Check command + extract version when present.
check() {
    local name="$1" cmd="$2" version_cmd="${3:-}"
    if command -v "$cmd" >/dev/null 2>&1; then
        local v=""
        [ -n "$version_cmd" ] && v="$(eval "$version_cmd" 2>/dev/null | head -1 || true)"
        status "✓" "$GREEN" "$name" "$v"
        return 0
    else
        status "✗" "$RED" "$name (missing)"
        MISSING+=("$name")
        return 1
    fi
}

echo "Recursant prerequisite check"
echo "============================"
echo
MISSING=()

check "docker"  docker  "docker --version"            || true
check "kind"    kind    "kind --version"              || true
check "kubectl" kubectl "kubectl version --client=true | head -1" || true
check "helm"    helm    "helm version --short"        || true
check "python3" python3 "python3 --version"           || true
check "node"    node    "node --version"              || true
check "make"    make    "make --version | head -1"    || true

# Python version >= 3.11 ?
if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
        status "!" "$YELLOW" "python3 is < 3.11 (registry needs 3.11+)"
        MISSING+=("python3>=3.11")
    fi
fi

# Node version >= 18 ?
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node --version | sed -E 's/^v?([0-9]+).*/\1/')
    if [ "$NODE_MAJOR" -lt 18 ]; then
        status "!" "$YELLOW" "node is < 18 (frontend needs 18+)"
        MISSING+=("node>=18")
    fi
fi

echo
if [ ${#MISSING[@]} -eq 0 ]; then
    printf "%bAll prerequisites present.%b\n" "$GREEN" "$NC"
    exit 0
else
    printf "%bMissing or outdated:%b %s\n" "$RED" "$NC" "${MISSING[*]}"
    echo
    echo "Install hints:"
    echo "  Docker:   https://docs.docker.com/get-docker/"
    echo "  Kind:     https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
    echo "  kubectl:  https://kubernetes.io/docs/tasks/tools/"
    echo "  Helm:     https://helm.sh/docs/intro/install/"
    echo "  Python:   https://www.python.org/downloads/  (3.11+ required)"
    echo "  Node:     https://nodejs.org/  (18+ required)"
    exit 1
fi
