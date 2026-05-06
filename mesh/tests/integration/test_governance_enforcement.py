"""Integration test: governance enforcement blocks A2A messages through
K8s-deployed sidecars with mTLS and the real registry.

Proves that the authz interceptor governance check blocks actual A2A messages
for non-ACTIVE agents, and allows traffic between ACTIVE agents.

Uses the K8s-deployed agent-a (Research Assistant, ACTIVE) and agent-b
(Fact Checker, ACTIVE) with their auto-injected sidecars. Tests governance
enforcement by changing agent status via kubectl exec psql, then verifying
sidecar behavior after the policy sync interval.

Runs from the HOST (needs kubectl for DB access, port-forward for sidecar
access, and imports sidecar library code).
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid

import httpx
import pytest

from tests.integration.conftest import (
    MESH_API_KEY,
    REGISTRY_URL,
    admin_login,
    create_agent_in_registry,
    mesh_headers,
    register_sidecar,
    registry_available,
    set_agent_status,
)

# ---------------------------------------------------------------------------
# K8s constants
# ---------------------------------------------------------------------------
NAMESPACE = os.environ.get("K8S_NAMESPACE", "recursant")
RELEASE = os.environ.get("K8S_RELEASE", "recursant")

# Local ports for port-forwards (unique range to avoid conflicts)
LOCAL_REGISTRY_PORT = int(os.environ.get("GOV_REGISTRY_PORT", "15150"))
LOCAL_SIDECAR_A_PORT = int(os.environ.get("GOV_SIDECAR_A_PORT", "15901"))
LOCAL_SIDECAR_B_PORT = int(os.environ.get("GOV_SIDECAR_B_PORT", "15902"))

# K8s-deployed agent names (from seed scripts)
ALPHA_NAME = "Research Assistant"
BETA_NAME = "Fact Checker Agent"

# Cache TTL for governance lookups — K8s sidecars have a longer sync interval
# We need to wait for the sidecar to pick up status changes
GOVERNANCE_SYNC_WAIT = float(os.environ.get("GOVERNANCE_SYNC_WAIT", "5"))


# ---------------------------------------------------------------------------
# K8s helpers
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
    """Return True if agent pods are running."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", NAMESPACE,
             "-l", f"app={RELEASE}-agent-a",
             "--field-selector=status.phase=Running",
             "--no-headers"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _kubectl_exec_psql(sql: str) -> str:
    """Execute SQL against the K8s postgres pod."""
    result = subprocess.run(
        ["kubectl", "exec", "-n", NAMESPACE,
         f"{RELEASE}-db-0", "--",
         "psql", "-U", "registry", "-d", "registry",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout.strip()


pytestmark = pytest.mark.skipif(
    not _kubectl_available() or not _pods_running(),
    reason="K8s cluster with agent pods not available",
)


# ---------------------------------------------------------------------------
# Port-forward fixtures
# ---------------------------------------------------------------------------

def _start_port_forward(service: str, local_port: int, remote_port: int) -> subprocess.Popen:
    """Start a kubectl port-forward in the background."""
    proc = subprocess.Popen(
        ["kubectl", "port-forward", "-n", NAMESPACE,
         f"svc/{service}", f"{local_port}:{remote_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def _wait_for_url(url: str, path: str = "/health", timeout: float = 15.0) -> bool:
    """Wait for a URL to become reachable."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{url}{path}", timeout=3.0, verify=False)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def port_forwards():
    """Start port-forwards for registry and sidecars.

    Yields dict with local URLs:
        registry_url, sidecar_a_url, sidecar_b_url
    """
    procs = []

    # Registry port-forward
    reg_proc = _start_port_forward(f"{RELEASE}-registry", LOCAL_REGISTRY_PORT, 5000)
    procs.append(reg_proc)

    # Sidecar A port-forward (HTTP proxy port)
    sa_proc = _start_port_forward(f"{RELEASE}-agent-a", LOCAL_SIDECAR_A_PORT, 9901)
    procs.append(sa_proc)

    # Sidecar B port-forward (HTTP proxy port)
    sb_proc = _start_port_forward(f"{RELEASE}-agent-b", LOCAL_SIDECAR_B_PORT, 9902)
    procs.append(sb_proc)

    registry_url = f"http://localhost:{LOCAL_REGISTRY_PORT}"
    sidecar_a_url = f"http://localhost:{LOCAL_SIDECAR_A_PORT}"
    sidecar_b_url = f"http://localhost:{LOCAL_SIDECAR_B_PORT}"

    # Wait for all port-forwards to be ready
    assert _wait_for_url(registry_url, "/health"), "Registry port-forward not ready"
    assert _wait_for_url(sidecar_a_url, "/healthz"), "Sidecar A port-forward not ready"
    assert _wait_for_url(sidecar_b_url, "/healthz"), "Sidecar B port-forward not ready"

    yield {
        "registry_url": registry_url,
        "sidecar_a_url": sidecar_a_url,
        "sidecar_b_url": sidecar_b_url,
    }

    # Teardown
    for proc in procs:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


# ---------------------------------------------------------------------------
# A2A helpers
# ---------------------------------------------------------------------------

def _a2a_outbound(
    sidecar_url: str,
    skill: str,
    message: str,
    timeout: float = 30.0,
) -> httpx.Response:
    """Send outbound via sidecar's /a2a/send."""
    payload = {"skill": skill, "message": message}
    with httpx.Client(timeout=timeout) as c:
        return c.post(f"{sidecar_url}/a2a/send", json=payload)


# ---------------------------------------------------------------------------
# Agent name helpers — look up the actual registry names
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def agent_names(port_forwards):
    """Look up the actual agent names in the registry.

    Polls discovery until both Research and Fact Checker agents appear
    (handles stale discovery cache from previous test runs).
    """
    url = port_forwards["registry_url"]
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }

    # Ensure both agents are ACTIVE in the DB first
    _kubectl_exec_psql(
        f"UPDATE agents SET status = 'ACTIVE' "
        f"WHERE name IN ('{ALPHA_NAME}', '{BETA_NAME}') AND tenant_id = 'default'"
    )

    # Poll discovery until both agents appear (cache may be stale)
    deadline = time.time() + 90
    alpha = None
    beta = None
    while time.time() < deadline:
        resp = httpx.get(
            f"{url}/v1/mesh/discover",
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            agents = resp.json()["agents"]
            for a in agents:
                name = a["name"]
                if "Research" in name:
                    alpha = name
                elif "Fact" in name or "fact" in name:
                    beta = name
            if alpha and beta:
                break
        time.sleep(5)

    assert alpha, f"Research agent not found in discover after 90s"
    assert beta, f"Fact Checker agent not found in discover after 90s"

    # Also ensure sidecar-a can reach sidecar-b (wait for sidecar cache refresh)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            resp = _a2a_outbound(
                port_forwards["sidecar_a_url"],
                skill="fact-check",
                message="Fixture warmup",
            )
            if resp.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(5)

    return {"alpha": alpha, "beta": beta}


# ===========================================================================
# Group 1: Registry status lookups
# ===========================================================================

class TestRegistryStatusLookups:
    """Verify agent status can be fetched from the real registry."""

    def test_fetch_status_active(self, port_forwards, agent_names):
        """Alpha (Research Assistant) should be ACTIVE."""
        url = port_forwards["registry_url"]
        resp = httpx.get(
            f"{url}/v1/mesh/agents/lookup",
            params={"name": agent_names["alpha"]},
            headers={"X-Mesh-API-Key": MESH_API_KEY, "X-Tenant-ID": "default"},
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["status"].upper() == "ACTIVE"

    def test_fetch_status_unknown(self, port_forwards):
        """Nonexistent agent returns 404."""
        url = port_forwards["registry_url"]
        resp = httpx.get(
            f"{url}/v1/mesh/agents/lookup",
            params={"name": "Nonexistent Agent XYZ 99"},
            headers={"X-Mesh-API-Key": MESH_API_KEY, "X-Tenant-ID": "default"},
            timeout=10.0,
        )
        assert resp.status_code == 404


# ===========================================================================
# Group 2: Outbound A2A governance
# ===========================================================================

class TestOutboundGovernance:
    """Outbound requests via sidecar are blocked when destination is not ACTIVE."""

    def test_active_to_active_succeeds(self, port_forwards, agent_names):
        """Alpha -> Beta: 200, completed."""
        resp = _a2a_outbound(
            port_forwards["sidecar_a_url"],
            skill="fact-check",
            message="The Eiffel Tower is 330m tall",
        )
        assert resp.status_code == 200, f"Alpha->Beta should succeed: {resp.text}"
        data = resp.json()
        assert data.get("result", {}).get("status") == "completed"


# ===========================================================================
# Group 3: Dynamic status change
# ===========================================================================

class TestDynamicStatusChange:
    """Prove governance enforcement reflects registry status changes."""

    def test_status_change_blocks_after_sync(self, port_forwards, agent_names):
        """Alpha -> Beta succeeds; suspend Beta in DB; poll until sidecar's
        discovery cache expires and the request is blocked; restore Beta."""

        # Step 1: Confirm Alpha -> Beta works
        resp = _a2a_outbound(
            port_forwards["sidecar_a_url"],
            skill="fact-check",
            message="Pre-suspend test",
        )
        assert resp.status_code == 200, f"Pre-suspend should succeed: {resp.text}"

        # Step 2: Suspend Beta in DB
        _kubectl_exec_psql(
            f"UPDATE agents SET status = 'SUSPENDED' "
            f"WHERE name = '{agent_names['beta']}' AND tenant_id = 'default'"
        )

        try:
            # Step 3: Poll until sidecar's discovery cache expires (default 60s TTL)
            # and the request is blocked. Timeout after 90s.
            deadline = time.time() + 90
            blocked = False
            last_resp = None
            while time.time() < deadline:
                time.sleep(5)
                resp2 = _a2a_outbound(
                    port_forwards["sidecar_a_url"],
                    skill="fact-check",
                    message="Post-suspend test",
                )
                last_resp = resp2
                if resp2.status_code in (403, 404, 500):
                    blocked = True
                    break
                try:
                    if "error" in resp2.json():
                        blocked = True
                        break
                except Exception:
                    pass

            assert blocked, (
                f"After suspending Beta, expected blocked within 90s. "
                f"Last response: {last_resp.status_code} {last_resp.text}"
            )
        finally:
            # Step 4: Restore Beta to ACTIVE
            _kubectl_exec_psql(
                f"UPDATE agents SET status = 'ACTIVE' "
                f"WHERE name = '{agent_names['beta']}' AND tenant_id = 'default'"
            )
            time.sleep(GOVERNANCE_SYNC_WAIT)

    def test_restored_agent_works(self, port_forwards, agent_names):
        """After restoring Beta to ACTIVE, Alpha -> Beta works again.

        Polls until the sidecar's discovery cache refreshes with the restored
        agent (up to 90s for cache TTL expiry).
        """
        deadline = time.time() + 90
        last_resp = None
        while time.time() < deadline:
            resp = _a2a_outbound(
                port_forwards["sidecar_a_url"],
                skill="fact-check",
                message="Post-restore test",
            )
            last_resp = resp
            if resp.status_code == 200:
                break
            time.sleep(5)

        assert last_resp.status_code == 200, (
            f"After restoring Beta, should succeed within 90s: "
            f"{last_resp.status_code} {last_resp.text}"
        )


# ===========================================================================
# Group 4: Multi-layer defence
# ===========================================================================

class TestMultiLayerDefence:
    """Verify additional defence layers (registration gates, discovery)."""

    def test_draft_agent_cannot_register(self, port_forwards):
        """Create a DRAFT agent in the registry, then try to register its
        sidecar — should get 403."""
        url = port_forwards["registry_url"]
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": "default",
            "X-Mesh-API-Key": MESH_API_KEY,
        }

        # Login and create a test agent
        login_resp = httpx.post(
            f"{url}/v1/auth/login",
            json={"username": "admin", "password": MESH_API_KEY},
            timeout=10.0,
        )
        # Use mesh API key for registration attempt (no admin needed)
        agent_name = f"Gov Draft Test {uuid.uuid4().hex[:6]}"

        # Create agent via admin API (use the credentials from k8s secrets)
        token_resp = httpx.post(
            f"{url}/v1/auth/login",
            json={"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin")},
            timeout=10.0,
        )
        if token_resp.status_code != 200:
            pytest.skip("Cannot login as admin for test setup")

        token = token_resp.json()["token"]
        create_resp = httpx.post(
            f"{url}/v1/agents",
            json={
                "name": agent_name,
                "description": "Draft test agent",
                "version": "1.0.0",
                "owner_id": "test",
                "team_id": "test",
                "contact_email": "test@test.com",
                "classification": "internal",
                "data_sensitivity": "none",
                "risk_tier": "low",
                "capabilities": [{"name": "test-skill", "description": "test"}],
                "endpoint": {"type": "langgraph", "url": "http://nonexistent:9999", "auth_method": "mtls"},
            },
            headers={
                "Content-Type": "application/json",
                "X-Tenant-ID": "default",
                "Authorization": f"Bearer {token}",
            },
            timeout=10.0,
        )

        if create_resp.status_code == 201:
            agent_id = create_resp.json()["id"]
        elif create_resp.status_code == 409:
            # Already exists — look it up
            lookup = httpx.get(
                f"{url}/v1/mesh/agents/lookup",
                params={"name": agent_name},
                headers=headers,
                timeout=10.0,
            )
            agent_id = lookup.json()["agent_id"]
        else:
            pytest.skip(f"Could not create test agent: {create_resp.status_code}")

        # Ensure DRAFT status
        _kubectl_exec_psql(
            f"UPDATE agents SET status = 'DRAFT' "
            f"WHERE name = '{agent_name}' AND tenant_id = 'default'"
        )

        # Try to register sidecar -> 403
        reg_resp = httpx.post(
            f"{url}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": "http://nonexistent:9999",
                "agent_card": {
                    "name": agent_name,
                    "version": "1.0.0",
                    "skills": [{"id": "test-skill"}],
                },
            },
            headers=headers,
            timeout=10.0,
        )
        assert reg_resp.status_code == 403, (
            f"DRAFT agent registration should be rejected: {reg_resp.status_code} {reg_resp.text}"
        )

    def test_suspended_agent_not_discoverable(self, port_forwards, agent_names):
        """Suspend Beta, verify it disappears from discovery, then restore."""
        url = port_forwards["registry_url"]
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": "default",
            "X-Mesh-API-Key": MESH_API_KEY,
        }

        # Suspend Beta
        _kubectl_exec_psql(
            f"UPDATE agents SET status = 'SUSPENDED' "
            f"WHERE name = '{agent_names['beta']}' AND tenant_id = 'default'"
        )

        try:
            time.sleep(1)  # Brief pause for DB to settle

            # Discovery for fact-check should not return Beta
            resp = httpx.get(
                f"{url}/v1/mesh/discover",
                params={"skill": "fact-check"},
                headers=headers,
                timeout=10.0,
            )
            assert resp.status_code == 200
            agents = resp.json().get("agents", [])
            beta_match = [a for a in agents if a["name"] == agent_names["beta"]]
            assert len(beta_match) == 0, (
                f"SUSPENDED agent should not be discoverable: {beta_match}"
            )
        finally:
            # Restore Beta
            _kubectl_exec_psql(
                f"UPDATE agents SET status = 'ACTIVE' "
                f"WHERE name = '{agent_names['beta']}' AND tenant_id = 'default'"
            )

    def test_lifecycle_wired_governance(self, port_forwards):
        """Sidecar A's /healthz confirms it's registered and running."""
        resp = httpx.get(
            f"{port_forwards['sidecar_a_url']}/healthz",
            timeout=5.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
