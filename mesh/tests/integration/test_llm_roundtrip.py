"""Integration tests with real LLM calls through K8s-deployed sidecars and agents.

Uses the K8s-deployed agent-a (Research Assistant) and agent-b (Fact Checker)
which have LLM API keys from K8s secrets. No local Flask servers are spawned.

Requires at least one LLM API key available to the K8s agents.
Skipped when no key is available. Run explicitly with:

    make k8s-test-llm

Test topology (all in K8s):
    Client -> Sidecar B -> Agent B                  [fact-check with LLM]
    Client -> Sidecar A -> Agent A                  [research with LLM]
    Sidecar A /a2a/send -> Sidecar B -> Agent B     [cross-mesh via registry discovery]
"""

from __future__ import annotations

import os

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

LLM_TIMEOUT = 60.0  # LLM calls can be slow


# ---------------------------------------------------------------------------
# Determine if LLM is available
# ---------------------------------------------------------------------------
def _has_llm_key() -> bool:
    """Check if any LLM API key is available in the environment."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )


def _agents_reachable() -> bool:
    """Check if K8s agents are reachable."""
    for url in [SIDECAR_A_URL, SIDECAR_B_URL]:
        try:
            resp = httpx.get(f"{url}/healthz", timeout=5.0)
            if resp.status_code != 200:
                return False
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
    return True


NO_LLM_REASON = "no LLM API key set (need ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY)"

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(not _has_llm_key(), reason=NO_LLM_REASON),
    pytest.mark.skipif(not _agents_reachable(), reason="K8s agents not reachable"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mesh_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }


def _outbound_request(sidecar_url: str, skill: str, message: str) -> dict:
    """Send an outbound A2A request via sidecar's /a2a/send (skill-based discovery).

    All inter-agent communication must go through the outbound path, which
    handles mTLS and registry-based discovery automatically.
    """
    payload = {
        "skill": skill,
        "message": message,
    }
    with httpx.Client(timeout=LLM_TIMEOUT) as c:
        resp = c.post(f"{sidecar_url}/a2a/send", json=payload)
    return resp.json()


def _extract_text(data: dict) -> str:
    """Extract the text from an A2A response."""
    return data["result"]["artifacts"][0]["text"]


# ===========================================================================
# Tests: Agent B fact-checking with real LLM
# ===========================================================================

class TestFactCheckerLLM:
    """Verify Agent B produces real LLM-powered verdicts, not fallback text.

    Routes through Sidecar A outbound -> Sidecar B (mTLS) -> Agent B.
    """

    def test_true_claim_identified(self):
        """A true factual claim should get a TRUE verdict."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "The Eiffel Tower is located in Paris, France",
        )

        assert data["result"]["status"] == "completed"
        text = _extract_text(data).lower()
        assert "unverifiable" not in text, f"Got fallback response, LLM not active: {text}"
        assert "true" in text

    def test_false_claim_identified(self):
        """A false factual claim should get a FALSE verdict."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "The capital of Australia is Sydney",
        )

        assert data["result"]["status"] == "completed"
        text = _extract_text(data).lower()
        assert "unverifiable" not in text, f"Got fallback response, LLM not active: {text}"
        assert "false" in text
        assert "canberra" in text

    def test_verdict_includes_evidence(self):
        """The response should contain reasoning, not just a verdict label."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "Mount Everest is the tallest mountain on Earth",
        )

        text = _extract_text(data)
        assert len(text) > 50, f"Response too short to be LLM-generated: {text}"
        assert "Everest" in text

    def test_nuanced_claim_gets_analysis(self):
        """A partially true claim should get nuanced analysis."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "Lightning never strikes the same place twice",
        )

        text = _extract_text(data).lower()
        assert "unverifiable" not in text, f"Got fallback response: {text}"
        assert "false" in text


# ===========================================================================
# Tests: Agent A research with real LLM
# ===========================================================================

class TestResearchAssistantLLM:
    """Verify Agent A produces real LLM-powered research, not fallback text.

    Routes through Sidecar B outbound -> Sidecar A (mTLS) -> Agent A.
    """

    def test_generates_real_claim(self):
        """Agent A should generate a substantive claim, not 'Claim based on query:'."""
        data = _outbound_request(
            SIDECAR_B_URL, "research",
            "history of the internet",
        )

        assert data["result"]["status"] == "completed"
        text = _extract_text(data)
        assert not text.startswith("Research Summary\nQuery:"), (
            f"Got fallback response, LLM not active: {text[:100]}"
        )
        assert len(text) > 50

    def test_research_on_science_topic(self):
        """Research about a science topic should produce informed content."""
        data = _outbound_request(
            SIDECAR_B_URL, "research",
            "how do vaccines work",
        )

        text = _extract_text(data)
        assert not text.startswith("Research Summary\nQuery:"), (
            f"Got fallback response: {text[:100]}"
        )
        text_lower = text.lower()
        assert any(
            term in text_lower
            for term in ["immune", "antibod", "antigen", "pathogen", "virus", "vaccine"]
        ), f"Response doesn't seem to be about vaccines: {text[:200]}"


# ===========================================================================
# Tests: Cross-mesh with real LLM (Sidecar A -> Sidecar B -> Agent B)
# ===========================================================================

class TestCrossMeshLLM:
    """Full mesh path with real LLM responses."""

    def test_cross_mesh_fact_check(self):
        """Sidecar A -> Sidecar B -> Agent B should return a real LLM verdict."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "The Amazon River is the longest river in the world",
        )

        assert data["result"]["status"] == "completed"
        text = _extract_text(data).lower()
        assert "unverifiable" not in text, f"Got fallback response: {text}"
        assert "amazon" in text or "nile" in text or "river" in text

    def test_cross_mesh_returns_substantive_response(self):
        """Cross-mesh response should be multi-sentence LLM output."""
        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "Humans first landed on the Moon in 1969",
        )

        text = _extract_text(data)
        assert len(text) > 80, f"Response too short: {text}"
        assert "unverifiable" not in text.lower()

    def test_cross_mesh_audit_trail(self):
        """Cross-mesh LLM call should produce audit records in the registry."""
        import time

        _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "Water freezes at 0 degrees Celsius",
        )

        # Give audit records time to flush to registry
        time.sleep(3)

        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 50},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]

        outbound = [r for r in records if r.get("direction") == "outbound"]
        inbound = [r for r in records if r.get("direction") == "inbound"]

        assert len(outbound) >= 1, "No outbound audit on Sidecar A"
        assert len(inbound) >= 1, "No inbound audit on Sidecar B"


# ===========================================================================
# Tests: Full mesh end-to-end demonstration
# ===========================================================================

class TestMeshEndToEnd:
    """Full mesh demonstration: two agents on separate pods communicating
    through governed sidecars with registry-based discovery."""

    def test_registry_has_both_agents(self):
        """Both sidecars registered with the real registry."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/discover",
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        names = {a["name"] for a in resp.json()["agents"]}
        # Check for the K8s-deployed agent names
        assert any("Research" in n for n in names), f"No Research agent in {names}"
        assert any("Fact" in n or "fact" in n for n in names), f"No Fact Checker agent in {names}"

    def test_mesh_intercepts_and_delivers(self):
        """Two agents communicate through the mesh; verify LLM response
        and audit trail in the registry."""
        import time

        data = _outbound_request(
            SIDECAR_A_URL, "fact-check",
            "The Earth orbits the Sun",
        )

        # Verify Agent B produced a real LLM response
        assert data["result"]["status"] == "completed"
        response_text = _extract_text(data)
        assert len(response_text) > 20, (
            f"Response too short to be LLM-generated: {response_text}"
        )
        assert "without llm" not in response_text.lower(), (
            f"Got fallback response, LLM not active: {response_text}"
        )

        # Give audit records time to flush
        time.sleep(3)

        # Verify audit records exist in the registry
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 50},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]
        assert len(records) >= 1, "No audit records found after mesh communication"
