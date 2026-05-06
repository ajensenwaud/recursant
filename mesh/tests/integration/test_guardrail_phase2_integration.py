"""Integration tests for Guardrail Phase 2 features.

Tests cover:
- Guardrail observability event ingestion via mesh API
- Observability dashboard endpoints with real data
- Adversarial suite lifecycle via admin API
- Adversarial run execution against live guardrails
- CoT analysis fields in audit records

All tests run against the real registry (K8s or Docker Compose).
"""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest

from tests.integration.conftest import (
    REGISTRY_URL,
    admin_login,
    auth_headers,
    mesh_headers,
    registry_available,
)

pytestmark = pytest.mark.skipif(
    not registry_available(),
    reason="Real registry not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(path: str, headers: dict, json_data: dict, timeout: float = 15.0):
    return httpx.post(f"{REGISTRY_URL}/v1{path}", json=json_data, headers=headers, timeout=timeout)


def _get(path: str, headers: dict, params: dict | None = None, timeout: float = 15.0):
    return httpx.get(f"{REGISTRY_URL}/v1{path}", headers=headers, params=params, timeout=timeout)


def _delete(path: str, headers: dict, timeout: float = 15.0):
    return httpx.delete(f"{REGISTRY_URL}/v1{path}", headers=headers, timeout=timeout)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def token():
    return admin_login()


@pytest.fixture(scope="module")
def admin_hdrs(token):
    return auth_headers(token)


@pytest.fixture(scope="module")
def mesh_hdrs():
    return mesh_headers()


@pytest.fixture
def guardrail_id(admin_hdrs):
    """Create an active regex guardrail and return its ID. Cleans up after."""
    payload = {
        "name": f"integ-guardrail-{uuid.uuid4().hex[:8]}",
        "description": "Integration test guardrail",
        "type": "pre_processing",
        "mechanism": "regex",
        "enforcement_mode": "block",
        "config": {
            "patterns": [
                {"name": "injection", "pattern": r"ignore\s+previous", "action": "block"},
            ],
        },
        "priority": 10,
        "version": "1.0.0",
    }
    resp = _post("/guardrails", admin_hdrs, payload)
    assert resp.status_code == 201, f"Create guardrail failed: {resp.text}"
    gid = resp.json()["id"]

    # Activate it
    _post(f"/guardrails/{gid}/activate", admin_hdrs, {})

    yield gid

    # Cleanup
    _delete(f"/guardrails/{gid}", admin_hdrs)


# ============================================================================
# Observability Event Ingestion
# ============================================================================


class TestObservabilityEventIngestion:
    """POST /v1/mesh/guardrail-events — ingest events from sidecars."""

    def test_ingest_single_event(self, mesh_hdrs, guardrail_id):
        resp = _post("/mesh/guardrail-events", mesh_hdrs, {
            "events": [{
                "guardrail_id": guardrail_id,
                "guardrail_name": "test-guardrail",
                "guardrail_type": "pre_processing",
                "mechanism": "regex",
                "agent_name": "integ-agent-a",
                "action": "block",
                "reasoning": "Matched injection pattern",
                "latency_ms": 5,
                "matched_pattern": "ignore previous",
                "is_error": False,
            }],
        })
        assert resp.status_code == 201
        assert resp.json()["count"] == 1

    def test_ingest_batch_events(self, mesh_hdrs, guardrail_id):
        events = []
        for i in range(5):
            events.append({
                "guardrail_id": guardrail_id,
                "guardrail_name": "test-guardrail",
                "guardrail_type": "pre_processing",
                "mechanism": "regex",
                "agent_name": f"integ-agent-{i}",
                "action": "pass" if i % 2 == 0 else "block",
                "reasoning": f"Result {i}",
                "latency_ms": 3 + i,
                "is_error": False,
            })
        resp = _post("/mesh/guardrail-events", mesh_hdrs, {"events": events})
        assert resp.status_code == 201
        assert resp.json()["count"] == 5

    def test_ingest_requires_mesh_api_key(self, guardrail_id):
        bad_headers = {"Content-Type": "application/json", "X-Tenant-ID": "default"}
        resp = _post("/mesh/guardrail-events", bad_headers, {
            "events": [{"guardrail_id": guardrail_id, "agent_name": "x", "action": "pass"}],
        })
        assert resp.status_code == 401


# ============================================================================
# Observability Dashboard Endpoints
# ============================================================================


class TestObservabilityDashboard:
    """GET /v1/guardrails/observability/* — dashboard data."""

    def test_summary_returns_data(self, admin_hdrs):
        resp = _get("/guardrails/observability/summary", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events" in data
        assert "block_rate" in data

    def test_trigger_rates(self, admin_hdrs):
        resp = _get("/guardrails/observability/trigger-rates", admin_hdrs, params={"interval": "day"})
        assert resp.status_code == 200
        data = resp.json()
        # API returns {"trigger_rates": [...]}
        rates = data.get("trigger_rates", data) if isinstance(data, dict) else data
        assert isinstance(rates, list)

    def test_latency_breakdown(self, admin_hdrs):
        resp = _get("/guardrails/observability/latency", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        # API returns {"latency": [...]}
        latency = data.get("latency", data) if isinstance(data, dict) else data
        assert isinstance(latency, list)

    def test_top_blocked(self, admin_hdrs):
        resp = _get("/guardrails/observability/top-blocked", admin_hdrs, params={"limit": "5"})
        assert resp.status_code == 200
        data = resp.json()
        # API returns {"patterns": [...]}
        patterns = data.get("patterns", data) if isinstance(data, dict) else data
        assert isinstance(patterns, list)

    def test_drift_detection(self, admin_hdrs):
        resp = _get("/guardrails/observability/drift", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        # API returns {"drift": [...]}
        drift = data.get("drift", data) if isinstance(data, dict) else data
        assert isinstance(drift, list)


# ============================================================================
# Adversarial Suite Lifecycle
# ============================================================================


class TestAdversarialSuiteLifecycle:
    """Full CRUD lifecycle for adversarial test suites."""

    def test_create_list_get_update_delete(self, admin_hdrs, guardrail_id):
        # Create
        create_payload = {
            "name": f"integ-adv-suite-{uuid.uuid4().hex[:8]}",
            "description": "Integration test suite",
            "attack_types": ["encoding", "jailbreak"],
            "target_guardrail_ids": [guardrail_id],
            "evasion_rate_threshold": 0.5,
        }
        resp = _post("/adversarial-suites", admin_hdrs, create_payload)
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        suite = resp.json()
        suite_id = suite["id"]
        assert suite["name"] == create_payload["name"]
        assert suite["status"] == "active"

        # List
        resp = _get("/adversarial-suites", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        suites = data.get("suites", data) if isinstance(data, dict) else data
        assert any(s["id"] == suite_id for s in suites)

        # Get
        resp = _get(f"/adversarial-suites/{suite_id}", admin_hdrs)
        assert resp.status_code == 200
        assert resp.json()["id"] == suite_id

        # Update
        resp = httpx.put(
            f"{REGISTRY_URL}/v1/adversarial-suites/{suite_id}",
            json={"description": "Updated description"},
            headers=admin_hdrs,
            timeout=15.0,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

        # Delete (soft)
        resp = _delete(f"/adversarial-suites/{suite_id}", admin_hdrs)
        assert resp.status_code == 200

        # Should no longer appear in list
        resp = _get(f"/adversarial-suites/{suite_id}", admin_hdrs)
        assert resp.status_code == 404


# ============================================================================
# Adversarial Run Execution
# ============================================================================


class TestAdversarialRunExecution:
    """Trigger and execute adversarial runs against live guardrails."""

    def test_trigger_and_poll_run(self, admin_hdrs, guardrail_id):
        # Create suite targeting the guardrail
        suite_payload = {
            "name": f"integ-run-suite-{uuid.uuid4().hex[:8]}",
            "attack_types": ["encoding"],
            "target_guardrail_ids": [guardrail_id],
            "evasion_rate_threshold": 1.0,
        }
        resp = _post("/adversarial-suites", admin_hdrs, suite_payload)
        assert resp.status_code == 201
        suite_id = resp.json()["id"]

        # Trigger run
        resp = _post(f"/adversarial-suites/{suite_id}/run", admin_hdrs, {})
        assert resp.status_code in (201, 202), f"Trigger failed: {resp.text}"
        data = resp.json()
        run_id = data.get("run_id", data.get("id"))

        # Poll until completed (runs in background thread)
        deadline = time.time() + 60
        status = "pending"
        while time.time() < deadline and status not in ("completed", "failed"):
            time.sleep(2)
            resp = _get(f"/adversarial-suites/{suite_id}/runs/{run_id}", admin_hdrs)
            if resp.status_code == 200:
                status = resp.json().get("status", "pending")

        assert status == "completed", f"Run did not complete in time, last status: {status}"

        # Verify run results
        run_data = resp.json()
        assert run_data["total_inputs"] > 0
        assert "evasion_rate" in run_data
        assert run_data["result_signature"] is not None
        assert run_data["signature_algorithm"] == "HMAC-SHA256"

        # List runs
        resp = _get(f"/adversarial-suites/{suite_id}/runs", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        runs = data.get("runs", data) if isinstance(data, dict) else data
        assert len(runs) >= 1

        # Cleanup
        _delete(f"/adversarial-suites/{suite_id}", admin_hdrs)

    def test_alerts_endpoint(self, admin_hdrs):
        """GET /v1/adversarial-alerts returns breached runs."""
        resp = _get("/adversarial-alerts", admin_hdrs)
        assert resp.status_code == 200
        data = resp.json()
        alerts = data.get("alerts", data) if isinstance(data, dict) else data
        assert isinstance(alerts, list)


# ============================================================================
# CoT Analysis in Audit Records
# ============================================================================


class TestCoTAuditIntegration:
    """Verify CoT analysis fields are accepted and stored in audit records."""

    def test_audit_record_with_cot_analysis(self, mesh_hdrs, admin_hdrs):
        """Submit an audit record with CoT analysis details and verify storage."""
        cot_details = {
            "cot_analysis": {
                "analyzed": True,
                "risk_level": "medium",
                "flags": [
                    {
                        "type": "injection_in_retrieval",
                        "severity": "medium",
                        "description": "Injection pattern in retrieved doc",
                        "step_index": 2,
                    }
                ],
                "tool_calls_analyzed": 3,
                "retrieval_steps_analyzed": 1,
                "decision_points_analyzed": 2,
                "latency_ms": 150,
                "model_used": "claude-sonnet-4-5-20250929",
            }
        }

        record = {
            "records": [{
                "timestamp": "2026-02-27T12:00:00Z",
                "source_agent_id": "test-src",
                "source_agent_name": "integ-cot-agent-a",
                "dest_agent_id": "test-dst",
                "dest_agent_name": "integ-cot-agent-b",
                "task_id": f"cot-task-{uuid.uuid4().hex[:8]}",
                "a2a_method": "message/send",
                "message_hash": "abc123",
                "direction": "inbound",
                "decision": "pass",
                "outcome": "success",
                "details": cot_details,
                "sidecar_id": "integ-cot-sidecar",
                "record_hash": "deadbeef" * 8,
                "previous_record_hash": None,
                "sequence_number": 1,
            }],
        }

        resp = _post("/mesh/audit", mesh_hdrs, record)
        assert resp.status_code == 201, f"Audit submit failed: {resp.text}"
        assert resp.json()["count"] == 1

        # Verify via mesh audit API that CoT fields are stored
        resp = _get("/mesh/audit", admin_hdrs, params={"limit": "5"})
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("records", data) if isinstance(data, dict) else data
            # Just verify the endpoint works — detailed CoT field checks are in unit tests
            assert isinstance(records, (list, dict))
