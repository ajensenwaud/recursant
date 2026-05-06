#!/bin/bash
# Discovery test harness — builds simulator, starts 50-container topology,
# seeds governed agents, runs integration tests, then tears down.
#
# Usage:
#   ./run_discovery_tests.sh          # full run
#   ./run_discovery_tests.sh --up     # just start topology
#   ./run_discovery_tests.sh --down   # just tear down
#   ./run_discovery_tests.sh --test   # just run tests (topology must be up)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.discovery-test.yaml"
SIMULATOR_DIR="$SCRIPT_DIR/simulator"
PROJECT_NAME="discovery-test"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[discovery-test]${NC} $1"; }
warn() { echo -e "${YELLOW}[discovery-test]${NC} $1"; }
err() { echo -e "${RED}[discovery-test]${NC} $1"; }

# ----------------------------------------------------------------
# Build simulator image
# ----------------------------------------------------------------
build_simulator() {
    log "Building discovery-test-agent image..."
    docker build -t discovery-test-agent "$SIMULATOR_DIR"
}

# ----------------------------------------------------------------
# Start topology
# ----------------------------------------------------------------
start_topology() {
    log "Starting 50-container topology..."
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d

    log "Waiting for all containers to be healthy..."
    local max_wait=120
    local waited=0
    while [ $waited -lt $max_wait ]; do
        local total=$(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps -q | wc -l)
        local healthy=$(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps | grep -c "(healthy)" || true)
        local running=$(docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps --status running -q | wc -l)

        if [ "$running" -ge 49 ]; then  # 49 because nginx:alpine doesn't have healthcheck
            log "All containers running ($running/$total)"
            break
        fi

        sleep 2
        waited=$((waited + 2))
        echo -ne "  Waiting... $running/$total running (${waited}s)\r"
    done

    if [ $waited -ge $max_wait ]; then
        warn "Timeout waiting for containers. Some may not be ready."
        docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps
    fi
}

# ----------------------------------------------------------------
# Stop topology
# ----------------------------------------------------------------
stop_topology() {
    log "Stopping topology..."
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down -v --remove-orphans
}

# ----------------------------------------------------------------
# Run tests
# ----------------------------------------------------------------
run_tests() {
    log "Running discovery integration tests..."

    # Find the registry pod name
    local pod=$(kubectl get pods -l app=registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$pod" ]; then
        warn "No registry pod found in Kubernetes. Running tests locally instead."
        cd "$SCRIPT_DIR/../.."
        python3 -m pytest tests/discovery/ -v --tb=short "$@"
    else
        log "Running tests via kubectl exec in pod: $pod"
        kubectl exec "$pod" -- python3 -m pytest tests/discovery/ -v --tb=short "$@"
    fi
}

# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------
case "${1:-all}" in
    --up)
        build_simulator
        start_topology
        ;;
    --down)
        stop_topology
        ;;
    --test)
        shift
        run_tests "$@"
        ;;
    --build)
        build_simulator
        ;;
    all)
        build_simulator
        start_topology
        shift || true
        run_tests "$@"
        stop_topology
        ;;
    *)
        echo "Usage: $0 [--up|--down|--test|--build|all]"
        exit 1
        ;;
esac
