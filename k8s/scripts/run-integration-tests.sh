#!/usr/bin/env bash
# Run integration tests against the K8s cluster.
#
# Usage:
#   bash k8s/scripts/run-integration-tests.sh                    # all tests
#   bash k8s/scripts/run-integration-tests.sh governance          # tool governance only
#   bash k8s/scripts/run-integration-tests.sh compliance          # CrewAI compliance (including LLM)
#   bash k8s/scripts/run-integration-tests.sh compliance-nollm    # compliance without LLM tests
#   bash k8s/scripts/run-integration-tests.sh k8s-features        # K8s feature tests (audit, HA, etc.)
#   bash k8s/scripts/run-integration-tests.sh registry-e2e        # registry E2E (evaluation + security scan)
#   bash k8s/scripts/run-integration-tests.sh smoke               # K8s smoke tests
#   bash k8s/scripts/run-integration-tests.sh a2a                 # A2A roundtrip tests (in-cluster)
#   bash k8s/scripts/run-integration-tests.sh llm-roundtrip       # LLM roundtrip tests (in-cluster)
#   bash k8s/scripts/run-integration-tests.sh isolation            # Agent isolation tests (in-cluster)
#   bash k8s/scripts/run-integration-tests.sh banking              # Complex banking/mortgage tests (in-cluster)
#   bash k8s/scripts/run-integration-tests.sh registry-lifecycle   # Registry lifecycle tests (from host)
#   bash k8s/scripts/run-integration-tests.sh governance-enforcement  # Governance enforcement (from host)
#   bash k8s/scripts/run-integration-tests.sh guardrail-integration  # Guardrail API integration (from host)
#
# Most tests run inside the registry pod via kubectl cp + exec.
# test_k8s_features.py, test_registry_lifecycle.py, and test_governance_enforcement.py
# run from the host (need kubectl + mesh venv).

set -uo pipefail

NAMESPACE="${K8S_NAMESPACE:-recursant}"
RELEASE="${K8S_RELEASE:-recursant}"
SUITE="${1:-all}"

# Resolve the registry pod name
POD=$(kubectl get pod -n "$NAMESPACE" -l "app=${RELEASE}-registry" -o jsonpath='{.items[0].metadata.name}')
if [[ -z "$POD" ]]; then
    echo "ERROR: Could not find registry pod"
    exit 1
fi
echo "Using registry pod: $POD"

# Resolve the DB pod name
DB_POD=$(kubectl get pod -n "$NAMESPACE" -l "app=${RELEASE}-db" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

# Get secrets from K8s
ADMIN_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "${RELEASE}-secrets" -o jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d)
MESH_API_KEY=$(kubectl get secret -n "$NAMESPACE" "${RELEASE}-secrets" -o jsonpath='{.data.MESH_API_KEY}' 2>/dev/null | base64 -d || echo "mesh-dev-key")
ANTHROPIC_API_KEY=$(kubectl get secret -n "$NAMESPACE" "${RELEASE}-secrets" -o jsonpath='{.data.ANTHROPIC_API_KEY}' 2>/dev/null | base64 -d || echo "")
OPENAI_API_KEY=$(kubectl get secret -n "$NAMESPACE" "${RELEASE}-secrets" -o jsonpath='{.data.OPENAI_API_KEY}' 2>/dev/null | base64 -d || echo "")

# K8s service URLs for agent/sidecar tests
AGENT_A_URL="http://${RELEASE}-agent-a:5010"
AGENT_B_URL="http://${RELEASE}-agent-b:5011"
SIDECAR_A_URL="http://${RELEASE}-agent-a:9901"
SIDECAR_B_URL="http://${RELEASE}-agent-b:9902"
SIDECAR_A_A2A_URL="https://${RELEASE}-agent-a:8443"
SIDECAR_B_A2A_URL="https://${RELEASE}-agent-b:8444"
REGISTRY_DB_HOST="${RELEASE}-db"

# K8s service URLs for mortgage/compliance agents
COMPLIANCE_AGENT_URL="http://${RELEASE}-agents-compliance:5025"
COMPLIANCE_SIDECAR_URL="http://${RELEASE}-agents-compliance:9915"

# Mortgage agent URLs
CUSTOMER_AGENT_URL="http://${RELEASE}-agents-customer:5020"
CUSTOMER_SIDECAR_URL="http://${RELEASE}-agents-customer:9910"
AUTH_AGENT_URL="http://${RELEASE}-agents-customer:5021"
AUTH_SIDECAR_URL="http://${RELEASE}-agents-customer:9911"
KYC_AGENT_URL="http://${RELEASE}-n8n-kyc:5022"
KYC_SIDECAR_URL="http://${RELEASE}-n8n-kyc:9912"
CREDIT_AGENT_URL="http://${RELEASE}-agents-kyc-credit:5023"
CREDIT_SIDECAR_URL="http://${RELEASE}-agents-kyc-credit:9913"
CORE_BANKING_AGENT_URL="http://${RELEASE}-agents-core-banking:5024"
CORE_BANKING_SIDECAR_URL="http://${RELEASE}-agents-core-banking:9914"

# Create a temp directory inside the pod for test files
kubectl exec -n "$NAMESPACE" "$POD" -c registry -- mkdir -p /tmp/tests

# ---------------------------------------------------------------------------
# Helper: copy a test file into the registry pod and run pytest
# Usage: run_test <src_file> [extra pytest args...]
# ---------------------------------------------------------------------------
run_test() {
    local src="$1"
    shift
    local filename
    filename=$(basename "$src")

    echo ""
    echo "========================================"
    echo "Running: $filename $*"
    echo "========================================"

    kubectl cp "$src" "$NAMESPACE/$POD:/tmp/tests/$filename" -c registry

    if kubectl exec -n "$NAMESPACE" "$POD" -c registry -- env \
        REGISTRY_URL="http://localhost:5000" \
        ADMIN_USERNAME="admin" \
        ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        REGISTRY_PASSWORD="$ADMIN_PASSWORD" \
        MESH_API_KEY="$MESH_API_KEY" \
        ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
        OPENAI_API_KEY="$OPENAI_API_KEY" \
        AGENT_A_URL="$AGENT_A_URL" \
        AGENT_B_URL="$AGENT_B_URL" \
        SIDECAR_A_URL="$SIDECAR_A_URL" \
        SIDECAR_B_URL="$SIDECAR_B_URL" \
        SIDECAR_A_A2A_URL="$SIDECAR_A_A2A_URL" \
        SIDECAR_B_A2A_URL="$SIDECAR_B_A2A_URL" \
        REGISTRY_DB_HOST="$REGISTRY_DB_HOST" \
        K8S_RELEASE="$RELEASE" \
        COMPLIANCE_AGENT_URL="$COMPLIANCE_AGENT_URL" \
        COMPLIANCE_SIDECAR_URL="$COMPLIANCE_SIDECAR_URL" \
        CUSTOMER_AGENT_URL="$CUSTOMER_AGENT_URL" \
        CUSTOMER_SIDECAR_URL="$CUSTOMER_SIDECAR_URL" \
        AUTH_AGENT_URL="$AUTH_AGENT_URL" \
        AUTH_SIDECAR_URL="$AUTH_SIDECAR_URL" \
        KYC_AGENT_URL="$KYC_AGENT_URL" \
        KYC_SIDECAR_URL="$KYC_SIDECAR_URL" \
        CREDIT_AGENT_URL="$CREDIT_AGENT_URL" \
        CREDIT_SIDECAR_URL="$CREDIT_SIDECAR_URL" \
        CORE_BANKING_AGENT_URL="$CORE_BANKING_AGENT_URL" \
        CORE_BANKING_SIDECAR_URL="$CORE_BANKING_SIDECAR_URL" \
        python -m pytest "/tmp/tests/$filename" -v "$@"; then
        echo ""
        echo "$filename: PASSED"
        return 0
    else
        local rc=$?
        echo ""
        echo "$filename: FAILED (exit code $rc)"
        return $rc
    fi
}

# ---------------------------------------------------------------------------
# Helper: copy a directory of test files (with conftest) and run pytest
# Usage: run_test_dir <src_dir> <test_file_relative> [extra pytest args...]
# ---------------------------------------------------------------------------
run_test_dir() {
    local src_dir="$1"
    local test_file="$2"
    shift 2
    local dirname
    dirname=$(basename "$src_dir")

    echo ""
    echo "========================================"
    echo "Running: $dirname/$test_file $*"
    echo "========================================"

    # Copy the entire test directory
    kubectl exec -n "$NAMESPACE" "$POD" -c registry -- mkdir -p "/tmp/tests/$dirname"
    for f in "$src_dir"/*.py; do
        kubectl cp "$f" "$NAMESPACE/$POD:/tmp/tests/$dirname/$(basename "$f")" -c registry
    done

    if kubectl exec -n "$NAMESPACE" "$POD" -c registry -- env \
        REGISTRY_URL="http://localhost:5000" \
        ADMIN_USERNAME="admin" \
        ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        REGISTRY_PASSWORD="$ADMIN_PASSWORD" \
        MESH_API_KEY="$MESH_API_KEY" \
        ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
        OPENAI_API_KEY="$OPENAI_API_KEY" \
        AGENT_A_URL="$AGENT_A_URL" \
        AGENT_B_URL="$AGENT_B_URL" \
        SIDECAR_A_URL="$SIDECAR_A_URL" \
        SIDECAR_B_URL="$SIDECAR_B_URL" \
        SIDECAR_A_A2A_URL="$SIDECAR_A_A2A_URL" \
        SIDECAR_B_A2A_URL="$SIDECAR_B_A2A_URL" \
        REGISTRY_DB_HOST="$REGISTRY_DB_HOST" \
        K8S_RELEASE="$RELEASE" \
        COMPLIANCE_AGENT_URL="$COMPLIANCE_AGENT_URL" \
        COMPLIANCE_SIDECAR_URL="$COMPLIANCE_SIDECAR_URL" \
        CUSTOMER_AGENT_URL="$CUSTOMER_AGENT_URL" \
        CUSTOMER_SIDECAR_URL="$CUSTOMER_SIDECAR_URL" \
        AUTH_AGENT_URL="$AUTH_AGENT_URL" \
        AUTH_SIDECAR_URL="$AUTH_SIDECAR_URL" \
        KYC_AGENT_URL="$KYC_AGENT_URL" \
        KYC_SIDECAR_URL="$KYC_SIDECAR_URL" \
        CREDIT_AGENT_URL="$CREDIT_AGENT_URL" \
        CREDIT_SIDECAR_URL="$CREDIT_SIDECAR_URL" \
        CORE_BANKING_AGENT_URL="$CORE_BANKING_AGENT_URL" \
        CORE_BANKING_SIDECAR_URL="$CORE_BANKING_SIDECAR_URL" \
        TEST_DATABASE_URL="postgresql://registry:registry@${RELEASE}-db:5432/registry_test" \
        TEST_AGENT_URL="http://${RELEASE}-test-agent:5001" \
        python -m pytest "/tmp/tests/$dirname/$test_file" -v "$@"; then
        echo ""
        echo "$dirname/$test_file: PASSED"
        return 0
    else
        local rc=$?
        echo ""
        echo "$dirname/$test_file: FAILED (exit code $rc)"
        return $rc
    fi
}

# ---------------------------------------------------------------------------
# Helper: run test from host (needs kubectl + mesh venv)
# Usage: run_host_test <test_file> [extra pytest args...]
# ---------------------------------------------------------------------------
run_host_test() {
    local test_file="$1"
    shift
    local filename
    filename=$(basename "$test_file")

    echo ""
    echo "========================================"
    echo "Running: $filename (from host) $*"
    echo "========================================"

    local pytest_cmd="mesh/.venv/bin/pytest"
    if [[ ! -x "$pytest_cmd" ]]; then
        pytest_cmd="pytest"
    fi

    # Start a port-forward to the registry if port 8050 isn't already accessible
    local pf_pid=""
    local registry_url="http://127.0.0.1:8050"
    if ! curl -sf "$registry_url/health" >/dev/null 2>&1; then
        echo "Starting port-forward to registry..."
        local pf_port=18050
        kubectl port-forward -n "$NAMESPACE" "svc/${RELEASE}-registry" "$pf_port:5000" >/dev/null 2>&1 &
        pf_pid=$!
        sleep 2
        registry_url="http://127.0.0.1:$pf_port"
        if ! curl -sf "$registry_url/health" >/dev/null 2>&1; then
            echo "ERROR: Could not reach registry via port-forward"
            kill "$pf_pid" 2>/dev/null || true
            return 1
        fi
    fi

    local rc=0
    if K8S_NAMESPACE="$NAMESPACE" K8S_RELEASE="$RELEASE" \
       K8S_REGISTRY_URL="$registry_url" \
       ADMIN_PASSWORD="$ADMIN_PASSWORD" MESH_API_KEY="$MESH_API_KEY" \
       ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" OPENAI_API_KEY="$OPENAI_API_KEY" \
       $pytest_cmd "$test_file" -v "$@"; then
        echo ""
        echo "$filename: PASSED"
    else
        rc=$?
        echo ""
        echo "$filename: FAILED (exit code $rc)"
    fi

    # Clean up port-forward
    if [[ -n "$pf_pid" ]]; then
        kill "$pf_pid" 2>/dev/null || true
        wait "$pf_pid" 2>/dev/null || true
    fi
    return $rc
}

# ---------------------------------------------------------------------------
# Helper: run test_k8s_features.py from the host (needs kubectl + mesh venv)
# ---------------------------------------------------------------------------
run_k8s_features() {
    run_host_test "mesh/tests/integration/test_k8s_features.py" "$@"
}

# ---------------------------------------------------------------------------
# Helper: ensure registry_test database exists on the DB pod
# ---------------------------------------------------------------------------
ensure_test_db() {
    if [[ -z "$DB_POD" ]]; then
        echo "WARNING: DB pod not found, skipping test DB creation"
        return 1
    fi
    kubectl exec -n "$NAMESPACE" "$DB_POD" -- \
        psql -U registry -tc "SELECT 1 FROM pg_database WHERE datname = 'registry_test'" \
        | grep -q 1 \
        || kubectl exec -n "$NAMESPACE" "$DB_POD" -- \
            psql -U registry -c "CREATE DATABASE registry_test" 2>/dev/null
}

# Track overall result
EXIT_CODE=0

case "$SUITE" in
    governance)
        run_test "mesh/tests/integration/test_tool_governance.py" || EXIT_CODE=$?
        ;;
    compliance)
        run_test "demo/mortgage/tests/test_crewai_compliance.py" || EXIT_CODE=$?
        ;;
    compliance-nollm)
        run_test "demo/mortgage/tests/test_crewai_compliance.py" -m "not llm" || EXIT_CODE=$?
        ;;
    k8s-features)
        run_k8s_features || EXIT_CODE=$?
        ;;
    registry-e2e)
        ensure_test_db
        run_test_dir "registry/tests/integration" "test_e2e_security_scan.py" || EXIT_CODE=$?
        run_test_dir "registry/tests/integration" "test_e2e_evaluation.py" || EXIT_CODE=$?
        ;;
    smoke)
        bash k8s/scripts/smoke-test.sh || EXIT_CODE=$?
        ;;
    a2a)
        run_test "mesh/tests/integration/test_a2a_roundtrip.py" || EXIT_CODE=$?
        ;;
    llm-roundtrip)
        run_test "mesh/tests/integration/test_llm_roundtrip.py" || EXIT_CODE=$?
        ;;
    isolation)
        run_test "mesh/tests/integration/test_agent_isolation.py" || EXIT_CODE=$?
        ;;
    banking)
        run_test "mesh/tests/integration/test_complex_banking.py" || EXIT_CODE=$?
        ;;
    registry-lifecycle)
        run_host_test "mesh/tests/integration/test_registry_lifecycle.py" || EXIT_CODE=$?
        ;;
    governance-enforcement)
        run_host_test "mesh/tests/integration/test_governance_enforcement.py" || EXIT_CODE=$?
        ;;
    guardrail-integration)
        run_host_test "mesh/tests/integration/test_guardrail_integration.py" || EXIT_CODE=$?
        ;;
    all)
        # 1. K8s smoke tests (pod health, sidecar injection, NetworkPolicy)
        echo ""
        echo "========================================"
        echo "Running: K8s smoke tests"
        echo "========================================"
        bash k8s/scripts/smoke-test.sh || EXIT_CODE=$?

        # 2. Tool governance (23 tests: CRUD, sidecar endpoints, egress, MCP metadata)
        run_test "mesh/tests/integration/test_tool_governance.py" || EXIT_CODE=$?

        # 3. CrewAI compliance with LLM (11 tests: health, registration, tools, sidecar, A2A+LLM, audit)
        run_test "demo/mortgage/tests/test_crewai_compliance.py" || EXIT_CODE=$?

        # 4. K8s features — audit explorer, traffic weight, NetworkPolicy (from host)
        run_k8s_features || EXIT_CODE=$?

        # 5. Registry E2E — evaluation + security scan (inside registry pod)
        ensure_test_db
        run_test_dir "registry/tests/integration" "test_e2e_security_scan.py" || EXIT_CODE=$?
        run_test_dir "registry/tests/integration" "test_e2e_evaluation.py" || EXIT_CODE=$?

        # 6. A2A roundtrip (in-cluster — agent-a/b with sidecars)
        run_test "mesh/tests/integration/test_a2a_roundtrip.py" || EXIT_CODE=$?

        # 7. LLM roundtrip (in-cluster — requires LLM API key)
        run_test "mesh/tests/integration/test_llm_roundtrip.py" || EXIT_CODE=$?

        # 8. Agent isolation (in-cluster — DRAFT agent rejection)
        run_test "mesh/tests/integration/test_agent_isolation.py" || EXIT_CODE=$?

        # 9. Complex banking/mortgage (in-cluster — requires mortgage deployment)
        run_test "mesh/tests/integration/test_complex_banking.py" || EXIT_CODE=$?

        # 10. Registry lifecycle (from host — imports sidecar library)
        run_host_test "mesh/tests/integration/test_registry_lifecycle.py" || EXIT_CODE=$?

        # 11. Governance enforcement (from host — dynamic status changes)
        run_host_test "mesh/tests/integration/test_governance_enforcement.py" || EXIT_CODE=$?

        # 12. Guardrail integration (from host — CRUD, lifecycle, sidecar endpoint, assignments)
        run_host_test "mesh/tests/integration/test_guardrail_integration.py" || EXIT_CODE=$?
        ;;
    *)
        echo "Unknown suite: $SUITE"
        echo "Usage: $0 [governance|compliance|compliance-nollm|k8s-features|registry-e2e|smoke|a2a|llm-roundtrip|isolation|banking|registry-lifecycle|governance-enforcement|guardrail-integration|all]"
        exit 1
        ;;
esac

# Cleanup
kubectl exec -n "$NAMESPACE" "$POD" -c registry -- rm -rf /tmp/tests 2>/dev/null || true

if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "SOME TESTS FAILED (exit code $EXIT_CODE)"
    exit $EXIT_CODE
fi

echo ""
echo "ALL TESTS PASSED"
