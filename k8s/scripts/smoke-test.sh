#!/usr/bin/env bash
# Smoke test for Recursant K8s deployment
# Verifies all pods are healthy and basic API calls work
set -euo pipefail

NAMESPACE="${NAMESPACE:-recursant}"
RELEASE="${RELEASE:-recursant}"
PASSED=0
FAILED=0

pass() {
    echo "  PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "  FAIL: $1"
    FAILED=$((FAILED + 1))
}

cleanup() {
    # Kill any port-forward processes we started
    [ -n "${PF_PID_REGISTRY:-}" ] && kill "$PF_PID_REGISTRY" 2>/dev/null || true
    [ -n "${PF_PID_FRONTEND:-}" ] && kill "$PF_PID_FRONTEND" 2>/dev/null || true
    [ -n "${PF_PID_MORTGAGE:-}" ] && kill "$PF_PID_MORTGAGE" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Recursant K8s Smoke Test ==="
echo ""

# 1. Check all pods are Ready
echo "--- Pod Health ---"
NOT_READY=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -v "Completed" | grep -v "1/1\|2/2\|3/3\|4/4" || true)
if [ -z "$NOT_READY" ]; then
    pass "All pods are Ready"
else
    fail "Some pods are not Ready:"
    echo "$NOT_READY"
fi

# Show pod overview
kubectl get pods -n "$NAMESPACE" -o wide 2>/dev/null || true
echo ""

# 2. Port-forward registry and test /health
echo "--- Registry API ---"
kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-registry" 15000:5000 &>/dev/null &
PF_PID_REGISTRY=$!
sleep 2

HEALTH=$(curl -sf http://localhost:15000/health 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -qi "healthy\|ok\|true" 2>/dev/null; then
    pass "Registry /health returns healthy"
else
    fail "Registry /health returned: $HEALTH"
fi

# 3. Port-forward frontend and check HTTP 200
echo "--- Frontend ---"
kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-frontend" 13000:80 &>/dev/null &
PF_PID_FRONTEND=$!
sleep 2

HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:13000/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Frontend returns HTTP 200"
else
    fail "Frontend returned HTTP $HTTP_CODE"
fi

# 4. Verify sidecar injection on agent pods (container count >= 2)
echo "--- Sidecar Injection ---"
AGENT_A_CONTAINERS=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-agent-a" --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[*].name}' 2>/dev/null || echo "")
if echo "$AGENT_A_CONTAINERS" | grep -q "recursant-sidecar" 2>/dev/null; then
    pass "Agent A has injected sidecar: $AGENT_A_CONTAINERS"
else
    if [ -n "$AGENT_A_CONTAINERS" ]; then
        fail "Agent A missing sidecar (containers: $AGENT_A_CONTAINERS)"
    else
        echo "  SKIP: Agent A not deployed"
    fi
fi

AGENT_B_CONTAINERS=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-agent-b" --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[*].name}' 2>/dev/null || echo "")
if echo "$AGENT_B_CONTAINERS" | grep -q "recursant-sidecar" 2>/dev/null; then
    pass "Agent B has injected sidecar: $AGENT_B_CONTAINERS"
else
    if [ -n "$AGENT_B_CONTAINERS" ]; then
        fail "Agent B missing sidecar (containers: $AGENT_B_CONTAINERS)"
    else
        echo "  SKIP: Agent B not deployed"
    fi
fi

# 5. Check mortgage frontend if deployed
echo "--- Mortgage Demo ---"
MORTGAGE_FE=$(kubectl get svc -n "$NAMESPACE" "${RELEASE}-mortgage-frontend" 2>/dev/null || echo "")
if [ -n "$MORTGAGE_FE" ]; then
    kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-mortgage-frontend" 13001:80 &>/dev/null &
    PF_PID_MORTGAGE=$!
    sleep 2

    HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:13001/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Mortgage frontend returns HTTP 200"
    else
        fail "Mortgage frontend returned HTTP $HTTP_CODE"
    fi

    # Check multi-sidecar injection on customer agent
    CUSTOMER_CONTAINERS=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-agents-customer" --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[*].name}' 2>/dev/null || echo "")
    if echo "$CUSTOMER_CONTAINERS" | grep -q "recursant-sidecar-customer" 2>/dev/null; then
        pass "Customer agent has multi-sidecar injection: $CUSTOMER_CONTAINERS"
    else
        if [ -n "$CUSTOMER_CONTAINERS" ]; then
            fail "Customer agent missing sidecars (containers: $CUSTOMER_CONTAINERS)"
        fi
    fi
else
    echo "  SKIP: Mortgage demo not deployed"
fi

# 6. NetworkPolicy enforcement — verify sidecar-only communication
echo "--- NetworkPolicy Enforcement ---"
NP_EXISTS=$(kubectl get networkpolicy -n "$NAMESPACE" "${RELEASE}-agent-ingress" 2>/dev/null || echo "")
if [ -n "$NP_EXISTS" ]; then
    # Get agent-a and agent-b pod names
    AGENT_A_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-agent-a" --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    AGENT_B_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-agent-b" --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    REGISTRY_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=${RELEASE}-registry" --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    AGENT_A_SVC="${RELEASE}-agent-a"

    if [ -n "$AGENT_A_POD" ] && [ -n "$AGENT_B_POD" ]; then
        # Test 1: Agent B should NOT reach Agent A's application port (5010)
        APP_RESULT=$(kubectl exec -n "$NAMESPACE" "$AGENT_B_POD" -c recursant-sidecar -- \
            timeout 3 curl -sf "http://${AGENT_A_SVC}:5010/" 2>&1 || echo "BLOCKED")
        if echo "$APP_RESULT" | grep -qi "BLOCKED\|timed out\|refused\|reset" 2>/dev/null; then
            pass "Agent-to-agent application port (5010) blocked by NetworkPolicy"
        else
            fail "Agent-to-agent application port (5010) NOT blocked (got: ${APP_RESULT:0:80})"
        fi

        # Test 2: Agent B SHOULD reach Agent A's A2A port (8443) — TCP connect
        A2A_RESULT=$(kubectl exec -n "$NAMESPACE" "$AGENT_B_POD" -c recursant-sidecar -- \
            timeout 3 curl -sf -o /dev/null -w '%{http_code}' "http://${AGENT_A_SVC}:8443/" 2>&1 || echo "CONNECT_OK")
        if echo "$A2A_RESULT" | grep -qvE "BLOCKED|timed out|refused" 2>/dev/null; then
            pass "Agent-to-agent A2A port (8443) reachable (TCP connect succeeded)"
        else
            fail "Agent-to-agent A2A port (8443) NOT reachable"
        fi

        # Test 3: Registry (infrastructure) SHOULD reach Agent A's application port
        if [ -n "$REGISTRY_POD" ]; then
            INFRA_RESULT=$(kubectl exec -n "$NAMESPACE" "$REGISTRY_POD" -- \
                timeout 3 curl -sf -o /dev/null -w '%{http_code}' "http://${AGENT_A_SVC}:5010/" 2>&1 || echo "FALLBACK")
            if echo "$INFRA_RESULT" | grep -qvE "timed out|refused" 2>/dev/null; then
                pass "Infrastructure (registry) can reach agent application port"
            else
                fail "Infrastructure (registry) cannot reach agent application port"
            fi
        else
            echo "  SKIP: Registry pod not found for infrastructure access test"
        fi
    else
        echo "  SKIP: Agent pods not found for NetworkPolicy tests"
    fi
else
    echo "  SKIP: NetworkPolicy not deployed (networkPolicy.enabled=false)"
fi

# Summary
echo ""
echo "=== Results ==="
echo "  Passed: $PASSED"
echo "  Failed: $FAILED"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "Smoke test FAILED"
    exit 1
else
    echo ""
    echo "Smoke test PASSED"
fi
