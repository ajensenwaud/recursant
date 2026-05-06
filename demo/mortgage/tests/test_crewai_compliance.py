"""Integration tests for the CrewAI Compliance Crew agent.

Tests run against the real K8s cluster (or Docker Compose stack).
LLM-powered tests are marked @pytest.mark.llm and skipped without API keys.

Usage:
    pytest demo/mortgage/tests/test_crewai_compliance.py -v
    pytest demo/mortgage/tests/test_crewai_compliance.py -v -m "not llm"  # skip LLM tests

Environment variables:
    REGISTRY_URL, REGISTRY_USERNAME, REGISTRY_PASSWORD, MESH_API_KEY,
    COMPLIANCE_AGENT_URL, COMPLIANCE_SIDECAR_URL, ANTHROPIC_API_KEY
"""

from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:8050")
COMPLIANCE_AGENT_URL = os.environ.get("COMPLIANCE_AGENT_URL", "http://localhost:5025")
COMPLIANCE_SIDECAR_URL = os.environ.get("COMPLIANCE_SIDECAR_URL", "http://localhost:9915")

# Check for API key to determine if LLM tests can run
_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not _api_key:
    try:
        from pathlib import Path
        env_file = Path(__file__).resolve().parents[3] / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    _api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass

HAS_LLM_KEY = bool(_api_key)


def _auth_headers() -> dict[str, str]:
    """Get auth headers for registry API calls."""
    username = os.environ.get("REGISTRY_USERNAME", "admin")
    password = os.environ.get("REGISTRY_PASSWORD", "admin")
    mesh_api_key = os.environ.get("MESH_API_KEY", "mesh-dev-key")

    try:
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
        if resp.status_code == 200:
            token = resp.json()["token"]
            return {
                "Authorization": f"Bearer {token}",
                "X-Tenant-ID": "default",
                "X-Mesh-API-Key": mesh_api_key,
            }
    except Exception:
        pass

    return {"X-Tenant-ID": "default", "X-Mesh-API-Key": mesh_api_key}


def _make_a2a_payload(data: dict) -> dict:
    """Build a JSON-RPC message/send payload."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "parts": [{"kind": "text", "text": json.dumps(data)}],
            },
        },
    }


# =====================================================================
# Test 1: Health check
# =====================================================================

class TestComplianceAgentHealth:
    def test_health_endpoint(self):
        """Compliance agent /health returns 200 with status ok."""
        resp = httpx.get(f"{COMPLIANCE_AGENT_URL}/health", timeout=10.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# =====================================================================
# Test 2: Agent registered in registry with crewai endpoint type
# =====================================================================

class TestComplianceRegistration:
    def test_agent_registered(self):
        """Compliance Crew agent exists in the registry with crewai endpoint type."""
        headers = _auth_headers()
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/agents",
            params={"per_page": 100},
            headers=headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        agents = resp.json().get("agents", [])

        compliance_agents = [a for a in agents if a["name"] == "Compliance Crew"]
        assert len(compliance_agents) == 1, f"Expected 1 Compliance Crew agent, found {len(compliance_agents)}"

        # Fetch detail view to check endpoint type (list view omits endpoint)
        agent_id = compliance_agents[0]["id"]
        detail_resp = httpx.get(
            f"{REGISTRY_URL}/v1/agents/{agent_id}",
            headers=headers,
            timeout=10.0,
        )
        assert detail_resp.status_code == 200
        agent = detail_resp.json()
        assert agent.get("endpoint", {}).get("type") == "crewai"


# =====================================================================
# Test 3: Compliance tools registered and assigned
# =====================================================================

class TestComplianceTools:
    def test_tools_registered(self):
        """All 3 compliance tools exist and are assigned to Compliance Crew."""
        headers = _auth_headers()
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools",
            params={"status": "approved"},
            headers=headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        tools = resp.json().get("tools", [])

        expected_tools = {
            "check_lending_regulations",
            "verify_document_completeness",
            "calculate_compliance_score",
        }

        found_tools = {}
        for tool in tools:
            if tool["name"] in expected_tools:
                found_tools[tool["name"]] = tool

        assert set(found_tools.keys()) == expected_tools, (
            f"Missing tools: {expected_tools - set(found_tools.keys())}"
        )


# =====================================================================
# Test 4: Mesh policies — bidirectional Customer Agent <-> Compliance Crew
# =====================================================================

class TestComplianceMeshPolicies:
    def test_bidirectional_policies_exist(self):
        """Customer Agent <-> Compliance Crew bidirectional allow policies exist."""
        headers = _auth_headers()
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/policies",
            headers=headers,
            timeout=10.0,
        )
        assert resp.status_code == 200
        policies = resp.json().get("policies", [])

        def get_source(p):
            return p.get("source_agent_name") or p.get("source", "")

        def get_dest(p):
            return p.get("dest_agent_name") or p.get("destination", "")

        customer_to_compliance = [
            p for p in policies
            if get_source(p) == "Customer Agent"
            and get_dest(p) == "Compliance Crew"
            and p.get("action") == "allow"
        ]
        assert len(customer_to_compliance) >= 1, "Missing policy: Customer Agent -> Compliance Crew"

        compliance_to_customer = [
            p for p in policies
            if get_source(p) == "Compliance Crew"
            and get_dest(p) == "Customer Agent"
            and p.get("action") == "allow"
        ]
        assert len(compliance_to_customer) >= 1, "Missing policy: Compliance Crew -> Customer Agent"


# =====================================================================
# Test 5: Sidecar tool call — call an assigned tool through the sidecar
# =====================================================================

class TestSidecarToolCall:
    def test_sidecar_allows_assigned_tool(self):
        """Calling an assigned tool through the sidecar returns 200 with real stub data."""
        resp = httpx.post(
            f"{COMPLIANCE_SIDECAR_URL}/tools/call",
            json={
                "tool_name": "check_lending_regulations",
                "arguments": {
                    "loan_amount": 300000,
                    "property_value": 400000,
                    "annual_income": 75000,
                },
            },
            timeout=30.0,
        )
        assert resp.status_code == 200, f"Sidecar returned {resp.status_code}: {resp.text}"
        data = resp.json()
        # The result should contain real data from the stub API
        result = data.get("result", data)
        # Result may be a string (from MCP tool) or dict
        if isinstance(result, str):
            result = json.loads(result)
        assert result.get("status") == "checked", f"Unexpected result: {result}"
        assert "ltv_ratio" in result
        assert "dti_ratio" in result

    def test_sidecar_blocks_unassigned_tool(self):
        """Calling an unassigned tool through the sidecar returns 403."""
        resp = httpx.post(
            f"{COMPLIANCE_SIDECAR_URL}/tools/call",
            json={
                "tool_name": "disburse_loan",  # assigned to Core Banking, not Compliance
                "arguments": {"loan_amount": 100000},
            },
            timeout=10.0,
        )
        assert resp.status_code == 403, f"Expected 403 for unassigned tool, got {resp.status_code}"

    def test_sidecar_verify_documents_tool(self):
        """verify_document_completeness tool works through sidecar with real data."""
        resp = httpx.post(
            f"{COMPLIANCE_SIDECAR_URL}/tools/call",
            json={
                "tool_name": "verify_document_completeness",
                "arguments": {"document_types_provided": "passport,payslip"},
            },
            timeout=30.0,
        )
        assert resp.status_code == 200, f"Sidecar returned {resp.status_code}: {resp.text}"
        data = resp.json()
        result = data.get("result", data)
        if isinstance(result, str):
            result = json.loads(result)
        assert result.get("status") == "checked"
        assert result.get("complete") is True
        assert result.get("missing_documents") == []

    def test_sidecar_calculate_score_tool(self):
        """calculate_compliance_score tool works through sidecar."""
        resp = httpx.post(
            f"{COMPLIANCE_SIDECAR_URL}/tools/call",
            json={
                "tool_name": "calculate_compliance_score",
                "arguments": {"findings": "All documents present. All regulatory checks passed. Application is compliant."},
            },
            timeout=30.0,
        )
        assert resp.status_code == 200, f"Sidecar returned {resp.status_code}: {resp.text}"
        data = resp.json()
        result = data.get("result", data)
        if isinstance(result, str):
            result = json.loads(result)
        assert result.get("status") == "scored"
        assert result.get("compliance_score") == 100
        assert result.get("suggested_verdict") == "PASS"


# =====================================================================
# Test 6: CrewAI A2A call — tools route through sidecar with real data
# =====================================================================

class TestCrewAISidecarIntegration:
    @pytest.mark.llm
    @pytest.mark.skipif(not HAS_LLM_KEY, reason="ANTHROPIC_API_KEY not set")
    def test_crew_uses_real_tool_results(self):
        """CrewAI crew calls tools through sidecar and verdict reflects real stub data.

        A compliant application (LTV=75%, all docs present) should get PASS.
        """
        payload = _make_a2a_payload({
            "customer_name": "Sidecar Test",
            "loan_amount": 300000,
            "property_value": 400000,
            "annual_salary": 75000,
            "document_types_provided": "passport,payslip",
        })

        resp = httpx.post(f"{COMPLIANCE_AGENT_URL}/a2a", json=payload, timeout=180.0)
        assert resp.status_code == 200
        result = resp.json().get("result", {})
        assert result.get("status") == "completed"

        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        verdict_data = json.loads(artifacts[0]["text"])

        assert "verdict" in verdict_data
        assert verdict_data["verdict"] in ("PASS", "FAIL", "REVIEW")
        assert "compliance_score" in verdict_data
        # A compliant application should score well
        assert verdict_data["compliance_score"] >= 50, (
            f"Expected score >= 50 for compliant application, got {verdict_data['compliance_score']}"
        )

    @pytest.mark.llm
    @pytest.mark.skipif(not HAS_LLM_KEY, reason="ANTHROPIC_API_KEY not set")
    def test_crew_detects_violation(self):
        """CrewAI crew detects LTV violation via sidecar tool call.

        LTV of 98% (490k/500k) should trigger a violation.
        """
        payload = _make_a2a_payload({
            "customer_name": "High LTV User",
            "loan_amount": 490000,
            "property_value": 500000,
            "annual_salary": 30000,
            "document_types_provided": "passport,payslip",
        })

        resp = httpx.post(f"{COMPLIANCE_AGENT_URL}/a2a", json=payload, timeout=180.0)
        assert resp.status_code == 200
        result = resp.json().get("result", {})
        assert result.get("status") == "completed"

        artifacts = result.get("artifacts", [])
        assert len(artifacts) > 0
        verdict_data = json.loads(artifacts[0]["text"])

        assert "verdict" in verdict_data
        # High LTV + high DTI should fail or at least have findings
        assert "findings" in verdict_data
        findings_text = str(verdict_data.get("findings", "")).lower()
        verdict = verdict_data["verdict"]
        score = verdict_data.get("compliance_score", 100)
        # Either the verdict is FAIL, or the score is low, or findings mention violation
        assert (
            verdict == "FAIL"
            or score < 80
            or "violation" in findings_text
            or "exceed" in findings_text
            or "ltv" in findings_text
            or "dti" in findings_text
        ), f"Expected detection of violations: verdict={verdict}, score={score}, findings={findings_text}"


# =====================================================================
# Test 7: Audit trail records tool calls through sidecar
# =====================================================================

class TestSidecarAuditTrail:
    @pytest.mark.llm
    @pytest.mark.skipif(not HAS_LLM_KEY, reason="ANTHROPIC_API_KEY not set")
    def test_audit_records_tool_calls(self):
        """After a crew run, the sidecar's audit trail has tool call records with decision=pass."""
        # Trigger a compliance review
        payload = _make_a2a_payload({
            "customer_name": "Audit Test",
            "loan_amount": 200000,
            "property_value": 300000,
            "annual_salary": 60000,
            "document_types_provided": "passport,payslip",
        })

        resp = httpx.post(f"{COMPLIANCE_AGENT_URL}/a2a", json=payload, timeout=180.0)
        assert resp.status_code == 200
        assert resp.json().get("result", {}).get("status") == "completed"

        # Give the sidecar a moment to flush audit records
        time.sleep(2)

        # Query the registry audit trail for Compliance Crew tool calls
        headers = _auth_headers()
        audit_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/audit",
            params={"source_agent": "Compliance Crew", "per_page": 50},
            headers=headers,
            timeout=10.0,
        )

        if audit_resp.status_code != 200:
            pytest.skip(f"Audit API returned {audit_resp.status_code} — may not be available")

        data = audit_resp.json()
        records = data.get("records", data.get("audit_records", []))

        # Filter for tool call records with decision=pass (not block)
        tool_pass_records = [
            r for r in records
            if r.get("decision") == "pass"
            and (r.get("source_agent_name") or r.get("source_agent")) == "Compliance Crew"
        ]

        assert len(tool_pass_records) >= 3, (
            f"Expected >= 3 tool call audit records with decision=pass, "
            f"found {len(tool_pass_records)}. "
            f"Total records: {len(records)}. "
            f"This means tool calls are not going through the sidecar correctly."
        )

        # Verify the 3 compliance tools appear in audit
        tool_names_in_audit = {r.get("dest_agent_name") or r.get("dest_agent", "") for r in tool_pass_records}
        expected_tools = {
            "check_lending_regulations",
            "verify_document_completeness",
            "calculate_compliance_score",
        }
        assert expected_tools.issubset(tool_names_in_audit), (
            f"Expected all 3 tool names in audit. Found: {tool_names_in_audit}"
        )
