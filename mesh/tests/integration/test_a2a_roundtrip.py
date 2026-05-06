"""Integration tests: real A2A roundtrip through K8s-deployed sidecars and agents.

Uses the K8s-deployed agent-a (Research Assistant) and agent-b (Fact Checker)
with their auto-injected sidecars. No local Flask servers are spawned.
Agents use their built-in fallback logic (no LLM API keys needed).

Test topology (all in K8s):
    Client -> Sidecar B -> Agent B
    Client -> Sidecar A -> Agent A -> Sidecar A /a2a/send -> Sidecar B -> Agent B

Runs inside the registry pod (pure HTTP, no sidecar library imports).
URLs come from env vars set by the test runner.
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
AGENT_A_URL = os.environ.get("AGENT_A_URL", "http://127.0.0.1:5010")
AGENT_B_URL = os.environ.get("AGENT_B_URL", "http://127.0.0.1:5011")
SIDECAR_A_URL = os.environ.get("SIDECAR_A_URL", "http://127.0.0.1:9901")
SIDECAR_B_URL = os.environ.get("SIDECAR_B_URL", "http://127.0.0.1:9902")


# ---------------------------------------------------------------------------
# Skip if agents not reachable
# ---------------------------------------------------------------------------
def _agents_reachable() -> bool:
    """Check if the K8s agents are reachable."""
    for url in [AGENT_A_URL, AGENT_B_URL, SIDECAR_A_URL, SIDECAR_B_URL]:
        try:
            path = "/health" if "5010" in url or "5011" in url else "/healthz"
            resp = httpx.get(f"{url}{path}", timeout=5.0)
            if resp.status_code != 200:
                return False
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
    return True


pytestmark = pytest.mark.skipif(
    not _agents_reachable(),
    reason="K8s agents not reachable (agent-a, agent-b, sidecar-a, sidecar-b)",
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


def _a2a_request(sidecar_url: str, text: str, timeout: float = 30.0) -> dict:
    """Send an A2A message/send to a sidecar and return the JSON response."""
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
    with httpx.Client(timeout=timeout) as c:
        resp = c.post(f"{sidecar_url}/a2a", json=payload)
    return resp.json()


def _outbound_request(
    sidecar_url: str,
    skill: str,
    message: str,
    dest_url: str | None = None,
    dest_name: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Send an outbound A2A request via a sidecar's /a2a/send."""
    payload: dict = {"skill": skill, "message": message}
    if dest_url:
        payload["destination_url"] = dest_url
    if dest_name:
        payload["destination_agent_name"] = dest_name
    with httpx.Client(timeout=timeout) as c:
        resp = c.post(f"{sidecar_url}/a2a/send", json=payload)
    return resp.json()


# ===========================================================================
# Tests: Agent health
# ===========================================================================

class TestAgentHealth:
    def test_agent_b_health(self):
        with httpx.Client() as c:
            resp = c.get(f"{AGENT_B_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["agent"] == "fact-checker"

    def test_agent_a_health(self):
        with httpx.Client() as c:
            resp = c.get(f"{AGENT_A_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["agent"] == "research-assistant"


# ===========================================================================
# Tests: Sidecar health and agent card
# ===========================================================================

class TestSidecarEndpoints:
    def test_sidecar_b_healthz(self):
        with httpx.Client() as c:
            resp = c.get(f"{SIDECAR_B_URL}/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_sidecar_a_healthz(self):
        with httpx.Client() as c:
            resp = c.get(f"{SIDECAR_A_URL}/healthz")
        assert resp.status_code == 200

    def test_sidecar_b_agent_card(self):
        with httpx.Client() as c:
            resp = c.get(f"{SIDECAR_B_URL}/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "Fact Checker Agent"
        assert any(s["id"] == "fact-check" for s in card["skills"])

    def test_sidecar_a_agent_card(self):
        with httpx.Client() as c:
            resp = c.get(f"{SIDECAR_A_URL}/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "Research Assistant"


# ===========================================================================
# Tests: Inbound A2A through Sidecar B -> Agent B
# ===========================================================================

class TestInboundRoundtrip:
    """Verify that messages reach Agent B through the mesh.

    Uses sidecar-a's outbound /a2a/send to route to sidecar-b via
    skill-based discovery, which tests the full mesh path including
    mTLS authentication between sidecars."""

    def test_message_reaches_agent_b(self):
        """Sidecar A outbound -> Sidecar B inbound -> Agent B -> response."""
        data = _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="The Eiffel Tower is 330 metres tall",
        )

        assert "result" in data, f"Expected result, got: {data}"
        assert data["result"]["status"] == "completed"
        text = data["result"]["artifacts"][0]["text"]
        assert "Eiffel Tower" in text

    def test_different_query_reaches_agent_b(self):
        data = _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="Humans landed on the Moon in 1969",
        )

        text = data["result"]["artifacts"][0]["text"]
        assert "Moon" in text

    def test_agent_b_responds_to_science_claim(self):
        """Agent B produces a response that references the claim topic."""
        data = _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="The speed of light is 300000 km/s",
        )

        text = data["result"]["artifacts"][0]["text"]
        assert "light" in text.lower() or "speed" in text.lower()

    def test_audit_records_created(self):
        """After a request through the mesh, audit records should exist."""
        _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="Test audit roundtrip",
        )

        import time
        time.sleep(2)

        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 10},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1


# ===========================================================================
# Tests: Outbound — Sidecar A sends to Sidecar B
# ===========================================================================

class TestOutboundSidecarToSidecar:
    """Agent A uses its sidecar's /a2a/send endpoint to forward a fact-check
    request to Sidecar B via skill-based discovery through the registry.

    This is the core mesh test: Sidecar A -> Sidecar B -> Agent B -> response
    propagating back through both sidecars."""

    def test_outbound_fact_check_reaches_agent_b(self):
        """POST /a2a/send on Sidecar A with skill=fact-check."""
        data = _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="The Great Wall of China is visible from space",
        )

        assert data.get("result", {}).get("status") == "completed"
        text = data["result"]["artifacts"][0]["text"]
        assert "Great Wall" in text or "China" in text

    def test_outbound_returns_structured_response(self):
        """The response from Agent B should contain the claim topic."""
        data = _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="Water boils at 100 degrees Celsius",
        )

        text = data["result"]["artifacts"][0]["text"]
        assert "100" in text or "boil" in text.lower()

    def test_outbound_audit_on_both_sides(self):
        """After an outbound A2A call, audit records should exist in the registry
        for both outbound (sidecar-a) and inbound (sidecar-b) directions."""
        _outbound_request(
            SIDECAR_A_URL,
            skill="fact-check",
            message="Audit trail test message",
        )

        # Give audit records a moment to flush
        import time
        time.sleep(2)

        # Query audit API for recent records
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 50},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]

        # Should have both outbound and inbound records
        outbound = [r for r in records if r.get("direction") == "outbound"]
        inbound = [r for r in records if r.get("direction") == "inbound"]
        assert len(outbound) >= 1, "No outbound audit records found"
        assert len(inbound) >= 1, "No inbound audit records found"


# ===========================================================================
# Tests: Auth enforcement on deployed sidecars
# ===========================================================================

class TestAuthEnforcement:
    """Verify that the K8s-deployed sidecars enforce authentication."""

    def test_unauthenticated_inbound_rejected(self):
        """A2A request to Sidecar B without mTLS or API key is rejected.

        The sidecar's auth interceptor requires valid credentials (mTLS
        client cert or API key) for inbound requests. Requests from outside
        the pod without credentials should be blocked."""
        payload = {
            "jsonrpc": "2.0", "id": "auth-test-1", "method": "message/send",
            "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": "test"}]}},
        }
        with httpx.Client(timeout=10.0) as c:
            resp = c.post(f"{SIDECAR_B_URL}/a2a", json=payload)
        # Auth interceptor rejects unauthenticated inbound requests
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {resp.status_code}"
        )
