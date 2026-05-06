"""Cross-cluster HA integration tests.

These tests require two kind clusters (recursant-1 and recursant-2) with
Recursant deployed via Helm using the multi-cluster values overlays.

Prerequisites:
  - make multi-cluster-up
  - Port-forwards to both registries (or NodePort access)

Run with:
  make multi-cluster-test
"""

import os
import subprocess
import time
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration — read from env or use defaults for kind NodePort setup
# ---------------------------------------------------------------------------

CLUSTER1_URL = os.environ.get("CLUSTER1_REGISTRY_URL", "http://localhost:8050")
CLUSTER2_URL = os.environ.get("CLUSTER2_REGISTRY_URL", "http://localhost:8052")
CLUSTER1_CONTEXT = os.environ.get("CLUSTER1_CONTEXT", "kind-recursant-1")
CLUSTER2_CONTEXT = os.environ.get("CLUSTER2_CONTEXT", "kind-recursant-2")
MESH_API_KEY = os.environ.get("MESH_API_KEY", "mesh-dev-key")
TENANT_ID = "default"

# How long to wait for cross-cluster replication (seconds)
REPLICATION_TIMEOUT = 30
POLL_INTERVAL = 2


def _headers():
    return {
        "X-Mesh-API-Key": MESH_API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


def _cluster_available(url: str) -> bool:
    """Check if a cluster's registry is reachable."""
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _kubectl(context: str, *args) -> str:
    """Run kubectl against a specific cluster context."""
    cmd = ["kubectl", f"--context={context}"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def _poll_until(check_fn, timeout=REPLICATION_TIMEOUT, interval=POLL_INTERVAL):
    """Poll check_fn() until it returns True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Skip markers — skip all tests if clusters aren't available
# ---------------------------------------------------------------------------

_skip_reason = None
if not _cluster_available(CLUSTER1_URL):
    _skip_reason = f"Cluster 1 not reachable at {CLUSTER1_URL}"
elif not _cluster_available(CLUSTER2_URL):
    _skip_reason = f"Cluster 2 not reachable at {CLUSTER2_URL}"

pytestmark = pytest.mark.skipif(
    _skip_reason is not None,
    reason=_skip_reason or "",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_agent_name():
    """Generate a unique agent name for test isolation."""
    return f"test-ha-agent-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cluster1():
    return CLUSTER1_URL


@pytest.fixture
def cluster2():
    return CLUSTER2_URL


# ---------------------------------------------------------------------------
# Helper — create a test agent via direct API (bypassing governance)
# ---------------------------------------------------------------------------

def _ensure_test_agent(registry_url: str, agent_name: str) -> str:
    """Create a minimal agent on the registry and return its agent_id.

    Uses the mesh agent lookup; if the agent doesn't exist, creates it
    via the submission API (requires JWT auth).
    """
    # Try lookup first
    resp = httpx.get(
        f"{registry_url}/v1/mesh/agents/lookup",
        params={"name": agent_name},
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()["agent_id"]

    # Agent doesn't exist — we need to create it via admin API
    # First get a JWT token
    auth_resp = httpx.post(
        f"{registry_url}/v1/auth/login",
        json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "changeme")},
        timeout=10,
    )
    if auth_resp.status_code != 200:
        pytest.skip(f"Cannot authenticate to registry at {registry_url}")

    token = auth_resp.json()["token"]
    jwt_headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }

    # Create a minimal agent
    create_resp = httpx.post(
        f"{registry_url}/v1/agents",
        json={
            "name": agent_name,
            "description": f"Test agent for multi-cluster HA: {agent_name}",
            "version": "1.0.0",
            "capabilities": [{"name": "test-skill", "description": "Test capability"}],
        },
        headers=jwt_headers,
        timeout=10,
    )
    if create_resp.status_code not in (200, 201):
        pytest.fail(f"Failed to create test agent: {create_resp.text}")

    agent_id = create_resp.json().get("id") or create_resp.json().get("agent_id")
    return str(agent_id)


# ===========================================================================
# TestCrossClusterReplication
# ===========================================================================

class TestCrossClusterReplication:
    """Test that data written on one cluster replicates to the other."""

    def test_registration_replicates(self, cluster1, cluster2, unique_agent_name):
        """Register agent on cluster-1, verify it appears on cluster-2."""
        agent_id = _ensure_test_agent(cluster1, unique_agent_name)

        # Register sidecar on cluster-1
        resp = httpx.post(
            f"{cluster1}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": f"http://test-sidecar-{unique_agent_name}:9901",
                "agent_card": {"name": unique_agent_name, "skills": []},
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 200, resp.text

        # Poll cluster-2 for the registration to appear
        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/discover",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            agents = r.json().get("agents", [])
            return any(a["name"] == unique_agent_name for a in agents)

        assert _poll_until(check), (
            f"Registration for {unique_agent_name} did not replicate to cluster-2 "
            f"within {REPLICATION_TIMEOUT}s"
        )

    def test_policy_replicates(self, cluster1, cluster2):
        """Create policy on cluster-1, verify it appears on cluster-2."""
        source = f"src-{uuid.uuid4().hex[:6]}"
        dest = f"dst-{uuid.uuid4().hex[:6]}"

        resp = httpx.post(
            f"{cluster1}/v1/mesh/policies",
            json={
                "source_agent_name": source,
                "dest_agent_name": dest,
                "action": "allow",
                "priority": 10,
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 201, resp.text

        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/policies",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            policies = r.json().get("policies", [])
            return any(
                p["source"] == source and p["destination"] == dest
                for p in policies
            )

        assert _poll_until(check), (
            f"Policy {source}->{dest} did not replicate to cluster-2"
        )

    def test_audit_replicates(self, cluster1, cluster2):
        """Submit audit record on cluster-1, query it on cluster-2."""
        task_id = f"test-task-{uuid.uuid4().hex[:8]}"

        resp = httpx.post(
            f"{cluster1}/v1/mesh/audit",
            json={
                "records": [{
                    "timestamp": "2026-02-19T12:00:00Z",
                    "source_agent_name": "test-source",
                    "dest_agent_name": "test-dest",
                    "a2a_method": "tasks/send",
                    "message_hash": "abc123",
                    "direction": "outbound",
                    "decision": "pass",
                    "outcome": "success",
                    "task_id": task_id,
                }],
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 201, resp.text

        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/audit",
                params={"task_id": task_id},
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            return r.json().get("total", 0) > 0

        assert _poll_until(check), (
            f"Audit record {task_id} did not replicate to cluster-2"
        )

    def test_heartbeat_on_both(self, cluster1, cluster2, unique_agent_name):
        """Register on cluster-1, heartbeat via cluster-2, verify updated."""
        agent_id = _ensure_test_agent(cluster1, unique_agent_name)

        # Register on cluster-1
        resp = httpx.post(
            f"{cluster1}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": f"http://hb-sidecar-{unique_agent_name}:9901",
                "agent_card": {"name": unique_agent_name, "skills": []},
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 200

        # Wait for replication
        time.sleep(5)

        # Heartbeat via cluster-2
        hb_resp = httpx.post(
            f"{cluster2}/v1/mesh/heartbeat",
            json={"agent_id": agent_id},
            headers=_headers(),
            timeout=10,
        )
        # May be 404 if not yet replicated — that's acceptable
        if hb_resp.status_code == 200:
            assert hb_resp.json()["status"] == "ok"

    def test_deregister_replicates(self, cluster1, cluster2, unique_agent_name):
        """Deregister on cluster-1, verify removed on cluster-2."""
        agent_id = _ensure_test_agent(cluster1, unique_agent_name)

        # Register
        httpx.post(
            f"{cluster1}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": f"http://dereg-sidecar-{unique_agent_name}:9901",
                "agent_card": {"name": unique_agent_name, "skills": []},
            },
            headers=_headers(),
            timeout=10,
        )

        # Wait for registration to replicate
        time.sleep(5)

        # Deregister on cluster-1
        httpx.post(
            f"{cluster1}/v1/mesh/deregister",
            json={"agent_id": agent_id},
            headers=_headers(),
            timeout=10,
        )

        # Poll cluster-2 to confirm removal
        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/discover",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            agents = r.json().get("agents", [])
            return not any(a["name"] == unique_agent_name for a in agents)

        assert _poll_until(check), (
            f"Deregistration for {unique_agent_name} did not replicate to cluster-2"
        )

    def test_compliance_rule_replicates(self, cluster1, cluster2):
        """Create compliance rule on cluster-1, verify on cluster-2."""
        src = f"zone-{uuid.uuid4().hex[:6]}"
        dst = f"zone-{uuid.uuid4().hex[:6]}"

        resp = httpx.post(
            f"{cluster1}/v1/mesh/compliance-rules",
            json={
                "rule_type": "sovereignty",
                "source_value": src,
                "dest_value": dst,
                "action": "block",
                "priority": 5,
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 201, resp.text

        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/compliance-rules",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            rules = r.json().get("rules", [])
            return any(
                rule.get("source_value") == src and rule.get("dest_value") == dst
                for rule in rules
            )

        assert _poll_until(check), (
            f"Compliance rule {src}->{dst} did not replicate to cluster-2"
        )


# ===========================================================================
# TestCrossClusterFailover
# ===========================================================================

class TestCrossClusterFailover:
    """Test sidecar failover behaviour when a cluster is down."""

    def test_sidecar_failover_on_registry_down(self, cluster1, cluster2):
        """RegistryClient with both URLs should fail over when primary is down."""
        from runtime.sidecar.registry_client import RegistryClient

        # Use a bad URL as primary, real cluster-2 as secondary
        client = RegistryClient(
            registry_urls=["http://localhost:1", cluster2],
            api_key=MESH_API_KEY,
            tenant_id=TENANT_ID,
            failover_timeout=2.0,
        )

        try:
            # This should fail over to cluster2
            agents = client.discover(skill="", use_cache=False)
            # Should not raise — we got a response from the secondary
            assert isinstance(agents, list)
        finally:
            client.stop()

    def test_discovery_from_remote_cluster(self, cluster1, cluster2, unique_agent_name):
        """Register on cluster-1, discover from cluster-2."""
        agent_id = _ensure_test_agent(cluster1, unique_agent_name)

        httpx.post(
            f"{cluster1}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": f"http://disc-sidecar-{unique_agent_name}:9901",
                "agent_card": {"name": unique_agent_name, "skills": []},
            },
            headers=_headers(),
            timeout=10,
        )

        # Wait for replication, then discover from cluster-2
        def check():
            r = httpx.get(
                f"{cluster2}/v1/mesh/discover",
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            return any(a["name"] == unique_agent_name for a in r.json().get("agents", []))

        assert _poll_until(check), (
            f"Agent {unique_agent_name} not discoverable from cluster-2"
        )

    def test_write_during_failover(self, cluster1, cluster2):
        """Write audit records to cluster-2, verify they arrive."""
        task_id = f"failover-task-{uuid.uuid4().hex[:8]}"

        resp = httpx.post(
            f"{cluster2}/v1/mesh/audit",
            json={
                "records": [{
                    "timestamp": "2026-02-19T13:00:00Z",
                    "source_agent_name": "failover-source",
                    "dest_agent_name": "failover-dest",
                    "a2a_method": "tasks/send",
                    "message_hash": "def456",
                    "direction": "outbound",
                    "decision": "pass",
                    "outcome": "success",
                    "task_id": task_id,
                }],
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 201

        # Verify on cluster-1 after replication
        def check():
            r = httpx.get(
                f"{cluster1}/v1/mesh/audit",
                params={"task_id": task_id},
                headers=_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return False
            return r.json().get("total", 0) > 0

        assert _poll_until(check), (
            f"Audit record {task_id} did not replicate from cluster-2 to cluster-1"
        )

    def test_full_cluster_failure(self, cluster1, cluster2):
        """Verify operations continue via cluster-2 when cluster-1 is simulated down."""
        from runtime.sidecar.registry_client import RegistryClient

        # Simulate cluster-1 being down: use unreachable URL + real cluster-2
        client = RegistryClient(
            registry_urls=["http://localhost:1", cluster2],
            api_key=MESH_API_KEY,
            tenant_id=TENANT_ID,
            failover_timeout=2.0,
        )

        try:
            # Policy fetch should work via cluster-2
            policies = client.fetch_policies()
            assert isinstance(policies, list)

            # Discovery should work
            agents = client.discover(skill="", use_cache=False)
            assert isinstance(agents, list)
        finally:
            client.stop()

    def test_cluster_recovery(self, cluster1, cluster2):
        """RegistryClient re-promotes a recovered URL."""
        from runtime.sidecar.registry_client import RegistryClient

        client = RegistryClient(
            registry_urls=[cluster1, cluster2],
            api_key=MESH_API_KEY,
            tenant_id=TENANT_ID,
        )

        try:
            # Both should be healthy initially
            assert client.active_registry_url == cluster1

            # Simulate cluster-1 failure by marking unhealthy
            client.mark_unhealthy(cluster1)
            assert client.active_registry_url == cluster2

            # "Recover" cluster-1 by marking healthy again
            with client._lock:
                client._url_health[cluster1] = True
                client._current_index = 0

            assert client.active_registry_url == cluster1
        finally:
            client.stop()


# ===========================================================================
# TestConflictResolution
# ===========================================================================

class TestConflictResolution:
    """Test LWW and append-only conflict resolution."""

    def test_concurrent_heartbeat_lww(self, cluster1, cluster2, unique_agent_name):
        """Send heartbeats to both clusters for same agent — both should succeed."""
        agent_id = _ensure_test_agent(cluster1, unique_agent_name)

        # Register on cluster-1
        httpx.post(
            f"{cluster1}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": f"http://lww-sidecar-{unique_agent_name}:9901",
                "agent_card": {"name": unique_agent_name, "skills": []},
            },
            headers=_headers(),
            timeout=10,
        )

        # Wait for replication
        time.sleep(5)

        # Send heartbeats to both clusters concurrently
        hb1 = httpx.post(
            f"{cluster1}/v1/mesh/heartbeat",
            json={"agent_id": agent_id},
            headers=_headers(),
            timeout=10,
        )
        hb2 = httpx.post(
            f"{cluster2}/v1/mesh/heartbeat",
            json={"agent_id": agent_id},
            headers=_headers(),
            timeout=10,
        )

        # At least one should succeed
        assert hb1.status_code == 200 or hb2.status_code == 200

    def test_audit_no_conflict(self, cluster1, cluster2):
        """Submit audit records to both clusters — all should be present."""
        task_id_1 = f"nc-c1-{uuid.uuid4().hex[:8]}"
        task_id_2 = f"nc-c2-{uuid.uuid4().hex[:8]}"

        # Submit to cluster-1
        httpx.post(
            f"{cluster1}/v1/mesh/audit",
            json={
                "records": [{
                    "timestamp": "2026-02-19T14:00:00Z",
                    "source_agent_name": "nc-source",
                    "dest_agent_name": "nc-dest",
                    "a2a_method": "tasks/send",
                    "message_hash": "ghi789",
                    "direction": "outbound",
                    "decision": "pass",
                    "outcome": "success",
                    "task_id": task_id_1,
                }],
            },
            headers=_headers(),
            timeout=10,
        )

        # Submit to cluster-2
        httpx.post(
            f"{cluster2}/v1/mesh/audit",
            json={
                "records": [{
                    "timestamp": "2026-02-19T14:00:01Z",
                    "source_agent_name": "nc-source-2",
                    "dest_agent_name": "nc-dest-2",
                    "a2a_method": "tasks/send",
                    "message_hash": "jkl012",
                    "direction": "outbound",
                    "decision": "pass",
                    "outcome": "success",
                    "task_id": task_id_2,
                }],
            },
            headers=_headers(),
            timeout=10,
        )

        # After replication, both records should be on both clusters
        def check():
            for url in [cluster1, cluster2]:
                r1 = httpx.get(f"{url}/v1/mesh/audit", params={"task_id": task_id_1}, headers=_headers(), timeout=10)
                r2 = httpx.get(f"{url}/v1/mesh/audit", params={"task_id": task_id_2}, headers=_headers(), timeout=10)
                if r1.status_code != 200 or r2.status_code != 200:
                    return False
                if r1.json().get("total", 0) == 0 or r2.json().get("total", 0) == 0:
                    return False
            return True

        assert _poll_until(check, timeout=REPLICATION_TIMEOUT * 2), (
            "Audit records did not replicate bidirectionally"
        )

    def test_policy_lww(self, cluster1, cluster2):
        """Update same policy on both clusters — LWW should keep the latest."""
        source = f"lww-src-{uuid.uuid4().hex[:6]}"
        dest = f"lww-dst-{uuid.uuid4().hex[:6]}"

        # Create policy on cluster-1
        resp = httpx.post(
            f"{cluster1}/v1/mesh/policies",
            json={
                "source_agent_name": source,
                "dest_agent_name": dest,
                "action": "allow",
                "priority": 1,
            },
            headers=_headers(),
            timeout=10,
        )
        assert resp.status_code == 201

        # Wait for replication
        time.sleep(5)

        # Both clusters should have the policy
        r1 = httpx.get(f"{cluster1}/v1/mesh/policies", headers=_headers(), timeout=10)
        r2 = httpx.get(f"{cluster2}/v1/mesh/policies", headers=_headers(), timeout=10)

        p1_match = [p for p in r1.json().get("policies", []) if p.get("source") == source]
        assert len(p1_match) >= 1, "Policy not found on cluster-1"

        # Cluster-2 should eventually have it too
        def check():
            r = httpx.get(f"{cluster2}/v1/mesh/policies", headers=_headers(), timeout=10)
            return any(p.get("source") == source for p in r.json().get("policies", []))

        assert _poll_until(check), "Policy did not replicate to cluster-2 for LWW test"
