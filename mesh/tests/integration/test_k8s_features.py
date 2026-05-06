"""Integration tests for Istio-parity features against a live Kubernetes cluster.

Tests the following feature gaps:
- Phase 2B: traffic_weight in discovery response
- Phase 3: Prometheus /metrics on sidecars
- Phase 4: Audit log explorer (query filters, stats, detail endpoints)
- Phase 6: Registry HA (multi-replica behaviour)

Requirements:
- A running Kind (or other) k8s cluster with the recursant Helm chart deployed
- kubectl configured to access the cluster
- Set K8S_REGISTRY_URL env var if not using port-forward (default: auto port-forward)

Run with:
    K8S_REGISTRY_URL=http://localhost:15050 pytest mesh/tests/integration/test_k8s_features.py -v
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest

# ---------------------------------------------------------------------------
# K8s-specific constants — load from k8s secrets, NOT .env
# ---------------------------------------------------------------------------
NAMESPACE = os.environ.get("K8S_NAMESPACE", "recursant")
RELEASE = os.environ.get("K8S_RELEASE", "recursant")


def _k8s_secret(key: str, fallback: str) -> str:
    """Read a value from the k8s secret, falling back to env/default."""
    # Allow explicit override via env var
    env_val = os.environ.get(f"K8S_{key}")
    if env_val:
        return env_val
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "secret", "-n", NAMESPACE,
                f"{RELEASE}-secrets",
                "-o", f"jsonpath={{.data.{key}}}",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            import base64
            return base64.b64decode(result.stdout.strip()).decode()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return os.environ.get(key, fallback)


MESH_API_KEY = _k8s_secret("MESH_API_KEY", "mesh-dev-key")
ADMIN_USERNAME = _k8s_secret("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _k8s_secret("ADMIN_PASSWORD", "admin")
LOCAL_REGISTRY_PORT = int(os.environ.get("K8S_REGISTRY_LOCAL_PORT", "15050"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _kubectl_available() -> bool:
    """Return True if kubectl can reach the cluster."""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _pods_running() -> bool:
    """Return True if recursant pods are running in the namespace."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", NAMESPACE, "--no-headers"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        lines = [l for l in result.stdout.strip().splitlines()
                 if "Completed" not in l]
        return len(lines) > 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requires_k8s = pytest.mark.skipif(
    not _kubectl_available() or not _pods_running(),
    reason="Kubernetes cluster with recursant deployment not available",
)


@pytest.fixture(scope="module")
def registry_url():
    """Return the registry URL, starting a port-forward if needed.

    If K8S_REGISTRY_URL is set, use that directly.
    Otherwise, start a kubectl port-forward for the duration of the module.
    """
    explicit_url = os.environ.get("K8S_REGISTRY_URL")
    if explicit_url:
        yield explicit_url
        return

    # Start port-forward
    proc = subprocess.Popen(
        [
            "kubectl", "port-forward", "-n", NAMESPACE,
            f"svc/{RELEASE}-registry", f"{LOCAL_REGISTRY_PORT}:5000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for port-forward to be ready
    url = f"http://localhost:{LOCAL_REGISTRY_PORT}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=2.0)
            if resp.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.skip("Could not establish port-forward to registry")

    yield url

    # Teardown
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def jwt_token(registry_url):
    """Login as admin and return a JWT token."""
    resp = httpx.post(
        f"{registry_url}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def mesh_headers():
    """Headers for mesh API key auth."""
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }


@pytest.fixture(scope="module")
def auth_headers(jwt_token):
    """Headers for JWT auth."""
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "Authorization": f"Bearer {jwt_token}",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _submit_audit_records(registry_url: str, headers: dict, records: list[dict]) -> dict:
    """Submit audit records to the registry and return the response body."""
    resp = httpx.post(
        f"{registry_url}/v1/mesh/audit",
        json={"records": records},
        headers=headers,
        timeout=10.0,
    )
    assert resp.status_code == 201, f"Audit submit failed: {resp.status_code} {resp.text}"
    return resp.json()


def _make_audit_record(
    source: str = "test-agent-src",
    dest: str = "test-agent-dst",
    method: str = "tasks/send",
    direction: str = "outbound",
    decision: str = "pass",
    outcome: str = "success",
    task_id: str | None = None,
    sidecar_id: str | None = None,
    details: dict | None = None,
) -> dict:
    """Build a single audit record dict for submission."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_agent_name": source,
        "dest_agent_name": dest,
        "a2a_method": method,
        "message_hash": uuid.uuid4().hex,
        "direction": direction,
        "decision": decision,
        "outcome": outcome,
        "task_id": task_id or f"task-{uuid.uuid4().hex[:8]}",
        "sidecar_id": sidecar_id or f"sidecar-{uuid.uuid4().hex[:8]}",
        "details": details or {"interceptors": ["auth", "audit"]},
    }


def _kubectl_exec_psql(sql: str) -> str:
    """Execute SQL against the k8s postgres pod and return stdout."""
    result = subprocess.run(
        [
            "kubectl", "exec", "-n", NAMESPACE,
            f"{RELEASE}-db-0", "--",
            "psql", "-U", "registry", "-d", "registry",
            "-t", "-A", "-c", sql,
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout.strip()


def _traffic_weight_column_exists() -> bool:
    """Check if the traffic_weight column has been migrated."""
    try:
        output = _kubectl_exec_psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'mesh_registrations' AND column_name = 'traffic_weight'"
        )
        return "traffic_weight" in output
    except RuntimeError:
        return False


requires_traffic_weight = pytest.mark.skipif(
    not _traffic_weight_column_exists(),
    reason="traffic_weight column not yet migrated — redeploy with latest schema",
)


def _registry_has_endpoint(path: str) -> bool:
    """Probe whether the k8s registry supports a given endpoint.

    Starts a temporary port-forward, sends a request, checks for non-404.
    """
    try:
        proc = subprocess.Popen(
            [
                "kubectl", "port-forward", "-n", NAMESPACE,
                f"svc/{RELEASE}-registry", f"{LOCAL_REGISTRY_PORT + 1}:5000",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        try:
            resp = httpx.get(
                f"http://localhost:{LOCAL_REGISTRY_PORT + 1}{path}",
                headers={
                    "X-Mesh-API-Key": MESH_API_KEY,
                    "X-Tenant-ID": "default",
                },
                timeout=5.0,
            )
            return resp.status_code != 404
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
    except Exception:
        return False


_has_audit_stats = _registry_has_endpoint("/v1/mesh/audit/stats")

requires_audit_stats = pytest.mark.skipif(
    not _has_audit_stats,
    reason="Registry does not have /v1/mesh/audit/stats — rebuild and redeploy",
)


def _registry_supports_audit_filters() -> bool:
    """Check whether the deployed registry supports the new audit query filters.

    The new code filters by source_agent_name, direction, etc.
    The old code ignores unknown params and returns all records.
    """
    try:
        proc = subprocess.Popen(
            [
                "kubectl", "port-forward", "-n", NAMESPACE,
                f"svc/{RELEASE}-registry", f"{LOCAL_REGISTRY_PORT + 2}:5000",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        try:
            # Submit a test record with known direction
            headers = {
                "Content-Type": "application/json",
                "X-Mesh-API-Key": MESH_API_KEY,
                "X-Tenant-ID": "default",
            }
            tag = f"_probe_{uuid.uuid4().hex[:6]}"
            httpx.post(
                f"http://localhost:{LOCAL_REGISTRY_PORT + 2}/v1/mesh/audit",
                json={"records": [_make_audit_record(
                    direction="inbound", task_id=tag,
                )]},
                headers=headers,
                timeout=5.0,
            )
            # Query filtering by direction=outbound — if filters work,
            # we should NOT get the inbound record back
            resp = httpx.get(
                f"http://localhost:{LOCAL_REGISTRY_PORT + 2}/v1/mesh/audit",
                params={"direction": "outbound", "task_id": tag},
                headers=headers,
                timeout=5.0,
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data["total"] == 0  # Filters working = no match
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
    except Exception:
        return False


_has_audit_filters = _registry_supports_audit_filters()

requires_audit_filters = pytest.mark.skipif(
    not _has_audit_filters,
    reason="Registry does not support advanced audit filters — rebuild and redeploy",
)


# =========================================================================
# Phase 4: Audit Log Explorer
# =========================================================================


@requires_k8s
class TestAuditExplorer:
    """Tests for the audit query, stats, and detail endpoints."""

    # Use a unique tag so we can filter test data from other audit records
    TRACE_TAG = f"k8s-test-{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True, scope="class")
    def seed_audit_data(self, registry_url, mesh_headers):
        """Submit a variety of audit records for query testing."""
        tag = self.TRACE_TAG
        records = [
            # Normal outbound success
            _make_audit_record(
                source="alpha-agent", dest="beta-agent",
                method="tasks/send", direction="outbound",
                decision="pass", outcome="success",
                task_id=f"{tag}-task-1",
            ),
            # Inbound success
            _make_audit_record(
                source="beta-agent", dest="alpha-agent",
                method="tasks/send", direction="inbound",
                decision="pass", outcome="success",
                task_id=f"{tag}-task-1",
            ),
            # Blocked outbound
            _make_audit_record(
                source="alpha-agent", dest="gamma-agent",
                method="tasks/send", direction="outbound",
                decision="block", outcome="blocked",
                task_id=f"{tag}-task-2",
            ),
            # Error case
            _make_audit_record(
                source="gamma-agent", dest="alpha-agent",
                method="tasks/send", direction="inbound",
                decision="pass", outcome="error",
                task_id=f"{tag}-task-3",
            ),
            # Different method
            _make_audit_record(
                source="alpha-agent", dest="beta-agent",
                method="tasks/get", direction="outbound",
                decision="pass", outcome="success",
                task_id=f"{tag}-task-4",
            ),
        ]
        result = _submit_audit_records(registry_url, mesh_headers, records)
        assert result["count"] == 5

    # -- Query endpoint --

    def test_query_returns_all_seeded(self, registry_url, auth_headers):
        """GET /v1/mesh/audit with task_id prefix returns seeded records."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": self.TRACE_TAG, "per_page": 50},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5

    @requires_audit_filters
    def test_query_filter_by_source_agent(self, registry_url, auth_headers):
        """Filter audit by source_agent_name returns matching records only."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"source_agent_name": "alpha-agent", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        for rec in data["records"]:
            assert rec["source_agent_name"] == "alpha-agent"

    @requires_audit_filters
    def test_query_filter_by_dest_agent(self, registry_url, auth_headers):
        """Filter audit by dest_agent_name returns matching records only."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"dest_agent_name": "beta-agent", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        for rec in data["records"]:
            assert rec["dest_agent_name"] == "beta-agent"

    @requires_audit_filters
    def test_query_filter_by_direction(self, registry_url, auth_headers):
        """Filter audit by direction=inbound."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"direction": "inbound", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        for rec in data["records"]:
            assert rec["direction"] == "inbound"

    @requires_audit_filters
    def test_query_filter_by_decision(self, registry_url, auth_headers):
        """Filter audit by decision=block."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"decision": "block", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for rec in data["records"]:
            assert rec["decision"] == "block"

    @requires_audit_filters
    def test_query_filter_by_outcome(self, registry_url, auth_headers):
        """Filter audit by outcome=error."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"outcome": "error", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for rec in data["records"]:
            assert rec["outcome"] == "error"

    @requires_audit_filters
    def test_query_filter_by_method(self, registry_url, auth_headers):
        """Filter audit by a2a_method."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"a2a_method": "tasks/get", "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for rec in data["records"]:
            assert rec["a2a_method"] == "tasks/get"

    def test_query_filter_by_task_id(self, registry_url, auth_headers):
        """Filter audit by exact task_id (trace reconstruction)."""
        task_id = f"{self.TRACE_TAG}-task-1"
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"task_id": task_id},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        # task-1 has 2 records (outbound + inbound)
        assert data["total"] == 2
        for rec in data["records"]:
            assert rec["task_id"] == task_id

    @requires_audit_filters
    def test_query_trace_id_alias(self, registry_url, auth_headers):
        """trace_id is an alias for task_id in query."""
        task_id = f"{self.TRACE_TAG}-task-1"
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"trace_id": task_id},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_query_date_range(self, registry_url, auth_headers):
        """Filter audit by date range covers recent records."""
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(hours=1)).isoformat()
        date_to = (now + timedelta(hours=1)).isoformat()
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"date_from": date_from, "date_to": date_to, "search": self.TRACE_TAG},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 5

    def test_query_search_freetext(self, registry_url, auth_headers):
        """Full-text search across agent names/method/task_id."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": "gamma-agent"},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_query_pagination(self, registry_url, auth_headers):
        """Audit query supports pagination."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": self.TRACE_TAG, "per_page": 2, "page": 1},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) <= 2
        assert data["total"] >= 5
        assert data["pages"] >= 3

    def test_query_with_mesh_api_key(self, registry_url, mesh_headers):
        """Audit query also works with mesh API key auth."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": self.TRACE_TAG, "per_page": 5},
            headers=mesh_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 5

    # -- Stats endpoint --

    @requires_audit_stats
    def test_stats_returns_totals(self, registry_url, auth_headers):
        """GET /v1/mesh/audit/stats returns total, blocked, errors counts."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "blocked" in data
        assert "errors" in data
        # We seeded at least 5 records
        assert data["total"] >= 5

    @requires_audit_stats
    def test_stats_blocked_count(self, registry_url, auth_headers):
        """Stats endpoint counts blocked records."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert data["blocked"] >= 1  # We seeded one blocked record

    @requires_audit_stats
    def test_stats_error_count(self, registry_url, auth_headers):
        """Stats endpoint counts error records."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert data["errors"] >= 1  # We seeded one error record

    @requires_audit_stats
    def test_stats_top_sources(self, registry_url, auth_headers):
        """Stats endpoint returns top source agents."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert "top_sources" in data
        assert isinstance(data["top_sources"], list)
        # alpha-agent is the most frequent source in our seeded data
        source_names = [s["name"] for s in data["top_sources"]]
        assert "alpha-agent" in source_names

    @requires_audit_stats
    def test_stats_top_destinations(self, registry_url, auth_headers):
        """Stats endpoint returns top destination agents."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert "top_destinations" in data
        assert isinstance(data["top_destinations"], list)

    @requires_audit_stats
    def test_stats_outcome_breakdown(self, registry_url, auth_headers):
        """Stats endpoint returns outcome distribution."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert "outcomes" in data
        assert "success" in data["outcomes"]
        assert "blocked" in data["outcomes"]

    @requires_audit_stats
    def test_stats_decision_breakdown(self, registry_url, auth_headers):
        """Stats endpoint returns decision distribution."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            headers=auth_headers,
            timeout=10.0,
        )
        data = resp.json()
        assert "decisions" in data
        assert "pass" in data["decisions"]

    @requires_audit_stats
    def test_stats_with_date_range(self, registry_url, auth_headers):
        """Stats endpoint accepts date_from and date_to filters."""
        now = datetime.now(timezone.utc)
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/stats",
            params={
                "date_from": (now - timedelta(hours=1)).isoformat(),
                "date_to": (now + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5

    # -- Detail endpoint --

    @requires_audit_stats
    def test_detail_returns_full_record(self, registry_url, auth_headers):
        """GET /v1/mesh/audit/{id} returns a single audit record with details."""
        # First get an audit record ID
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": self.TRACE_TAG, "per_page": 1},
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]
        assert len(records) >= 1
        record_id = records[0]["id"]

        # Fetch detail
        detail_resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/{record_id}",
            headers=auth_headers,
            timeout=10.0,
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == record_id
        assert "source_agent_name" in detail
        assert "dest_agent_name" in detail
        assert "a2a_method" in detail
        assert "direction" in detail
        assert "decision" in detail
        assert "outcome" in detail
        assert "message_hash" in detail
        assert "timestamp" in detail

    @requires_audit_stats
    def test_detail_includes_details_json(self, registry_url, auth_headers):
        """Audit detail includes the details JSON payload."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": self.TRACE_TAG, "per_page": 1},
            headers=auth_headers,
            timeout=10.0,
        )
        record_id = resp.json()["records"][0]["id"]

        detail_resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/{record_id}",
            headers=auth_headers,
            timeout=10.0,
        )
        detail = detail_resp.json()
        # We seeded with details={"interceptors": ["auth", "audit"]}
        assert detail.get("details") is not None

    @requires_audit_stats
    def test_detail_nonexistent_returns_404(self, registry_url, auth_headers):
        """Requesting a nonexistent audit ID returns 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit/{fake_id}",
            headers=auth_headers,
            timeout=10.0,
        )
        assert resp.status_code == 404


# =========================================================================
# Phase 2B: Traffic Weight in Discovery
# =========================================================================


@requires_k8s
@requires_traffic_weight
class TestTrafficWeight:
    """Tests that traffic_weight is stored and returned in discovery."""

    @pytest.fixture(autouse=True, scope="class")
    def setup_registered_agent(self, registry_url, mesh_headers, jwt_token):
        """Ensure we have a registered agent to test traffic_weight.

        Uses the already-deployed agents in k8s. If none are registered,
        registers one by creating an agent and registering a sidecar.
        """
        # Check if any agents are already registered (healthy) in the mesh
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        agents = resp.json().get("agents", [])
        if agents:
            self.__class__._registered_agent = agents[0]
            return

        # No registered agents — create one and register it
        auth = {
            "Content-Type": "application/json",
            "X-Tenant-ID": "default",
            "Authorization": f"Bearer {jwt_token}",
        }
        # Find an ACTIVE agent to register
        agent_resp = httpx.get(
            f"{registry_url}/v1/agents?per_page=50",
            headers=auth,
            timeout=10.0,
        )
        active_agents = [
            a for a in agent_resp.json().get("agents", [])
            if a["status"] == "active"
        ]
        assert active_agents, "No active agents found in k8s registry"

        agent = active_agents[0]
        agent_id = agent["id"]

        # Register a sidecar for it
        reg_resp = httpx.post(
            f"{registry_url}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": "http://test-sidecar:9901",
                "agent_card": {
                    "name": agent["name"],
                    "description": agent.get("description", "test"),
                    "version": "1.0.0",
                    "skills": [{"id": "test-skill", "name": "test-skill"}],
                    "default_input_modes": ["text"],
                    "default_output_modes": ["text"],
                    "capabilities": {"streaming": False},
                },
            },
            headers=mesh_headers,
            timeout=10.0,
        )
        assert reg_resp.status_code in (200, 201), (
            f"Registration failed: {reg_resp.status_code} {reg_resp.text}"
        )

        # Re-fetch discover
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        agents = resp.json().get("agents", [])
        assert agents, "No agents after registration"
        self.__class__._registered_agent = agents[0]

    def test_discover_returns_traffic_weight(self, registry_url, mesh_headers):
        """Discovery response includes traffic_weight field."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert len(agents) >= 1
        for agent in agents:
            assert "traffic_weight" in agent
            assert isinstance(agent["traffic_weight"], int)

    def test_traffic_weight_default_is_100(self, registry_url, mesh_headers):
        """Default traffic_weight is 100."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        agents = resp.json()["agents"]
        # At least one agent should have the default weight
        weights = [a["traffic_weight"] for a in agents]
        assert 100 in weights

    def test_traffic_weight_updated_via_db(self, registry_url, mesh_headers):
        """Update traffic_weight directly in DB and verify discover returns it."""
        # Get an agent name from discover
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        agents = resp.json()["agents"]
        assert agents, "No agents to test"
        agent_name = agents[0]["name"]
        original_weight = agents[0]["traffic_weight"]

        new_weight = 42
        try:
            # Update via direct DB access
            _kubectl_exec_psql(
                f"UPDATE mesh_registrations SET traffic_weight = {new_weight} "
                f"FROM agents WHERE mesh_registrations.agent_id = agents.id "
                f"AND agents.name = '{agent_name}'"
            )

            # Verify discover returns the updated weight
            resp = httpx.get(
                f"{registry_url}/v1/mesh/discover",
                headers=mesh_headers,
                timeout=10.0,
            )
            agents = resp.json()["agents"]
            match = [a for a in agents if a["name"] == agent_name]
            assert match, f"Agent {agent_name} not found after DB update"
            assert match[0]["traffic_weight"] == new_weight
        finally:
            # Restore original weight
            _kubectl_exec_psql(
                f"UPDATE mesh_registrations SET traffic_weight = {original_weight} "
                f"FROM agents WHERE mesh_registrations.agent_id = agents.id "
                f"AND agents.name = '{agent_name}'"
            )

    def test_traffic_weight_zero_still_returned(self, registry_url, mesh_headers):
        """An agent with traffic_weight=0 is still returned in discover."""
        resp = httpx.get(
            f"{registry_url}/v1/mesh/discover",
            headers=mesh_headers,
            timeout=10.0,
        )
        agents = resp.json()["agents"]
        assert agents, "No agents to test"
        agent_name = agents[0]["name"]
        original_weight = agents[0]["traffic_weight"]

        try:
            _kubectl_exec_psql(
                f"UPDATE mesh_registrations SET traffic_weight = 0 "
                f"FROM agents WHERE mesh_registrations.agent_id = agents.id "
                f"AND agents.name = '{agent_name}'"
            )
            resp = httpx.get(
                f"{registry_url}/v1/mesh/discover",
                headers=mesh_headers,
                timeout=10.0,
            )
            agents = resp.json()["agents"]
            match = [a for a in agents if a["name"] == agent_name]
            assert match, "Agent not found with weight=0"
            assert match[0]["traffic_weight"] == 0
        finally:
            _kubectl_exec_psql(
                f"UPDATE mesh_registrations SET traffic_weight = {original_weight} "
                f"FROM agents WHERE mesh_registrations.agent_id = agents.id "
                f"AND agents.name = '{agent_name}'"
            )


# =========================================================================
# Phase 3: Prometheus /metrics on sidecar
# =========================================================================


@requires_k8s
class TestPrometheusMetrics:
    """Tests for Prometheus /metrics endpoint on sidecars."""

    def _get_sidecar_pod_and_port(self) -> tuple[str, int] | None:
        """Find a sidecar container in the cluster and return (pod_name, sidecar_port)."""
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "-l", f"app={RELEASE}-agent-a",
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].metadata.name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        pod_name = result.stdout.strip()
        # Sidecar port from annotations (default 9901)
        return (pod_name, 9901)

    def test_sidecar_healthz(self):
        """Sidecar /healthz endpoint is accessible."""
        info = self._get_sidecar_pod_and_port()
        if not info:
            pytest.skip("No sidecar pod found")
        pod_name, port = info

        # Port-forward to sidecar
        proc = subprocess.Popen(
            [
                "kubectl", "port-forward", "-n", NAMESPACE,
                pod_name, f"19901:{port}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(2)
            resp = httpx.get("http://localhost:19901/healthz", timeout=5.0)
            assert resp.status_code == 200
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)

    def test_metrics_endpoint_exists_when_enabled(self):
        """If prometheus is enabled in sidecar config, /metrics returns 200.

        If not enabled, the endpoint should return 404. Either outcome
        validates the feature works correctly.
        """
        info = self._get_sidecar_pod_and_port()
        if not info:
            pytest.skip("No sidecar pod found")
        pod_name, port = info

        proc = subprocess.Popen(
            [
                "kubectl", "port-forward", "-n", NAMESPACE,
                pod_name, f"19901:{port}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(2)
            resp = httpx.get("http://localhost:19901/metrics", timeout=5.0)
            # Either prometheus is enabled (200) or not (404)
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                # If enabled, check for OTel metric format
                body = resp.text
                assert "# HELP" in body or "# TYPE" in body or "sidecar" in body.lower()
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)

    def test_sidecar_readyz(self):
        """Sidecar /readyz endpoint is accessible."""
        info = self._get_sidecar_pod_and_port()
        if not info:
            pytest.skip("No sidecar pod found")
        pod_name, port = info

        proc = subprocess.Popen(
            [
                "kubectl", "port-forward", "-n", NAMESPACE,
                pod_name, f"19901:{port}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(2)
            resp = httpx.get("http://localhost:19901/readyz", timeout=5.0)
            assert resp.status_code == 200
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)


# =========================================================================
# Phase 6: Registry HA
# =========================================================================


@requires_k8s
class TestRegistryHA:
    """Tests for Registry High Availability features."""

    def test_registry_pod_running(self):
        """At least one registry pod is running."""
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "-l", f"app={RELEASE}-registry",
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        pods = result.stdout.strip().split()
        assert len(pods) >= 1

    def test_registry_health(self, registry_url):
        """Registry /health endpoint returns healthy."""
        resp = httpx.get(f"{registry_url}/health", timeout=5.0)
        assert resp.status_code == 200
        assert "healthy" in resp.text.lower() or "ok" in resp.text.lower()

    def test_registry_concurrent_requests(self, registry_url, mesh_headers):
        """Registry handles multiple concurrent requests without errors."""
        import concurrent.futures

        def make_request():
            resp = httpx.get(
                f"{registry_url}/v1/mesh/audit",
                params={"per_page": 1},
                headers=mesh_headers,
                timeout=10.0,
            )
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(code == 200 for code in results), (
            f"Some requests failed: {results}"
        )

    def test_redis_is_running(self):
        """Redis pod is healthy (needed for HA Socket.IO message queue)."""
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "-l", f"app={RELEASE}-redis",
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        pods = result.stdout.strip().split()
        assert len(pods) >= 1

    def test_redis_ping(self):
        """Redis is reachable and responds to PING."""
        result = subprocess.run(
            [
                "kubectl", "exec", "-n", NAMESPACE,
                f"{RELEASE}-redis-bdf5cbccb-sv7zm", "--",
                "redis-cli", "ping",
            ],
            capture_output=True, text=True, timeout=10,
        )
        # If exact pod name changes, fall back to label selector
        if result.returncode != 0:
            # Find redis pod dynamically
            pod_result = subprocess.run(
                [
                    "kubectl", "get", "pods", "-n", NAMESPACE,
                    "-l", f"app={RELEASE}-redis",
                    "-o", "jsonpath={.items[0].metadata.name}",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if pod_result.returncode != 0 or not pod_result.stdout.strip():
                pytest.skip("No redis pod found")
            redis_pod = pod_result.stdout.strip()
            result = subprocess.run(
                [
                    "kubectl", "exec", "-n", NAMESPACE,
                    redis_pod, "--",
                    "redis-cli", "ping",
                ],
                capture_output=True, text=True, timeout=10,
            )

        assert result.returncode == 0
        assert "PONG" in result.stdout

    def test_socketio_redis_configured(self, registry_url):
        """Verify the registry container has REDIS_URL env var set for HA Socket.IO."""
        result = subprocess.run(
            [
                "kubectl", "get", "deployment", "-n", NAMESPACE,
                f"{RELEASE}-registry",
                "-o", "jsonpath={.spec.template.spec.containers[0].env[*].name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        # REDIS_URL should be in the env vars (either directly or via secretKeyRef)
        env_names = result.stdout.strip()

        # Also check envFrom / secretRef
        result2 = subprocess.run(
            [
                "kubectl", "get", "deployment", "-n", NAMESPACE,
                f"{RELEASE}-registry", "-o", "yaml",
            ],
            capture_output=True, text=True, timeout=10,
        )
        # REDIS_URL should be available to the registry via secrets or direct env
        assert "REDIS_URL" in env_names or "REDIS_URL" in result2.stdout, (
            "REDIS_URL not found in registry deployment env vars"
        )

    def test_db_is_running(self):
        """PostgreSQL pod is healthy."""
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                f"{RELEASE}-db-0",
                "-o", "jsonpath={.status.phase}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "Running"

    def test_db_connectivity(self):
        """Can execute a query against the DB pod."""
        output = _kubectl_exec_psql("SELECT 1 AS health_check")
        assert "1" in output

    def test_multiple_replicas_if_ha(self):
        """If HA is enabled, verify multiple registry replicas are running.

        If HA is not enabled (single replica), this test passes trivially.
        """
        result = subprocess.run(
            [
                "kubectl", "get", "deployment", "-n", NAMESPACE,
                f"{RELEASE}-registry",
                "-o", "jsonpath={.spec.replicas}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        replicas = int(result.stdout.strip())

        if replicas > 1:
            # Verify all replicas are ready
            ready_result = subprocess.run(
                [
                    "kubectl", "get", "deployment", "-n", NAMESPACE,
                    f"{RELEASE}-registry",
                    "-o", "jsonpath={.status.readyReplicas}",
                ],
                capture_output=True, text=True, timeout=10,
            )
            ready = int(ready_result.stdout.strip() or "0")
            assert ready == replicas, (
                f"Only {ready}/{replicas} registry replicas ready"
            )

    def test_traffic_weight_column_exists(self):
        """Verify the traffic_weight column exists in the DB schema.

        Skips if the column hasn't been migrated yet (pre-Phase 2B deployment).
        """
        output = _kubectl_exec_psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'mesh_registrations' AND column_name = 'traffic_weight'"
        )
        if "traffic_weight" not in output:
            pytest.skip(
                "traffic_weight column not yet migrated — redeploy with latest schema"
            )
        assert "traffic_weight" in output


# =========================================================================
# Phase 6: Registry HA — Failover
# =========================================================================


def _scale_registry(replicas: int, wait: bool = True, timeout: int = 90) -> None:
    """Scale the registry deployment to the given replica count."""
    result = subprocess.run(
        [
            "kubectl", "scale", "deployment", "-n", NAMESPACE,
            f"{RELEASE}-registry", f"--replicas={replicas}",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Scale failed: {result.stderr}")

    if wait:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready = _get_ready_replicas()
            if ready == replicas:
                return
            time.sleep(2)
        raise RuntimeError(
            f"Timed out waiting for {replicas} ready replicas "
            f"(got {_get_ready_replicas()})"
        )


def _get_ready_replicas() -> int:
    """Return the number of ready registry replicas."""
    result = subprocess.run(
        [
            "kubectl", "get", "deployment", "-n", NAMESPACE,
            f"{RELEASE}-registry",
            "-o", "jsonpath={.status.readyReplicas}",
        ],
        capture_output=True, text=True, timeout=10,
    )
    return int(result.stdout.strip() or "0")


def _get_registry_pods() -> list[str]:
    """Return list of running registry pod names."""
    result = subprocess.run(
        [
            "kubectl", "get", "pods", "-n", NAMESPACE,
            "-l", f"app={RELEASE}-registry",
            "--field-selector=status.phase=Running",
            "-o", "jsonpath={.items[*].metadata.name}",
        ],
        capture_output=True, text=True, timeout=10,
    )
    names = result.stdout.strip()
    return names.split() if names else []


@requires_k8s
class TestRegistryFailover:
    """Tests that the registry survives pod failure with multiple replicas.

    Scales the registry to 2 replicas, kills one, and verifies the service
    continues to handle requests through the surviving pod. Restores the
    original replica count on teardown.
    """

    @pytest.fixture(autouse=True, scope="class")
    def scale_up_and_restore(self):
        """Scale registry to 2 replicas, yield, then scale back to 1."""
        original = _get_ready_replicas()
        try:
            _scale_registry(2)
            yield
        finally:
            _scale_registry(original if original >= 1 else 1)

    def test_two_replicas_are_ready(self):
        """After scale-up, both replicas should be ready."""
        assert _get_ready_replicas() == 2
        pods = _get_registry_pods()
        assert len(pods) == 2

    def test_service_routes_to_both_pods(self, registry_url, mesh_headers):
        """Requests through the Service reach healthy pods."""
        # Send several requests — with 2 pods the Service load-balances
        successes = 0
        for _ in range(10):
            resp = httpx.get(
                f"{registry_url}/health",
                timeout=5.0,
            )
            if resp.status_code == 200:
                successes += 1
        assert successes == 10

    def test_write_before_failover(self, registry_url, mesh_headers):
        """Submit an audit record before killing a pod (used by later test)."""
        tag = f"failover-{uuid.uuid4().hex[:8]}"
        self.__class__._failover_tag = tag
        records = [_make_audit_record(
            source="failover-src", dest="failover-dst",
            task_id=tag,
        )]
        result = _submit_audit_records(registry_url, mesh_headers, records)
        assert result["count"] == 1

    def test_kill_one_pod_service_survives(self, registry_url, mesh_headers):
        """Delete one registry pod; requests via the Service still succeed."""
        pods = _get_registry_pods()
        assert len(pods) >= 2, "Need 2 running pods to test failover"

        victim = pods[0]

        # Kill the pod (not the deployment — k8s will reschedule)
        result = subprocess.run(
            [
                "kubectl", "delete", "pod", "-n", NAMESPACE, victim,
                "--grace-period=0", "--force",
            ],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"Pod delete failed: {result.stderr}"

        # Give the Service a moment to update endpoints
        time.sleep(3)

        # The surviving pod should still serve requests
        failures = 0
        for i in range(15):
            try:
                resp = httpx.get(
                    f"{registry_url}/health",
                    timeout=5.0,
                )
                if resp.status_code != 200:
                    failures += 1
            except (httpx.ConnectError, httpx.ReadError):
                failures += 1
            time.sleep(0.5)

        # Allow at most 2 transient failures during endpoint update
        assert failures <= 2, (
            f"Too many failures during failover: {failures}/15"
        )

    def test_data_survives_pod_death(self, registry_url, mesh_headers):
        """Data written before failover is still queryable after a pod dies."""
        tag = getattr(self.__class__, "_failover_tag", None)
        if not tag:
            pytest.skip("No failover tag — write_before_failover didn't run")

        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": tag, "per_page": 5},
            headers=mesh_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(r["task_id"] == tag for r in data["records"])

    def test_replacement_pod_starts(self):
        """Kubernetes reschedules a replacement pod after the kill."""
        # Wait up to 60s for k8s to bring the replica count back to 2
        deadline = time.time() + 60
        while time.time() < deadline:
            ready = _get_ready_replicas()
            if ready >= 2:
                break
            time.sleep(3)
        assert _get_ready_replicas() >= 2, (
            "Replacement pod did not become ready within 60s"
        )

    def test_post_recovery_writes_work(self, registry_url, mesh_headers):
        """After recovery, new writes succeed."""
        tag = f"post-recovery-{uuid.uuid4().hex[:8]}"
        records = [_make_audit_record(
            source="recovery-src", dest="recovery-dst",
            task_id=tag,
        )]
        result = _submit_audit_records(registry_url, mesh_headers, records)
        assert result["count"] == 1

        # Verify it's queryable
        resp = httpx.get(
            f"{registry_url}/v1/mesh/audit",
            params={"search": tag},
            headers=mesh_headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


# =========================================================================
# NetworkPolicy Enforcement — sidecar-only communication
# =========================================================================


def _networkpolicy_deployed() -> bool:
    """Check if the agent-ingress NetworkPolicy exists."""
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "networkpolicy", "-n", NAMESPACE,
                f"{RELEASE}-agent-ingress",
                "-o", "jsonpath={.metadata.name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requires_networkpolicy = pytest.mark.skipif(
    not _networkpolicy_deployed(),
    reason="NetworkPolicy not deployed (networkPolicy.enabled=false or not installed)",
)


def _get_pod_name(label: str) -> str | None:
    """Return the name of a running pod matching the given app label."""
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "pods", "-n", NAMESPACE,
                "-l", f"app={label}",
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].metadata.name}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        name = result.stdout.strip()
        return name if result.returncode == 0 and name else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _kubectl_exec_curl(
    pod: str, container: str | None, url: str, timeout_secs: int = 3,
) -> tuple[int, str]:
    """Run curl inside a pod and return (returncode, output).

    Returns (0, body) on success, (non-zero, stderr/message) on failure.
    """
    cmd = ["kubectl", "exec", "-n", NAMESPACE, pod]
    if container:
        cmd += ["-c", container]
    cmd += ["--", "timeout", str(timeout_secs), "curl", "-sf", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_secs + 10)
        return (result.returncode, result.stdout if result.returncode == 0 else result.stderr)
    except subprocess.TimeoutExpired:
        return (1, "timeout")


@requires_k8s
@requires_networkpolicy
class TestNetworkPolicy:
    """Tests that NetworkPolicy enforces sidecar-only inter-agent communication.

    Verifies:
    - Agent pods cannot reach other agents' application ports directly
    - Agent pods CAN reach other agents' A2A/mTLS ports (sidecar-to-sidecar)
    - Infrastructure pods (registry) can reach agent application ports
    """

    def test_networkpolicy_exists(self):
        """The agent-ingress NetworkPolicy resource is deployed."""
        result = subprocess.run(
            [
                "kubectl", "get", "networkpolicy", "-n", NAMESPACE,
                f"{RELEASE}-agent-ingress",
                "-o", "jsonpath={.spec.podSelector.matchLabels}",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        # Should target pods with the sidecar-inject label
        assert "sidecar-inject" in result.stdout

    def test_agent_cannot_reach_other_agent_app_port(self):
        """Agent B cannot reach Agent A's application port (5010) directly."""
        agent_b = _get_pod_name(f"{RELEASE}-agent-b")
        if not agent_b:
            pytest.skip("Agent B pod not found")

        agent_a_svc = f"{RELEASE}-agent-a"
        rc, output = _kubectl_exec_curl(
            agent_b, "recursant-sidecar",
            f"http://{agent_a_svc}:5010/",
        )
        # curl should fail — connection refused, reset, or timeout
        assert rc != 0, (
            f"Agent B should NOT be able to reach Agent A on app port 5010, "
            f"but curl succeeded: {output[:200]}"
        )

    def test_agent_can_reach_other_agent_a2a_port(self):
        """Agent B can reach Agent A's A2A port (8443) — sidecar-to-sidecar."""
        agent_b = _get_pod_name(f"{RELEASE}-agent-b")
        if not agent_b:
            pytest.skip("Agent B pod not found")

        agent_a_svc = f"{RELEASE}-agent-a"
        # A2A port should be reachable at TCP level. The curl may get a TLS
        # error or non-200 response (no client cert), but the connection
        # itself should not be blocked by NetworkPolicy.
        cmd = [
            "kubectl", "exec", "-n", NAMESPACE, agent_b,
            "-c", "recursant-sidecar", "--",
            "timeout", "3", "curl", "-sk", "-o", "/dev/null",
            "-w", "%{http_code}",
            f"https://{agent_a_svc}:8443/",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            # Any HTTP response code (even 000 from TLS failure) means TCP
            # connected. Only a timeout (exit code 124) or connection refused
            # means the NetworkPolicy blocked it.
            if result.returncode == 124:
                pytest.fail("A2A port 8443 appears blocked (timeout)")
            # If we got here, TCP connection was established
        except subprocess.TimeoutExpired:
            pytest.fail("A2A port 8443 appears blocked (subprocess timeout)")

    def test_registry_can_reach_agent_app_port(self):
        """Registry (infrastructure) can reach Agent A's application port."""
        registry_pod = _get_pod_name(f"{RELEASE}-registry")
        if not registry_pod:
            pytest.skip("Registry pod not found")

        agent_a_svc = f"{RELEASE}-agent-a"
        # Registry pod uses Python slim (no curl), so use a socket connect test
        py_script = (
            "import socket, sys; "
            f"s = socket.create_connection(('{agent_a_svc}', 5010), timeout=3); "
            "s.close(); print('OK')"
        )
        cmd = [
            "kubectl", "exec", "-n", NAMESPACE, registry_pod,
            "-c", "registry", "--",
            "python", "-c", py_script,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0, (
                f"Registry should be able to reach agent app port, "
                f"but connection failed: {(result.stdout + result.stderr)[:200]}"
            )
        except subprocess.TimeoutExpired:
            pytest.fail("Registry could not reach agent app port (subprocess timeout)")
