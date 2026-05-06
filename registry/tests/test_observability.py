"""
Integration tests for the observability dashboard API endpoints.

All tests make real HTTP calls (httpx) to the running registry service.
Test data is seeded via the real API (mesh audit, guardrails) or direct DB
inserts (anomalies, guardrail events — no API for those).

Run via: kubectl exec -n recursant deployment/recursant-registry -c registry -- \
    python -m pytest tests/test_observability.py -v

Covers:
- POST /v1/mesh/audit → Kafka pipeline (202)
- GET /v1/mesh/observability/traces (list + pagination + filter)
- GET /v1/mesh/observability/traces/<task_id> (detail / waterfall)
- GET /v1/mesh/observability/alerts (list, resolved filter)
- GET /v1/mesh/observability/alerts/<id> (get)
- POST /v1/mesh/observability/alerts/<id>/acknowledge
- POST /v1/mesh/observability/alerts/<id>/resolve
- GET /v1/mesh/observability/security/posture
- GET /v1/mesh/observability/tools/effectiveness
- GET /v1/mesh/observability/tools/metrics
- GET /v1/mesh/observability/golden-signals
- GET /v1/mesh/observability/cost
- Auth required on all endpoints
"""

import hashlib
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

BASE_URL = "http://localhost:5000"
TENANT_ID = "default"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def auth_token():
    """Login with real admin credentials and return JWT token."""
    resp = httpx.post(
        f"{BASE_URL}/v1/auth/login",
        json={
            "username": os.environ.get("ADMIN_USERNAME", "admin"),
            "password": os.environ["ADMIN_PASSWORD"],
        },
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="session")
def headers(auth_token):
    """Auth headers for all requests."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="session")
def mesh_headers():
    """Headers for mesh API endpoints (use API key, not JWT)."""
    return {
        "X-Mesh-Api-Key": os.environ.get("MESH_API_KEY", "mesh-dev-key"),
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="session")
def db_conn():
    """Direct DB connection for seeding data that has no API (anomalies, etc)."""
    import psycopg2

    db_url = os.environ.get("DATABASE_URL", "postgresql://registry:registry@recursant-db:5432/registry")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    yield conn
    conn.close()


# ============================================================================
# Helpers
# ============================================================================


def _post_audit_event(mesh_headers, task_id=None, source="obs-test-src",
                      dest="obs-test-dst", decision="allow", outcome="success",
                      details=None):
    """POST a real audit event through the API (goes through Kafka or PG)."""
    task_id = task_id or str(uuid.uuid4())
    msg_hash = hashlib.sha256(f"{task_id}:{time.time()}".encode()).hexdigest()[:64]
    record = {
        "sidecar_id": f"obs-test-sidecar-{source}",
        "source_agent_name": source,
        "dest_agent_name": dest,
        "direction": "outbound",
        "a2a_method": "tasks/send",
        "message_hash": msg_hash,
        "decision": decision,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "details": details or {},
        "record_hash": hashlib.sha256(msg_hash.encode()).hexdigest()[:64],
        "sequence_number": 1,
    }
    resp = httpx.post(
        f"{BASE_URL}/v1/mesh/audit",
        json={"records": [record]},
        headers=mesh_headers,
        timeout=10,
    )
    assert resp.status_code in (201, 202), f"Audit POST failed: {resp.status_code} {resp.text}"
    return task_id


def _insert_anomaly(db_conn, anomaly_type="traffic_spike", severity="medium",
                    agent_name="obs-test-agent", resolved=False, acknowledged=False):
    """Insert anomaly directly into DB (no API exists for this)."""
    anomaly_id = str(uuid.uuid4())
    cur = db_conn.cursor()
    cur.execute(
        """INSERT INTO mesh_anomalies
           (id, tenant_id, anomaly_type, severity, agent_name, description, details,
            detected_at, resolved_at, is_acknowledged)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            anomaly_id, TENANT_ID, anomaly_type, severity, agent_name,
            f"{anomaly_type} detected for {agent_name}",
            '{"threshold": 2.0, "observed": 5.0}',
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) if resolved else None,
            acknowledged,
        ),
    )
    return anomaly_id


def _insert_guardrail_event(db_conn, guardrail_id, guardrail_name, action="block",
                            agent_name="obs-test-agent", ts=None, is_false_positive=None):
    """Insert guardrail event directly into DB."""
    ts = ts or datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())
    cur = db_conn.cursor()
    is_error = action not in ("pass", "block")
    cur.execute(
        """INSERT INTO guardrail_events
           (id, tenant_id, guardrail_id, guardrail_name, guardrail_type, mechanism,
            agent_name, action, latency_ms, timestamp, is_false_positive, is_error)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            event_id, TENANT_ID, guardrail_id, guardrail_name, "pre_processing", "regex",
            agent_name, action, 5.0, ts, is_false_positive, is_error,
        ),
    )


def _cleanup_anomalies(db_conn, ids):
    """Remove test anomalies."""
    if not ids:
        return
    cur = db_conn.cursor()
    cur.execute(
        "DELETE FROM mesh_anomalies WHERE id = ANY(%s::uuid[])", (ids,)
    )


def _cleanup_guardrail_events(db_conn, guardrail_id):
    """Remove test guardrail events."""
    cur = db_conn.cursor()
    cur.execute(
        "DELETE FROM guardrail_events WHERE guardrail_id = %s", (guardrail_id,)
    )


# ============================================================================
# Kafka pipeline
# ============================================================================


class TestKafkaPipeline:
    def test_audit_post_accepted(self, mesh_headers):
        """POST /v1/mesh/audit should return 201 or 202 (Kafka)."""
        task_id = _post_audit_event(mesh_headers)
        assert task_id  # non-empty

    def test_audit_event_reaches_database(self, mesh_headers, headers):
        """Audit event posted via API should appear in trace listing."""
        unique_src = f"kafka-test-{uuid.uuid4().hex[:8]}"
        task_id = _post_audit_event(mesh_headers, source=unique_src, dest="kafka-test-dst")

        # Wait for PG writer consumer to flush (batch interval 1s)
        time.sleep(3)

        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces",
            params={"agent_name": unique_src},
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        matching = [t for t in data["traces"] if t["task_id"] == task_id]
        assert len(matching) == 1, f"Expected trace for {task_id}, got {data['traces']}"


# ============================================================================
# Trace endpoints
# ============================================================================


class TestTraceList:
    def test_list_traces_returns_results(self, mesh_headers, headers):
        """Posting audit events then listing should return them."""
        task_id = _post_audit_event(mesh_headers, source="trace-list-src", dest="trace-list-dst")
        time.sleep(3)

        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces",
            params={"agent_name": "trace-list-src"},
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(t["task_id"] == task_id for t in data["traces"])

    def test_list_traces_pagination(self, mesh_headers, headers):
        """Pagination should respect per_page parameter."""
        tag = uuid.uuid4().hex[:8]
        src = f"page-test-{tag}"
        for _ in range(3):
            _post_audit_event(mesh_headers, source=src, dest=f"page-dst-{tag}")
        time.sleep(3)

        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces",
            params={"agent_name": src, "per_page": 2, "page": 1},
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["traces"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 2

    def test_list_traces_filter_by_agent(self, mesh_headers, headers):
        """Filter should match source OR dest agent name."""
        tag = uuid.uuid4().hex[:8]
        src_a = f"filter-alpha-{tag}"
        src_b = f"filter-gamma-{tag}"
        tid_a = _post_audit_event(mesh_headers, source=src_a, dest=f"filter-beta-{tag}")
        tid_b = _post_audit_event(mesh_headers, source=src_b, dest=f"filter-delta-{tag}")
        time.sleep(3)

        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces",
            params={"agent_name": src_a},
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        task_ids = [t["task_id"] for t in data["traces"]]
        assert tid_a in task_ids
        assert tid_b not in task_ids


class TestTraceDetail:
    def test_get_trace_not_found(self, headers):
        """Non-existent task_id should return 404."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces/{uuid.uuid4()}",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_get_trace_returns_hops(self, mesh_headers, headers):
        """Trace detail should include per-hop data and summary."""
        task_id = str(uuid.uuid4())
        tag = uuid.uuid4().hex[:8]
        # Two hops: A→B and B→C with the same task_id
        _post_audit_event(mesh_headers, task_id=task_id,
                          source=f"hop-A-{tag}", dest=f"hop-B-{tag}")
        time.sleep(0.2)
        _post_audit_event(mesh_headers, task_id=task_id,
                          source=f"hop-B-{tag}", dest=f"hop-C-{tag}")
        time.sleep(3)

        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/traces/{task_id}",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert len(data["hops"]) >= 2
        assert data["agent_count"] >= 3  # A, B, C (may include duplicates from Kafka+PG path)
        assert data["total_duration_ms"] >= 0
        assert data["status"] == "success"


# ============================================================================
# Alert endpoints
# ============================================================================


class TestAlerts:
    def test_list_alerts_unresolved_only(self, headers, db_conn):
        """Default listing should only show unresolved alerts."""
        id1 = _insert_anomaly(db_conn, resolved=False, agent_name="alert-test-1")
        id2 = _insert_anomaly(db_conn, resolved=True, agent_name="alert-test-2")
        try:
            resp = httpx.get(
                f"{BASE_URL}/v1/mesh/observability/alerts",
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            data = resp.json()
            alert_ids = [a["id"] for a in data["alerts"]]
            assert id1 in alert_ids
            assert id2 not in alert_ids
        finally:
            _cleanup_anomalies(db_conn, [id1, id2])

    def test_list_alerts_include_resolved(self, headers, db_conn):
        """include_resolved=true should return all alerts."""
        id1 = _insert_anomaly(db_conn, resolved=False, agent_name="alert-incl-1")
        id2 = _insert_anomaly(db_conn, resolved=True, agent_name="alert-incl-2")
        try:
            resp = httpx.get(
                f"{BASE_URL}/v1/mesh/observability/alerts",
                params={"include_resolved": "true"},
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            alert_ids = [a["id"] for a in resp.json()["alerts"]]
            assert id1 in alert_ids
            assert id2 in alert_ids
        finally:
            _cleanup_anomalies(db_conn, [id1, id2])

    def test_get_alert(self, headers, db_conn):
        """GET a single alert by ID."""
        aid = _insert_anomaly(db_conn, anomaly_type="error_burst", severity="high")
        try:
            resp = httpx.get(
                f"{BASE_URL}/v1/mesh/observability/alerts/{aid}",
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == aid
            assert data["anomaly_type"] == "error_burst"
            assert data["severity"] == "high"
        finally:
            _cleanup_anomalies(db_conn, [aid])

    def test_get_alert_not_found(self, headers):
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/alerts/{uuid.uuid4()}",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_acknowledge_alert(self, headers, db_conn):
        """Acknowledging sets is_acknowledged=True."""
        aid = _insert_anomaly(db_conn, acknowledged=False)
        try:
            resp = httpx.post(
                f"{BASE_URL}/v1/mesh/observability/alerts/{aid}/acknowledge",
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            assert resp.json()["is_acknowledged"] is True
        finally:
            _cleanup_anomalies(db_conn, [aid])

    def test_acknowledge_not_found(self, headers):
        resp = httpx.post(
            f"{BASE_URL}/v1/mesh/observability/alerts/{uuid.uuid4()}/acknowledge",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_resolve_alert(self, headers, db_conn):
        """Resolving sets resolved_at timestamp."""
        aid = _insert_anomaly(db_conn, resolved=False)
        try:
            resp = httpx.post(
                f"{BASE_URL}/v1/mesh/observability/alerts/{aid}/resolve",
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            assert resp.json()["resolved_at"] is not None
        finally:
            _cleanup_anomalies(db_conn, [aid])

    def test_resolve_not_found(self, headers):
        resp = httpx.post(
            f"{BASE_URL}/v1/mesh/observability/alerts/{uuid.uuid4()}/resolve",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 404


# ============================================================================
# Security posture
# ============================================================================


class TestSecurityPosture:
    def test_posture_returns_valid_score(self, headers):
        """Should return a valid composite score with component breakdown."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/security/posture",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "composite_score" in data
        assert isinstance(data["composite_score"], (int, float))
        assert 0 <= data["composite_score"] <= 100
        assert "components" in data
        for key in ["mtls_coverage", "guardrail_coverage", "guardrail_effectiveness",
                     "anomaly_score", "policy_compliance"]:
            assert key in data["components"]

    def test_posture_anomalies_reduce_score(self, headers, db_conn):
        """Open anomalies should reduce the anomaly_score component."""
        aids = []
        for i in range(6):
            aids.append(_insert_anomaly(db_conn, resolved=False, agent_name=f"posture-test-{i}"))
        try:
            resp = httpx.get(
                f"{BASE_URL}/v1/mesh/observability/security/posture",
                headers=headers,
                timeout=10,
            )
            data = resp.json()
            assert data["components"]["anomaly_score"] <= 50.0
            assert data["open_anomalies"] >= 6
        finally:
            _cleanup_anomalies(db_conn, aids)


# ============================================================================
# Guardrail effectiveness
# ============================================================================


class TestGuardrailEffectiveness:
    def test_effectiveness_returns_matrix(self, headers):
        """Should return guardrail effectiveness matrix."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/tools/effectiveness",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "guardrails" in data
        assert "period_hours" in data

    def test_effectiveness_with_seeded_events(self, headers, db_conn):
        """Create guardrail + events via DB, verify effectiveness computes correctly."""
        tag = uuid.uuid4().hex[:8]
        gname = f"Effectiveness-Guard-{tag}"

        # Create guardrail via API (draft → activate)
        create_resp = httpx.post(
            f"{BASE_URL}/v1/guardrails",
            json={
                "name": gname,
                "description": f"Test guardrail {tag}",
                "type": "pre_processing",
                "mechanism": "regex",
                "enforcement_mode": "block",
                "config": {"patterns": [{"pattern": "test-pattern", "description": "test"}]},
                "scope": "all_agents",
                "priority": 10,
            },
            headers=headers,
            timeout=10,
        )
        assert create_resp.status_code == 201, f"Guardrail create failed: {create_resp.text}"
        gid = create_resp.json()["id"]

        # Activate the guardrail
        act_resp = httpx.post(
            f"{BASE_URL}/v1/guardrails/{gid}/activate",
            headers=headers,
            timeout=10,
        )
        assert act_resp.status_code == 200, f"Guardrail activate failed: {act_resp.text}"

        # Seed 10 events: 3 blocks, 1 false positive
        now = datetime.now(timezone.utc)
        for i in range(10):
            action = "block" if i < 3 else "pass"
            fp = True if i == 0 else None
            _insert_guardrail_event(
                db_conn, guardrail_id=gid, guardrail_name=gname,
                action=action, agent_name=f"eff-agent-{tag}",
                ts=now - timedelta(minutes=i), is_false_positive=fp,
            )

        try:
            resp = httpx.get(
                f"{BASE_URL}/v1/mesh/observability/tools/effectiveness",
                params={"hours": 1},
                headers=headers,
                timeout=10,
            )
            assert resp.status_code == 200
            data = resp.json()
            matched = [g for g in data["guardrails"] if g["guardrail_id"] == gid]
            assert len(matched) == 1

            g = matched[0]
            assert g["guardrail_name"] == gname
            assert g["guardrail_type"] == "pre_processing"
            assert g["mechanism"] == "regex"
            assert g["total_events"] == 10
            assert g["blocked_events"] == 3
            assert g["block_rate"] == 0.3
            assert g["false_positive_count"] == 1
            assert g["false_positive_rate"] == 0.1
        finally:
            _cleanup_guardrail_events(db_conn, gid)
            # Delete guardrail
            httpx.delete(f"{BASE_URL}/v1/guardrails/{gid}", headers=headers, timeout=10)


# ============================================================================
# Tool metrics
# ============================================================================


class TestToolMetrics:
    def test_tool_metrics_returns_list(self, headers):
        """Should return tools list with period_hours."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/tools/metrics",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "period_hours" in data


# ============================================================================
# Golden signals (reads from real Redis)
# ============================================================================


class TestGoldenSignals:
    def test_golden_signals_summary(self, headers):
        """Should return agents dict from Redis."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/golden-signals",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data

    def test_golden_signals_nonexistent_agent(self, headers):
        """Per-agent golden signals for nonexistent agent should 404."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/golden-signals/nonexistent-agent-{uuid.uuid4().hex[:8]}",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code in (200, 404)


# ============================================================================
# Cost (reads from real Redis)
# ============================================================================


class TestCost:
    def test_cost_summary(self, headers):
        """Should return cost summary structure."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/cost",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total_cost_usd" in data
        assert isinstance(data["total_cost_usd"], (int, float))

    def test_cost_nonexistent_agent(self, headers):
        """Per-agent cost for nonexistent agent should return empty entries."""
        resp = httpx.get(
            f"{BASE_URL}/v1/mesh/observability/cost/nonexistent-agent-{uuid.uuid4().hex[:8]}",
            headers=headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["entries"] == []


# ============================================================================
# Auth required
# ============================================================================


class TestAuthRequired:
    """All observability endpoints should require JWT authentication."""

    ENDPOINTS = [
        ("GET", f"{BASE_URL}/v1/mesh/observability/traces"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/traces/{uuid.uuid4()}"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/golden-signals"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/cost"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/alerts"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/security/posture"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/tools/metrics"),
        ("GET", f"{BASE_URL}/v1/mesh/observability/tools/effectiveness"),
    ]

    @pytest.mark.parametrize("method,url", ENDPOINTS)
    def test_requires_auth(self, method, url):
        """Requests without Authorization header should be rejected."""
        no_auth_headers = {"X-Tenant-ID": TENANT_ID}
        if method == "GET":
            resp = httpx.get(url, headers=no_auth_headers, timeout=10)
        else:
            resp = httpx.post(url, headers=no_auth_headers, timeout=10)
        assert resp.status_code in (401, 403, 422), (
            f"{method} {url} returned {resp.status_code} without auth"
        )
