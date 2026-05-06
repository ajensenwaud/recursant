#!/usr/bin/env bash
# Tear down the kind cluster
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-recursant}"

echo "Deleting kind cluster '${CLUSTER_NAME}'..."
kind delete cluster --name "${CLUSTER_NAME}"
echo "Cluster deleted."
