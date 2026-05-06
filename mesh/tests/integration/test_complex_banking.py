"""Integration test: mortgage origination mesh with K8s-deployed agents.

Tests the hub-and-spoke access control model across six mortgage agents
deployed in the K8s cluster with auto-injected sidecars.

  - Customer Service (hub) can communicate with all backend agents.
  - Backend agents CANNOT communicate with each other.
  - Audit trail is recorded in the registry.

Runs inside the registry pod (pure HTTP, no sidecar library imports).
Requires the mortgage demo to be deployed (values-mortgage.yaml).

Agent topology (all K8s services):
    Customer Service -> Auth, KYC, Credit, Core Banking, Compliance
    Auth, KYC, Credit, Core Banking, Compliance -> Customer Service (respond)
    Auth <-> KYC (BLOCKED), KYC <-> Credit (BLOCKED), etc.
"""

from __future__ import annotations

import os
import time
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

# K8s release name (used to construct service DNS names)
RELEASE = os.environ.get("K8S_RELEASE", "recursant")

# Mortgage agent URLs — built from K8s service DNS or from env vars
CUSTOMER_AGENT_URL = os.environ.get("CUSTOMER_AGENT_URL", f"http://{RELEASE}-agents-customer:5020")
CUSTOMER_SIDECAR_URL = os.environ.get("CUSTOMER_SIDECAR_URL", f"http://{RELEASE}-agents-customer:9910")
AUTH_AGENT_URL = os.environ.get("AUTH_AGENT_URL", f"http://{RELEASE}-agents-customer:5021")
AUTH_SIDECAR_URL = os.environ.get("AUTH_SIDECAR_URL", f"http://{RELEASE}-agents-customer:9911")
KYC_AGENT_URL = os.environ.get("KYC_AGENT_URL", f"http://{RELEASE}-n8n-kyc:5022")
KYC_SIDECAR_URL = os.environ.get("KYC_SIDECAR_URL", f"http://{RELEASE}-n8n-kyc:9912")
CREDIT_AGENT_URL = os.environ.get("CREDIT_AGENT_URL", f"http://{RELEASE}-agents-kyc-credit:5023")
CREDIT_SIDECAR_URL = os.environ.get("CREDIT_SIDECAR_URL", f"http://{RELEASE}-agents-kyc-credit:9913")
CORE_BANKING_AGENT_URL = os.environ.get("CORE_BANKING_AGENT_URL", f"http://{RELEASE}-agents-core-banking:5024")
CORE_BANKING_SIDECAR_URL = os.environ.get("CORE_BANKING_SIDECAR_URL", f"http://{RELEASE}-agents-core-banking:9914")
COMPLIANCE_AGENT_URL = os.environ.get("COMPLIANCE_AGENT_URL", f"http://{RELEASE}-agents-compliance:5025")
COMPLIANCE_SIDECAR_URL = os.environ.get("COMPLIANCE_SIDECAR_URL", f"http://{RELEASE}-agents-compliance:9915")

# Agent definitions for parametrized tests
AGENTS = {
    "customer": {
        "name": "Customer Agent",
        "skill": "mortgage-origination",
        "agent_url": CUSTOMER_AGENT_URL,
        "sidecar_url": CUSTOMER_SIDECAR_URL,
    },
    "auth": {
        "name": "Authentication Agent",
        "skill": "authenticate-customer",
        "agent_url": AUTH_AGENT_URL,
        "sidecar_url": AUTH_SIDECAR_URL,
    },
    "kyc": {
        "name": "KYC Agent",
        "skill": "kyc-verify",
        "agent_url": KYC_AGENT_URL,
        "sidecar_url": KYC_SIDECAR_URL,
    },
    "credit": {
        "name": "Credit Agent",
        "skill": "assess-credit-capacity",
        "agent_url": CREDIT_AGENT_URL,
        "sidecar_url": CREDIT_SIDECAR_URL,
    },
    "core-banking": {
        "name": "Core Banking Agent",
        "skill": "disburse-loan",
        "agent_url": CORE_BANKING_AGENT_URL,
        "sidecar_url": CORE_BANKING_SIDECAR_URL,
    },
    "compliance": {
        "name": "Compliance Crew",
        "skill": "compliance-review",
        "agent_url": COMPLIANCE_AGENT_URL,
        "sidecar_url": COMPLIANCE_SIDECAR_URL,
    },
}


# ---------------------------------------------------------------------------
# Skip if mortgage agents not deployed
# ---------------------------------------------------------------------------
def _mortgage_deployed() -> bool:
    """Check if the customer agent is reachable (proxy for mortgage deployment)."""
    try:
        resp = httpx.get(f"{CUSTOMER_AGENT_URL}/health", timeout=5.0)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


pytestmark = pytest.mark.skipif(
    not _mortgage_deployed(),
    reason="Mortgage agents not deployed in K8s (customer agent not reachable)",
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


def _outbound_request(
    sidecar_url: str,
    skill: str,
    message: str,
    timeout: float = 30.0,
) -> httpx.Response:
    """Send an outbound request via skill-based discovery (no destination_url).

    The sidecar discovers the destination agent from the registry.
    Returns the raw httpx.Response so callers can inspect status_code.
    """
    payload = {"skill": skill, "message": message}
    with httpx.Client(timeout=timeout) as c:
        return c.post(f"{sidecar_url}/a2a/send", json=payload)


def _exec_sql(sql: str) -> None:
    """Execute SQL via direct psycopg2 (inside registry pod) or env-based."""
    db_host = os.environ.get("REGISTRY_DB_HOST")
    if db_host:
        import psycopg2
        conn = psycopg2.connect(
            host=db_host, dbname="registry",
            user="registry", password="registry",
        )
        conn.autocommit = True
        conn.cursor().execute(sql)
        conn.close()


# ===========================================================================
# Tests
# ===========================================================================


class TestMortgageAgentHealth:
    """Verify all mortgage agents and sidecars are healthy."""

    @pytest.mark.parametrize("label", list(AGENTS.keys()))
    def test_agent_healthy(self, label):
        """Each mortgage agent responds to /health."""
        url = AGENTS[label]["agent_url"]
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{url}/health")
        assert resp.status_code == 200, (
            f"Agent {label} at {url} not healthy: {resp.status_code}"
        )

    @pytest.mark.parametrize("label", list(AGENTS.keys()))
    def test_sidecar_healthy(self, label):
        """Each sidecar responds to /healthz."""
        url = AGENTS[label]["sidecar_url"]
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{url}/healthz")
        assert resp.status_code == 200, (
            f"Sidecar {label} at {url} not healthy: {resp.status_code}"
        )

    @pytest.mark.parametrize("label", list(AGENTS.keys()))
    def test_agent_card_served(self, label):
        """Each sidecar serves an agent card."""
        url = AGENTS[label]["sidecar_url"]
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{url}/.well-known/agent.json")
        assert resp.status_code == 200, (
            f"Sidecar {label} agent card not served: {resp.status_code}"
        )
        card = resp.json()
        assert "name" in card
        assert "skills" in card


class TestHubToSpokeRouting:
    """Customer Service (hub) can reach all backend agents."""

    @pytest.mark.parametrize("dest", ["auth", "kyc", "credit", "core-banking", "compliance"])
    def test_customer_to_agent_allowed(self, dest):
        """Customer Service discovers and communicates with backend agent."""
        resp = _outbound_request(
            sidecar_url=CUSTOMER_SIDECAR_URL,
            skill=AGENTS[dest]["skill"],
            message=f"Mortgage origination: calling {AGENTS[dest]['name']}",
        )
        assert resp.status_code == 200, (
            f"Customer -> {dest} should be ALLOWED, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data.get("result", {}).get("status") == "completed", (
            f"Customer -> {dest} response not completed: {data}"
        )


class TestSpokeToSpokeBlocking:
    """Backend agents CANNOT communicate with each other (deny-all default)."""

    _SPOKE_PAIRS = [
        ("auth", "kyc"), ("auth", "credit"), ("auth", "core-banking"),
        ("kyc", "auth"), ("kyc", "credit"), ("kyc", "core-banking"),
        ("credit", "auth"), ("credit", "kyc"), ("credit", "core-banking"),
        ("core-banking", "auth"), ("core-banking", "kyc"), ("core-banking", "credit"),
    ]

    @pytest.mark.parametrize("src,dest", _SPOKE_PAIRS,
                             ids=[f"{s}->{d}" for s, d in _SPOKE_PAIRS])
    def test_spoke_to_spoke_blocked(self, src, dest):
        """Backend agent src cannot reach backend agent dest."""
        resp = _outbound_request(
            sidecar_url=AGENTS[src]["sidecar_url"],
            skill=AGENTS[dest]["skill"],
            message=f"Unauthorised: {src} -> {dest}",
        )
        assert resp.status_code == 403, (
            f"{src} -> {dest} should be BLOCKED, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data.get("blocked") is True


class TestAuditTrail:
    """Verify audit records are created for allowed and blocked calls."""

    def test_allowed_calls_produce_audit_records(self):
        """After an allowed call from Customer -> Auth, audit records exist."""
        _outbound_request(
            sidecar_url=CUSTOMER_SIDECAR_URL,
            skill=AGENTS["auth"]["skill"],
            message="Audit test: Customer -> Auth",
        )
        time.sleep(2)

        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 50},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]
        success = [r for r in records if r.get("outcome") == "success"]
        assert len(success) >= 1, "Expected success audit records"

    def test_blocked_calls_produce_audit_records(self):
        """After a blocked call from Auth -> KYC, blocked audit records exist."""
        _outbound_request(
            sidecar_url=AGENTS["auth"]["sidecar_url"],
            skill=AGENTS["kyc"]["skill"],
            message="Audit test: Auth -> KYC (should block)",
        )
        time.sleep(2)

        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"per_page": 50},
            headers=_mesh_headers(),
            timeout=10.0,
        )
        assert resp.status_code == 200
        records = resp.json()["records"]
        blocked = [r for r in records if r.get("outcome") == "blocked"]
        assert len(blocked) >= 1, "Expected blocked audit records"


class TestMortgageWorkflow:
    """End-to-end mortgage origination workflow."""

    def test_full_mortgage_origination(self):
        """Customer Service orchestrates the full workflow through all agents."""
        workflow_steps = [
            ("auth", "Verify identity for applicant Jane Doe"),
            ("kyc", "Run KYC check on applicant Jane Doe"),
            ("credit", "Assess credit risk and affordability"),
            ("core-banking", "Disburse approved loan to customer account"),
        ]

        for dest, message in workflow_steps:
            resp = _outbound_request(
                sidecar_url=CUSTOMER_SIDECAR_URL,
                skill=AGENTS[dest]["skill"],
                message=message,
            )
            assert resp.status_code == 200, (
                f"Workflow step Customer -> {dest} failed: {resp.status_code} {resp.text}"
            )
            assert resp.json().get("result", {}).get("status") == "completed"


class TestAgentSuspension:
    """Agent suspension makes the agent disappear from discovery."""

    def test_suspended_agent_not_discoverable(self):
        """Suspend an agent via DB, verify it disappears from discovery, restore."""
        agent_name = AGENTS["credit"]["name"]

        # Suspend via direct DB
        _exec_sql(
            f"UPDATE agents SET status = 'SUSPENDED' "
            f"WHERE name = '{agent_name}' AND tenant_id = 'default'"
        )

        try:
            time.sleep(1)

            # Discovery for credit-check should not return the suspended agent
            resp = httpx.get(
                f"{REGISTRY_URL}/v1/mesh/discover",
                params={"skill": AGENTS["credit"]["skill"]},
                headers=_mesh_headers(),
                timeout=10.0,
            )
            assert resp.status_code == 200
            agents = resp.json().get("agents", [])
            suspended = [a for a in agents if a["name"] == agent_name]
            assert len(suspended) == 0, (
                f"SUSPENDED agent should not be discoverable: {suspended}"
            )
        finally:
            # Restore
            _exec_sql(
                f"UPDATE agents SET status = 'ACTIVE' "
                f"WHERE name = '{agent_name}' AND tenant_id = 'default'"
            )

    def test_restored_agent_reachable(self):
        """After restoring a suspended agent, it can be reached again."""
        resp = _outbound_request(
            sidecar_url=CUSTOMER_SIDECAR_URL,
            skill=AGENTS["credit"]["skill"],
            message="Post-restore credit check",
        )
        assert resp.status_code == 200, (
            f"Restored agent should be reachable: {resp.status_code} {resp.text}"
        )
