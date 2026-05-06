#!/usr/bin/env bash
# Load secrets from .env file into a Kubernetes Secret
# Usage: ./load-secrets.sh [path-to-env-file]
set -euo pipefail

ENV_FILE="${1:-$(dirname "$0")/../../registry/.env}"
NAMESPACE="${NAMESPACE:-recursant}"
SECRET_NAME="${SECRET_NAME:-recursant-secrets}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    echo "Usage: $0 [path-to-env-file]"
    exit 1
fi

echo "Loading secrets from: $ENV_FILE"

# Ensure namespace exists
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || \
    kubectl create namespace "$NAMESPACE"

# Build --from-literal args from .env file
ARGS=""
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    # Remove surrounding quotes from value
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    ARGS="$ARGS --from-literal=${key}=${value}"
done < "$ENV_FILE"

# Delete existing secret if present
kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE" --ignore-not-found

# Create secret
eval kubectl create secret generic "$SECRET_NAME" -n "$NAMESPACE" $ARGS

echo "Secret '$SECRET_NAME' created in namespace '$NAMESPACE'"
