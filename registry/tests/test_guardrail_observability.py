"""
Tests for guardrail observability API endpoints and event ingestion.

Tests cover:
- POST /v1/mesh/guardrail-events (event ingestion via mesh API key)
- GET /v1/guardrails/observability/summary
- GET /v1/guardrails/observability/trigger-rates
- GET /v1/guardrails/observability/latency
- GET /v1/guardrails/observability/top-blocked
- GET /v1/guardrails/observability/drift
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models.guardrail import GuardrailEvent


# ============================================================================
# Helpers
# ============================================================================


def _mesh_headers(app):
    """Return headers for mesh API key authentication."""
    return {
        "Content-Type": "application/json",
        "X-Mesh-API-Key": app.config.get("MESH_API_KEY", "test-key"),
        "X-Tenant-ID": "test-tenant",
    }


def _seed_events(app, events):
    """Insert GuardrailEvent rows directly into the DB.

    *events* is a list of dicts whose keys match GuardrailEvent columns.
    The ``tenant_id`` defaults to ``test-tenant`` if not provided.
    """
    with app.app_context():
        for evt in events:
            evt.setdefault("tenant_id", "test-tenant")
            record = GuardrailEvent(**evt)
            db.session.add(record)
        db.session.commit()


# ============================================================================
# Event ingestion (POST /v1/mesh/guardrail-events)
# ============================================================================


class TestGuardrailEventIngestion:
    def test_ingest_single_event(self, app, client, db_session):
        """A single valid event should be accepted and persisted."""
        payload = {
            "events": [
                {
                    "guardrail_id": str(uuid.uuid4()),
                    "guardrail_name": "pii-filter",
                    "guardrail_type": "pre_processing",
                    "mechanism": "regex",
                    "agent_name": "test-agent",
                    "sidecar_id": "sidecar-1",
                    "action": "block",
                    "reasoning": "PII detected",
                    "latency_ms": 12.5,
                    "matched_pattern": "SSN pattern",
                    "input_hash": "abc123",
                    "is_error": False,
                }
            ]
        }
        resp = client.post(
            "/v1/mesh/guardrail-events",
            data=json.dumps(payload),
            headers=_mesh_headers(app),
        )
        assert resp.status_code in (201, 202)
        data = resp.get_json()
        assert data["status"] == "accepted"
        assert data["count"] == 1

    def test_ingest_batch_events(self, app, client, db_session):
        """Multiple events in one request should all be persisted."""
        events = [
            {
                "guardrail_name": f"guardrail-{i}",
                "agent_name": "batch-agent",
                "action": "pass" if i % 2 == 0 else "block",
                "mechanism": "regex",
                "latency_ms": 10.0 + i,
            }
            for i in range(5)
        ]
        resp = client.post(
            "/v1/mesh/guardrail-events",
            data=json.dumps({"events": events}),
            headers=_mesh_headers(app),
        )
        assert resp.status_code in (201, 202)
        assert resp.get_json()["count"] == 5

    def test_ingest_missing_events_array(self, app, client, db_session):
        """Request without ``events`` key should return 400."""
        resp = client.post(
            "/v1/mesh/guardrail-events",
            data=json.dumps({"data": []}),
            headers=_mesh_headers(app),
        )
        assert resp.status_code == 400

    def test_ingest_requires_mesh_api_key(self, app, client, db_session):
        """Request without a valid mesh API key should be rejected (401)."""
        # Only enforce when the app actually has a MESH_API_KEY configured.
        mesh_key = app.config.get("MESH_API_KEY")
        if not mesh_key:
            pytest.skip("No MESH_API_KEY configured; dev mode allows all")

        resp = client.post(
            "/v1/mesh/guardrail-events",
            data=json.dumps({"events": [{"action": "pass"}]}),
            headers={
                "Content-Type": "application/json",
                "X-Mesh-API-Key": "wrong-key",
                "X-Tenant-ID": "test-tenant",
            },
        )
        assert resp.status_code == 401

    def test_ingest_event_with_timestamp(self, app, client, db_session):
        """Events with an explicit ISO timestamp should honour it."""
        ts = "2026-02-01T12:00:00+00:00"
        payload = {
            "events": [
                {
                    "guardrail_name": "ts-test",
                    "agent_name": "ts-agent",
                    "action": "pass",
                    "timestamp": ts,
                }
            ]
        }
        resp = client.post(
            "/v1/mesh/guardrail-events",
            data=json.dumps(payload),
            headers=_mesh_headers(app),
        )
        assert resp.status_code in (201, 202)

        # Verify the persisted timestamp
        with app.app_context():
            event = GuardrailEvent.query.filter_by(
                guardrail_name="ts-test", tenant_id="test-tenant",
            ).first()
            assert event is not None
            assert event.timestamp.year == 2026
            assert event.timestamp.month == 2


# ============================================================================
# Observability summary (GET /v1/guardrails/observability/summary)
# ============================================================================


class TestObservabilitySummary:
    def test_summary_empty(self, app, client, db_session, auth_headers):
        """Summary with no events should return zeroed stats."""
        resp = client.get(
            "/v1/guardrails/observability/summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_events"] == 0
        assert data["block_count"] == 0
        assert data["block_rate"] == 0.0
        assert data["avg_latency_ms"] == 0.0

    def test_summary_with_data(self, app, client, db_session, auth_headers):
        """Summary should reflect seeded event data."""
        now = datetime.now(timezone.utc)
        _seed_events(app, [
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "latency_ms": 10.0, "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "latency_ms": 20.0, "timestamp": now,
             "matched_pattern": "injection"},
            {"guardrail_name": "g2", "agent_name": "a2", "action": "block",
             "mechanism": "llm_judge", "latency_ms": 100.0, "timestamp": now,
             "matched_pattern": "bias"},
            {"guardrail_name": "g2", "agent_name": "a2", "action": "warn",
             "mechanism": "llm_judge", "latency_ms": 80.0, "timestamp": now,
             "is_error": True, "error_message": "timeout"},
        ])

        resp = client.get(
            "/v1/guardrails/observability/summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_events"] == 4
        assert data["block_count"] == 2
        assert data["block_rate"] == 50.0
        assert data["active_guardrails"] == 2
        assert data["active_agents"] == 2
        assert data["error_count"] == 1
        assert data["avg_latency_ms"] > 0
        assert data["time_range"]["earliest"] is not None


# ============================================================================
# Trigger rates (GET /v1/guardrails/observability/trigger-rates)
# ============================================================================


class TestObservabilityTriggerRates:
    def test_trigger_rates_empty(self, app, client, db_session, auth_headers):
        """Trigger rates with no events should return empty list."""
        resp = client.get(
            "/v1/guardrails/observability/trigger-rates",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "trigger_rates" in data
        assert isinstance(data["trigger_rates"], list)
        assert len(data["trigger_rates"]) == 0

    def test_trigger_rates_with_data(self, app, client, db_session, auth_headers):
        """Trigger rates should bucket events by time."""
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        _seed_events(app, [
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "latency_ms": 5.0, "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "latency_ms": 8.0, "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "latency_ms": 6.0, "timestamp": hour_ago},
        ])

        resp = client.get(
            "/v1/guardrails/observability/trigger-rates?interval=1h",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rates = resp.get_json()["trigger_rates"]
        assert len(rates) >= 1
        # Each bucket should have the expected keys
        for bucket in rates:
            assert "bucket" in bucket
            assert "pass_count" in bucket
            assert "block_count" in bucket
            assert "total" in bucket

    def test_trigger_rates_filter_by_agent(self, app, client, db_session, auth_headers):
        """Trigger rates should accept agent_name filter."""
        now = datetime.now(timezone.utc)
        _seed_events(app, [
            {"guardrail_name": "g1", "agent_name": "agent-alpha",
             "action": "block", "mechanism": "regex", "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "agent-beta",
             "action": "pass", "mechanism": "regex", "timestamp": now},
        ])

        resp = client.get(
            "/v1/guardrails/observability/trigger-rates?agent_name=agent-alpha",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rates = resp.get_json()["trigger_rates"]
        # Only agent-alpha events should be counted
        total_events = sum(b["total"] for b in rates)
        assert total_events == 1


# ============================================================================
# Latency breakdown (GET /v1/guardrails/observability/latency)
# ============================================================================


class TestObservabilityLatency:
    def test_latency_empty(self, app, client, db_session, auth_headers):
        """Latency endpoint with no events should return empty list."""
        resp = client.get(
            "/v1/guardrails/observability/latency",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "latency" in data
        assert isinstance(data["latency"], list)
        assert len(data["latency"]) == 0

    def test_latency_breakdown_by_mechanism(self, app, client, db_session, auth_headers):
        """Latency should group by mechanism with p50/p95/p99."""
        now = datetime.now(timezone.utc)
        _seed_events(app, [
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "latency_ms": 5.0, "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "latency_ms": 15.0, "timestamp": now},
            {"guardrail_name": "g2", "agent_name": "a1", "action": "block",
             "mechanism": "llm_judge", "latency_ms": 200.0, "timestamp": now},
            {"guardrail_name": "g2", "agent_name": "a1", "action": "pass",
             "mechanism": "llm_judge", "latency_ms": 300.0, "timestamp": now},
        ])

        resp = client.get(
            "/v1/guardrails/observability/latency",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        breakdown = resp.get_json()["latency"]
        assert len(breakdown) == 2

        mechanisms = {row["mechanism"] for row in breakdown}
        assert "regex" in mechanisms
        assert "llm_judge" in mechanisms

        for row in breakdown:
            assert "p50" in row
            assert "p95" in row
            assert "p99" in row
            assert "avg" in row
            assert "count" in row
            assert row["count"] == 2


# ============================================================================
# Top blocked patterns (GET /v1/guardrails/observability/top-blocked)
# ============================================================================


class TestObservabilityTopBlocked:
    def test_top_blocked_empty(self, app, client, db_session, auth_headers):
        """Top blocked with no events should return empty list."""
        resp = client.get(
            "/v1/guardrails/observability/top-blocked",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "patterns" in data
        assert isinstance(data["patterns"], list)
        assert len(data["patterns"]) == 0

    def test_top_blocked_returns_ranked_patterns(self, app, client, db_session, auth_headers):
        """Top blocked should rank patterns by frequency, excluding pass actions."""
        now = datetime.now(timezone.utc)
        _seed_events(app, [
            # "injection" pattern -- blocked 3 times
            {"guardrail_name": "g1", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "matched_pattern": "injection", "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "matched_pattern": "injection", "timestamp": now},
            {"guardrail_name": "g1", "agent_name": "a2", "action": "block",
             "mechanism": "regex", "matched_pattern": "injection", "timestamp": now},
            # "pii-ssn" pattern -- blocked 1 time
            {"guardrail_name": "g2", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "matched_pattern": "pii-ssn", "timestamp": now},
            # "bias" pattern -- warned 1 time
            {"guardrail_name": "g3", "agent_name": "a1", "action": "warn",
             "mechanism": "llm_judge", "matched_pattern": "bias", "timestamp": now},
            # pass action with pattern -- should NOT appear
            {"guardrail_name": "g1", "agent_name": "a1", "action": "pass",
             "mechanism": "regex", "matched_pattern": "injection", "timestamp": now},
        ])

        resp = client.get(
            "/v1/guardrails/observability/top-blocked",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        patterns = resp.get_json()["patterns"]
        assert len(patterns) == 3

        # First should be "injection" (count=3)
        assert patterns[0]["pattern"] == "injection"
        assert patterns[0]["count"] == 3
        assert patterns[0]["percentage"] > 0

        # Verify ordering: injection > pii-ssn/bias
        counts = [p["count"] for p in patterns]
        assert counts == sorted(counts, reverse=True)

    def test_top_blocked_respects_limit(self, app, client, db_session, auth_headers):
        """The limit parameter should cap the number of returned patterns."""
        now = datetime.now(timezone.utc)
        _seed_events(app, [
            {"guardrail_name": "g1", "agent_name": "a1", "action": "block",
             "mechanism": "regex", "matched_pattern": f"pattern-{i}",
             "timestamp": now}
            for i in range(10)
        ])

        resp = client.get(
            "/v1/guardrails/observability/top-blocked?limit=3",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        patterns = resp.get_json()["patterns"]
        assert len(patterns) <= 3


# ============================================================================
# Drift detection (GET /v1/guardrails/observability/drift)
# ============================================================================


class TestObservabilityDrift:
    def test_drift_empty(self, app, client, db_session, auth_headers):
        """Drift endpoint with no events should return empty list."""
        resp = client.get(
            "/v1/guardrails/observability/drift",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "drift" in data
        assert isinstance(data["drift"], list)
        assert len(data["drift"]) == 0

    def test_drift_detects_increase(self, app, client, db_session, auth_headers):
        """Drift should detect when recent block rate exceeds historical rate."""
        now = datetime.now(timezone.utc)
        guardrail_id = str(uuid.uuid4())
        window_days = 7

        # Historical events (older than window): mostly pass
        old_time = now - timedelta(days=window_days + 5)
        historical_events = [
            {"guardrail_id": guardrail_id, "guardrail_name": "drift-guard",
             "agent_name": "a1", "action": "pass", "mechanism": "regex",
             "timestamp": old_time}
            for _ in range(8)
        ] + [
            {"guardrail_id": guardrail_id, "guardrail_name": "drift-guard",
             "agent_name": "a1", "action": "block", "mechanism": "regex",
             "timestamp": old_time, "matched_pattern": "injection"}
            for _ in range(2)
        ]

        # Recent events (within window): mostly block
        recent_time = now - timedelta(days=1)
        recent_events = [
            {"guardrail_id": guardrail_id, "guardrail_name": "drift-guard",
             "agent_name": "a1", "action": "block", "mechanism": "regex",
             "timestamp": recent_time, "matched_pattern": "injection"}
            for _ in range(8)
        ] + [
            {"guardrail_id": guardrail_id, "guardrail_name": "drift-guard",
             "agent_name": "a1", "action": "pass", "mechanism": "regex",
             "timestamp": recent_time}
            for _ in range(2)
        ]

        _seed_events(app, historical_events + recent_events)

        resp = client.get(
            f"/v1/guardrails/observability/drift?window_days={window_days}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        drift = resp.get_json()["drift"]
        assert len(drift) >= 1

        guard_drift = [d for d in drift if d["guardrail_name"] == "drift-guard"]
        assert len(guard_drift) == 1
        d = guard_drift[0]

        # Historical block rate = 20%, recent = 80% => drift_pct = +60
        assert d["recent_block_rate"] > d["historical_block_rate"]
        assert d["drift_pct"] > 0
        assert d["trend"] == "up"

    def test_drift_filter_by_guardrail(self, app, client, db_session, auth_headers):
        """Drift should accept guardrail_id filter."""
        now = datetime.now(timezone.utc)
        gid1 = str(uuid.uuid4())
        gid2 = str(uuid.uuid4())

        _seed_events(app, [
            {"guardrail_id": gid1, "guardrail_name": "guard-1",
             "agent_name": "a1", "action": "block", "mechanism": "regex",
             "timestamp": now, "matched_pattern": "test"},
            {"guardrail_id": gid2, "guardrail_name": "guard-2",
             "agent_name": "a1", "action": "pass", "mechanism": "regex",
             "timestamp": now},
        ])

        resp = client.get(
            f"/v1/guardrails/observability/drift?guardrail_id={gid1}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        drift = resp.get_json()["drift"]
        for d in drift:
            assert d["guardrail_id"] == gid1
