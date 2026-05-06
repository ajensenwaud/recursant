#!/usr/bin/env bash
# Create two kind clusters for multi-cluster active-active HA testing.
#
# Both clusters share a Docker bridge network (kind-multi) so pods and
# NodePort services can reach each other by node IP.
set -euo pipefail

CLUSTER1="recursant-1"
CLUSTER2="recursant-2"
NETWORK="kind-multi"

# ---------------------------------------------------------------
# Helper
# ---------------------------------------------------------------
create_cluster() {
    local name="$1" pod_subnet="$2" svc_subnet="$3" host_api="$4" host_frontend="$5"

    if kind get clusters 2>/dev/null | grep -q "^${name}$"; then
        echo "Cluster '${name}' already exists — skipping"
        return
    fi

    echo "Creating kind cluster '${name}' ..."
    cat <<EOF | kind create cluster --name "${name}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  podSubnet: "${pod_subnet}"
  serviceSubnet: "${svc_subnet}"
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30000
        hostPort: ${host_frontend}
        protocol: TCP
      - containerPort: 30500
        hostPort: ${host_api}
        protocol: TCP
      - containerPort: 30432
        hostPort: 0
        protocol: TCP
EOF
    echo "Cluster '${name}' created."
}

# ---------------------------------------------------------------
# Create both clusters
# ---------------------------------------------------------------
create_cluster "${CLUSTER1}" "10.244.0.0/16" "10.96.0.0/16"  8050 8030
create_cluster "${CLUSTER2}" "10.245.0.0/16" "10.97.0.0/16"  8052 8032

# ---------------------------------------------------------------
# Shared Docker network for cross-cluster communication
# ---------------------------------------------------------------
if ! docker network inspect "${NETWORK}" &>/dev/null; then
    echo "Creating shared Docker network '${NETWORK}' ..."
    docker network create "${NETWORK}"
fi

for container in "${CLUSTER1}-control-plane" "${CLUSTER2}-control-plane"; do
    if ! docker network inspect "${NETWORK}" | grep -q "\"${container}\""; then
        echo "Connecting ${container} to ${NETWORK} ..."
        docker network connect "${NETWORK}" "${container}"
    fi
done

# ---------------------------------------------------------------
# Print node IPs for Helm values
# ---------------------------------------------------------------
echo ""
echo "=== Cluster Node IPs ==="
C1_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID "'$(docker network inspect ${NETWORK} -f '{{.Id}}')'"}}{{.IPAddress}}{{end}}{{end}}' "${CLUSTER1}-control-plane" 2>/dev/null || docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CLUSTER1}-control-plane" | head -1)
C2_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID "'$(docker network inspect ${NETWORK} -f '{{.Id}}')'"}}{{.IPAddress}}{{end}}{{end}}' "${CLUSTER2}-control-plane" 2>/dev/null || docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CLUSTER2}-control-plane" | head -1)

# Fallback: grab the IP from the kind-multi network specifically
if [ -z "${C1_IP}" ]; then
    C1_IP=$(docker inspect "${CLUSTER1}-control-plane" -f '{{(index .NetworkSettings.Networks "kind-multi").IPAddress}}' 2>/dev/null || echo "UNKNOWN")
fi
if [ -z "${C2_IP}" ]; then
    C2_IP=$(docker inspect "${CLUSTER2}-control-plane" -f '{{(index .NetworkSettings.Networks "kind-multi").IPAddress}}' 2>/dev/null || echo "UNKNOWN")
fi

echo "  ${CLUSTER1}: ${C1_IP}"
echo "  ${CLUSTER2}: ${C2_IP}"
echo ""
echo "Use these IPs in your Helm values overlays:"
echo "  helm upgrade --install recursant k8s/charts/recursant \\"
echo "    -f k8s/charts/recursant/values-cluster-1.yaml \\"
echo "    --set multiCluster.remoteDbHost=${C2_IP} \\"
echo "    --set multiCluster.remoteRegistryUrl=http://${C2_IP}:30500 \\"
echo "    --kube-context kind-${CLUSTER1}"
echo ""
echo "Multi-cluster setup complete."
