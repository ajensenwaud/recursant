"""Integration test: registry identity check and agent isolation.

Proves that only approved/active agents can communicate via the mesh, and
that unregistered agents are blocked at the registry level.

Uses the K8s-deployed agent-a (Research Assistant, ACTIVE) and agent-b
(Fact Checker, ACTIVE) with their auto-injected sidecars. Creates a test
agent in DRAFT status via the registry API to test rejection.

Runs inside the registry pod (pure HTTP, no sidecar library imports).
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration from env vars (set by run-integration-tests.sh)
# ---------------------------------------------------------------------------
REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:5000")
MESH_API_KEY = os.environ.get("MESH_API_KEY", "mesh-dev-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
AGENT_A_URL = os.environ.get("AGENT_A_URL", "http://127.0.0.1:5010")
AGENT_B_URL = os.environ.get("AGENT_B_URL", "http://127.0.0.1:5011")
SIDECAR_A_URL = os.environ.get("SIDECAR_A_URL", "http://127.0.0.1:9901")
SIDECAR_B_URL = os.environ.get("SIDECAR_B_URL", "http://127.0.0.1:9902")

# Registry names of the K8s-deployed agents
AGENT_A_CARD_NAME = "Research Assistant"
AGENT_B_CARD_NAME = "Fact Checker Agent"

# Name for the test DRAFT agent
DRAFT_AGENT_NAME = f"Isolation Draft Agent {uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Skip if agents not reachable
# ---------------------------------------------------------------------------
def _agents_reachable() -> bool:
    for url in [SIDECAR_A_URL, SIDECAR_B_URL]:
        try:
            resp = httpx.get(f"{url}/healthz", timeout=5.0)
            if resp.status_code != 200:
                return False
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
    return True


pytestmark = pytest.mark.skipif(
    not _agents_reachable(),
    reason="K8s agents not reachable",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mesh_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "Authorization": f"Bearer {token}",
    }


def _admin_login() -> str:
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


def _a2a_inbound(sidecar_url: str, text: str, client_cert_cn: str | None = None) -> httpx.Response:
    """Send an inbound A2A message/send to a sidecar. Returns raw response."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"req-{uuid.uuid4()}",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    headers = {}
    if client_cert_cn:
        headers["X-Client-Cert-CN"] = client_cert_cn
    with httpx.Client(timeout=10.0) as c:
        return c.post(f"{sidecar_url}/a2a", json=payload, headers=headers)


def _a2a_outbound(
    sidecar_url: str, skill: str, message: str,
) -> httpx.Response:
    """Send an outbound request via sidecar's /a2a/send (skill-based discovery)."""
    payload = {"skill": skill, "message": message}
    with httpx.Client(timeout=10.0) as c:
        return c.post(f"{sidecar_url}/a2a/send", json=payload)


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def draft_agent():
    """Create a DRAFT agent in the registry for negative tests.

    Yields (agent_id, agent_name). Agent is left in DRAFT — never approved.
    """
    token = _admin_login()
    headers = _auth_headers(token)
    payload = {
        "name": DRAFT_AGENT_NAME,
        "description": "Draft agent for isolation tests",
        "version": "1.0.0",
        "owner_id": "integration-test",
        "team_id": "integration-test",
        "contact_email": "test@recursant.ai",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [{"name": "summarise", "description": "Skill: summarise"}],
        "endpoint": {
            "type": "langgraph",
            "url": "http://nonexistent:9999/a2a",
            "auth_method": "mtls",
        },
    }
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/agents", json=payload, headers=headers, timeout=10.0,
    )
    if resp.status_code == 201:
        agent_id = resp.json()["id"]
    elif resp.status_code == 409:
        # Already exists
        lookup = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/agents/lookup",
            params={"name": DRAFT_AGENT_NAME},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        agent_id = lookup.json()["agent_id"]
    else:
        raise RuntimeError(f"Failed to create draft agent: {resp.status_code} {resp.text}")

    # Ensure it's in DRAFT status via direct DB if possible, or via env
    db_host = os.environ.get("REGISTRY_DB_HOST")
    if db_host:
        import psycopg2
        conn = psycopg2.connect(
            host=db_host, dbname="registry",
            user="registry", password="registry",
        )
        conn.autocommit = True
        conn.cursor().execute(
            f"UPDATE agents SET status = 'DRAFT' "
            f"WHERE name = '{DRAFT_AGENT_NAME}' AND tenant_id = 'default'"
        )
        conn.close()

    yield agent_id, DRAFT_AGENT_NAME


# ===========================================================================
# Test cases
# ===========================================================================


class TestApprovedAgentCommunication:
    """Agent A and B are both ACTIVE and registered — they can talk to each other."""

    def test_a_to_b_via_sidecar(self):
        """Sidecar A /a2a/send -> Sidecar B -> Agent B -> 200."""
        resp = _a2a_outbound(
            SIDECAR_A_URL,
            skill="fact-check",
            message="The Eiffel Tower is 330m tall",
        )
        assert resp.status_code == 200, f"A->B should succeed: {resp.text}"
        data = resp.json()
        assert data["result"]["status"] == "completed"

    def test_a_sidecar_health(self):
        """Sidecar A is healthy."""
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{SIDECAR_A_URL}/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_b_sidecar_health(self):
        """Sidecar B is healthy."""
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{SIDECAR_B_URL}/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_both_agents_discoverable(self):
        """Both agents appear in registry discovery."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/discover",
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        names = {a["name"] for a in resp.json()["agents"]}
        assert any("Research" in n for n in names), f"Agent A not discoverable: {names}"
        assert any("Fact" in n or "fact" in n for n in names), f"Agent B not discoverable: {names}"


class TestUnregisteredAgentBlocked:
    """A DRAFT agent cannot register or communicate via the mesh."""

    def test_draft_mesh_registration_rejected(self, draft_agent):
        """POST /v1/mesh/register for a DRAFT agent -> 403."""
        agent_id, agent_name = draft_agent
        card = {
            "name": agent_name,
            "description": "Draft summariser",
            "version": "1.0.0",
            "skills": [{"id": "summarise", "name": "Summarise"}],
        }
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/register",
            json={
                "agent_id": agent_id,
                "sidecar_url": "http://nonexistent:9999",
                "agent_card": card,
            },
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 403, (
            f"DRAFT agent registration should be rejected, got {resp.status_code}: {resp.text}"
        )

    def test_draft_not_discoverable(self, draft_agent):
        """GET /v1/mesh/discover?skill=summarise -> does not include the draft agent."""
        _, agent_name = draft_agent
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/discover",
            params={"skill": "summarise"},
            headers=_mesh_headers(),
            timeout=5.0,
        )
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        draft_matches = [a for a in agents if a["name"] == agent_name]
        assert len(draft_matches) == 0, f"DRAFT agent should not be discoverable: {draft_matches}"

    def test_a_discovers_b_not_draft(self, draft_agent):
        """Discovery for skill 'fact-check' returns B; 'summarise' returns nothing from draft."""
        _, agent_name = draft_agent
        # fact-check -> B
        resp_b = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/discover",
            params={"skill": "fact-check"},
            headers=_mesh_headers(),
            timeout=5.0,
        )
        assert resp_b.status_code == 200
        agents_b = resp_b.json()["agents"]
        assert len(agents_b) >= 1

        # summarise -> empty (draft agent not registered)
        resp_c = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/discover",
            params={"skill": "summarise"},
            headers=_mesh_headers(),
            timeout=5.0,
        )
        assert resp_c.status_code == 200
        agents_c = resp_c.json()["agents"]
        draft = [a for a in agents_c if a["name"] == agent_name]
        assert len(draft) == 0, f"Draft agent should not be discoverable: {draft}"


class TestDirectBypassPrevented:
    """Verify sidecar is the enforcement point, not the agent."""

    def test_sidecar_enforces_auth_on_inbound(self):
        """Sidecar B rejects unauthenticated inbound A2A requests.

        The sidecar requires mTLS or API key auth for inbound requests.
        Requests without credentials are blocked at the sidecar level,
        preventing direct access to the agent."""
        payload = {
            "jsonrpc": "2.0",
            "id": "direct-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Direct request"}],
                }
            },
        }
        with httpx.Client(timeout=10.0) as c:
            resp = c.post(f"{SIDECAR_B_URL}/a2a", json=payload)
        # Auth interceptor blocks unauthenticated requests
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {resp.status_code}"
        )

    def test_sidecar_blocks_spoofed_identity(self):
        """A2A request to Sidecar B with spoofed X-Client-Cert-CN of a
        non-existent agent is rejected by auth or authz interceptor."""
        resp = _a2a_inbound(SIDECAR_B_URL, "I am evil", client_cert_cn="Evil Agent")
        # Sidecar rejects: 401 (auth failed), 403 (agent not in registry),
        # or other non-200 error — all indicate the spoofed identity was blocked.
        assert resp.status_code in (401, 403), (
            f"Spoofed CN should be blocked, got {resp.status_code}: {resp.text}"
        )
