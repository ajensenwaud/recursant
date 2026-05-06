#!/usr/bin/env bash
# Tear down the Recursant Kind cluster and free local resources.
#
# Usage:
#   ./scripts/teardown.sh                # delete the Kind cluster
#   ./scripts/teardown.sh --prune-images # also remove built Docker images
set -euo pipefail

cd "$(dirname "$0")/.."

PRUNE_IMAGES=0
for arg in "$@"; do
    case "$arg" in
        --prune-images) PRUNE_IMAGES=1 ;;
        -h|--help)      sed -n '2,8p' "$0"; exit 0 ;;
        *)              echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

echo "==> Deleting Kind cluster..."
make k8s-down || true

if [ "$PRUNE_IMAGES" -eq 1 ]; then
    echo "==> Removing built Recursant Docker images..."
    docker images --format '{{.Repository}}:{{.Tag}}' \
        | grep -E '^recursant-' \
        | xargs -r docker rmi -f
fi

echo "==> Done."
