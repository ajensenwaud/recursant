#!/usr/bin/env bash
# Create a kind cluster for Recursant with port mappings for NodePort access.
# Uses Calico CNI instead of kindnet so that NetworkPolicy is enforced.
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-recursant}"
CALICO_VERSION="${CALICO_VERSION:-v3.28.0}"

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '${CLUSTER_NAME}' already exists"
    exit 0
fi

echo "Creating kind cluster '${CLUSTER_NAME}'..."
cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  disableDefaultCNI: true
  podSubnet: "192.168.0.0/16"
nodes:
  - role: control-plane
    extraPortMappings:
      # Registry frontend (8030 to avoid conflict with Docker Compose 3000)
      - containerPort: 30000
        hostPort: 8030
        protocol: TCP
      # Registry API (8050 to avoid conflict with Docker Compose 5000)
      - containerPort: 30500
        hostPort: 8050
        protocol: TCP
      # Mortgage frontend (8031 to avoid conflict with Docker Compose 3001)
      - containerPort: 30001
        hostPort: 8031
        protocol: TCP
EOF

echo "Cluster '${CLUSTER_NAME}' created successfully"

# Install Calico CNI — required for NetworkPolicy enforcement.
# kindnet (Kind's default CNI) silently ignores NetworkPolicies.
echo "Installing Calico ${CALICO_VERSION} CNI..."
kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/calico.yaml" \
    --server-side 2>/dev/null || \
kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/calico.yaml"

# Wait for Calico pods to be ready
echo "Waiting for Calico pods to be ready (timeout 300s)..."
kubectl wait --for=condition=Ready pods -l k8s-app=calico-node -n kube-system --timeout=300s
kubectl wait --for=condition=Ready pods -l k8s-app=calico-kube-controllers -n kube-system --timeout=300s

echo "Calico CNI installed and ready"
echo "Cluster is ready. Install the chart with: make install"
