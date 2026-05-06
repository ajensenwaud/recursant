#!/usr/bin/env bash
# Tear down both kind clusters and the shared Docker network.
set -euo pipefail

CLUSTER1="recursant-1"
CLUSTER2="recursant-2"
NETWORK="kind-multi"

echo "Deleting kind clusters ..."
kind delete cluster --name "${CLUSTER1}" 2>/dev/null || true
kind delete cluster --name "${CLUSTER2}" 2>/dev/null || true

echo "Removing shared Docker network ..."
docker network rm "${NETWORK}" 2>/dev/null || true

echo "Multi-cluster teardown complete."
