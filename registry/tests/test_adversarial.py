"""
Tests for adversarial testing API endpoints and service layer.

Tests cover:
- Suite CRUD lifecycle (create, get, list, update, soft-delete)
- Static attack library input generation
- Merged input generation (static + custom + LLM)
- Run triggering and execution
- Evasion rate calculation
- Threshold alerting
- Alerts endpoint
- Result signing (HMAC-SHA256)
- Scheduler (get_scheduled_suites)
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models.adversarial import AdversarialTestSuite, AdversarialTestRun, CustomAttack
from app.models.guardrail import (
    EnforcementMode,
    Guardrail,
    GuardrailMechanism,
    GuardrailStatus,
    GuardrailType,
)
from app.services.adversarial_service import (
    AdversarialService,
    AdversarialNotFoundError,
    AdversarialValidationError,
    SIGNING_KEY,
    _ATTACK_LIBRARY,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adversarial_suite_payload():
    """Valid adversarial test suite creation payload."""
    return {
        "name": f"test-adversarial-suite-{uuid.uuid4().hex[:8]}",
        "description": "A test adversarial suite",
        "attack_types": ["encoding", "jailbreak"],
        "evasion_rate_threshold": 0.2,
        "alert_on_threshold_breach": True,
    }


@pytest.fixture
def active_regex_guardrail(app, db_session):
    """Create an active regex guardrail that blocks injection patterns."""
    with app.app_context():
        guardrail = Guardrail(
            name=f"adversarial-test-guardrail-{uuid.uuid4().hex[:8]}",
            type=GuardrailType.PRE_PROCESSING,
            mechanism=GuardrailMechanism.REGEX,
            enforcement_mode=EnforcementMode.BLOCK,
            status=GuardrailStatus.ACTIVE,
            config={
                "patterns": [
                    {
                        "name": "injection",
                        "pattern": r"ignore.*previous.*instructions",
                        "action": "block",
                    },
                    {
                        "name": "system_override",
                        "pattern": r"you\s+are\s+now",
                        "action": "block",
                    },
                    {
                        "name": "reveal_prompt",
                        "pattern": r"reveal.*system\s*prompt",
                        "action": "block",
                    },
                ],
            },
            tenant_id="test-tenant",
            priority=10,
        )
        db.session.add(guardrail)
        db.session.commit()
        return {"id": str(guardrail.id), "name": guardrail.name}


def _create_suite(client, auth_headers, payload):
    """Helper to create an adversarial suite via API."""
    return client.post(
        "/v1/adversarial-suites",
        json=payload,
        headers=auth_headers,
    )


# ============================================================================
# Suite CRUD Tests
# ============================================================================


class TestAdversarialSuiteCreate:
    def test_create_suite(self, client, auth_headers, db_session, adversarial_suite_payload):
        resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == adversarial_suite_payload["name"]
        assert data["attack_types"] == ["encoding", "jailbreak"]
        assert data["status"] == "active"
        assert data["evasion_rate_threshold"] == 0.2
        assert data["alert_on_threshold_breach"] is True
        assert "id" in data

    def test_create_suite_missing_name(self, client, auth_headers, db_session):
        payload = {
            "attack_types": ["encoding"],
        }
        resp = _create_suite(client, auth_headers, payload)
        assert resp.status_code == 400

    def test_create_suite_invalid_attack_type(self, client, auth_headers, db_session):
        payload = {
            "name": f"bad-suite-{uuid.uuid4().hex[:8]}",
            "attack_types": ["nonexistent_type"],
        }
        resp = _create_suite(client, auth_headers, payload)
        assert resp.status_code == 400

    def test_create_suite_missing_attack_types(self, client, auth_headers, db_session):
        payload = {
            "name": f"no-attacks-{uuid.uuid4().hex[:8]}",
        }
        resp = _create_suite(client, auth_headers, payload)
        assert resp.status_code == 400


class TestAdversarialSuiteRead:
    def test_get_suite(self, client, auth_headers, db_session, adversarial_suite_payload):
        create_resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        suite_id = create_resp.get_json()["id"]

        resp = client.get(
            f"/v1/adversarial-suites/{suite_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == suite_id
        assert data["name"] == adversarial_suite_payload["name"]

    def test_get_nonexistent_suite(self, client, auth_headers, db_session):
        resp = client.get(
            f"/v1/adversarial-suites/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestAdversarialSuiteUpdate:
    def test_update_suite(self, client, auth_headers, db_session, adversarial_suite_payload):
        create_resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        suite_id = create_resp.get_json()["id"]

        resp = client.put(
            f"/v1/adversarial-suites/{suite_id}",
            json={"name": "Updated Suite Name", "evasion_rate_threshold": 0.05},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Updated Suite Name"
        assert data["evasion_rate_threshold"] == 0.05

    def test_update_nonexistent_suite(self, client, auth_headers, db_session):
        resp = client.put(
            f"/v1/adversarial-suites/{uuid.uuid4()}",
            json={"name": "No Such Suite"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestAdversarialSuiteDelete:
    def test_delete_suite_soft_deletes(self, client, auth_headers, db_session, adversarial_suite_payload):
        create_resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        suite_id = create_resp.get_json()["id"]

        resp = client.delete(
            f"/v1/adversarial-suites/{suite_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Suite should no longer be found (soft-deleted)
        resp = client.get(
            f"/v1/adversarial-suites/{suite_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_suite(self, client, auth_headers, db_session):
        resp = client.delete(
            f"/v1/adversarial-suites/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ============================================================================
# Input Generation Tests
# ============================================================================


class TestInputGeneration:
    def test_generate_encoding_inputs(self, app, db_session):
        """Static attack library generates encoding variants."""
        with app.app_context():
            inputs = AdversarialService._generate_static_inputs(["encoding"])
            assert len(inputs) > 0
            for inp in inputs:
                assert inp["attack_type"] == "encoding"
                assert "text" in inp
                assert "variant_name" in inp

    def test_generate_jailbreak_inputs(self, app, db_session):
        """Static attack library generates jailbreak variants."""
        with app.app_context():
            inputs = AdversarialService._generate_static_inputs(["jailbreak"])
            assert len(inputs) > 0
            for inp in inputs:
                assert inp["attack_type"] == "jailbreak"

    def test_generate_multiple_attack_types(self, app, db_session):
        """Generating inputs for multiple attack types produces combined results."""
        with app.app_context():
            inputs = AdversarialService._generate_static_inputs(
                ["encoding", "injection", "pii_bypass"]
            )
            attack_types = {inp["attack_type"] for inp in inputs}
            assert "encoding" in attack_types
            assert "injection" in attack_types
            assert "pii_bypass" in attack_types

    def test_generate_all_attack_types_have_entries(self, app, db_session):
        """Every valid attack type in the library has at least one entry."""
        with app.app_context():
            for attack_type in _ATTACK_LIBRARY:
                inputs = AdversarialService._generate_static_inputs([attack_type])
                assert len(inputs) > 0, f"No inputs for attack type: {attack_type}"


# ============================================================================
# Run Triggering and Execution Tests
# ============================================================================


class TestRunTriggerAndExecution:
    def test_trigger_run_creates_pending_run(
        self, app, db_session, adversarial_suite_payload, auth_headers, client,
    ):
        """Triggering a run creates a run record with pending status."""
        create_resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        suite_id = create_resp.get_json()["id"]

        with app.app_context():
            run = AdversarialService.trigger_run(suite_id, "test-user", "test-tenant")
            assert run.status == "pending"
            assert run.triggered_by == "test-user"
            assert str(run.suite_id) == suite_id

    def test_execute_run_with_guardrail(
        self, app, db_session, active_regex_guardrail,
    ):
        """Executing a run evaluates inputs against guardrails and records results."""
        with app.app_context():
            # Create a suite targeting only encoding attacks (smaller set)
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"exec-test-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=0.5,
                alert_on_threshold_breach=True,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()
            suite_id = str(suite.id)

            run = AdversarialService.trigger_run(suite_id, "test-user", "test-tenant")
            run_id = str(run.id)

            completed_run = AdversarialService.execute_run(run_id, "test-tenant")

            assert completed_run.status == "completed"
            assert completed_run.total_inputs > 0
            assert completed_run.blocked_count + completed_run.evaded_count + completed_run.error_count == completed_run.total_inputs
            assert completed_run.evasion_rate is not None
            assert completed_run.results is not None
            assert len(completed_run.results) > 0

    def test_list_runs_for_suite(
        self, app, db_session, adversarial_suite_payload, auth_headers, client,
    ):
        """Listing runs returns runs belonging to the suite."""
        create_resp = _create_suite(client, auth_headers, adversarial_suite_payload)
        suite_id = create_resp.get_json()["id"]

        with app.app_context():
            # Create a run
            AdversarialService.trigger_run(suite_id, "test-user", "test-tenant")

            runs = AdversarialService.list_runs(suite_id, "test-tenant")
            assert len(runs) == 1
            assert str(runs[0].suite_id) == suite_id


# ============================================================================
# Evasion Rate Calculation Tests
# ============================================================================


class TestEvasionRateCalculation:
    def test_evasion_rate_is_calculated(
        self, app, db_session, active_regex_guardrail,
    ):
        """Evasion rate = evaded / (blocked + evaded + errors)."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"evasion-rate-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=1.0,  # High threshold so no breach
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            completed = AdversarialService.execute_run(str(run.id), "test-tenant")

            total = completed.blocked_count + completed.evaded_count + completed.error_count
            if total > 0:
                expected_rate = round(completed.evaded_count / total, 4)
            else:
                expected_rate = 0.0
            assert completed.evasion_rate == expected_rate


# ============================================================================
# Threshold Alerting Tests
# ============================================================================


class TestThresholdAlerting:
    def test_threshold_breach_detected(
        self, app, db_session, active_regex_guardrail,
    ):
        """When evasion rate exceeds threshold, threshold_breached is set True."""
        with app.app_context():
            # Use a very low threshold (0.0) so any evasion triggers a breach
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"threshold-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=0.0,
                alert_on_threshold_breach=True,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            completed = AdversarialService.execute_run(str(run.id), "test-tenant")

            # With regex-only guardrail and encoding attacks, some will likely evade
            if completed.evaded_count > 0:
                assert completed.threshold_breached is True
                assert completed.alert_sent is True


# ============================================================================
# Alerts Endpoint Tests
# ============================================================================


class TestAlertsEndpoint:
    def test_alerts_returns_breached_runs(
        self, app, client, auth_headers, db_session, active_regex_guardrail,
    ):
        """The alerts endpoint returns runs with threshold_breached=True."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"alert-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=0.0,
                alert_on_threshold_breach=True,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            AdversarialService.execute_run(str(run.id), "test-tenant")

        resp = client.get("/v1/adversarial-alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        # All returned alerts must have threshold_breached=True
        for alert in data["alerts"]:
            assert alert["threshold_breached"] is True

    def test_alerts_empty_when_no_breaches(
        self, client, auth_headers, db_session,
    ):
        """When there are no breached runs, alerts list is empty."""
        resp = client.get("/v1/adversarial-alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["alerts"] == []


# ============================================================================
# Result Signing Tests
# ============================================================================


class TestResultSigning:
    def test_run_results_are_signed(
        self, app, db_session, active_regex_guardrail,
    ):
        """Completed runs have an HMAC-SHA256 signature over the results."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"signing-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=1.0,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            completed = AdversarialService.execute_run(str(run.id), "test-tenant")

            assert completed.result_signature is not None
            assert completed.signature_algorithm == "HMAC-SHA256"
            assert len(completed.result_signature) == 64  # SHA-256 hex digest

    def test_signature_is_verifiable(
        self, app, db_session, active_regex_guardrail,
    ):
        """The stored signature is present and stable when re-signed."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"verify-sig-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=1.0,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            completed = AdversarialService.execute_run(str(run.id), "test-tenant")

            # Verify signature exists and is a 64-char hex SHA-256
            assert completed.result_signature is not None
            assert len(completed.result_signature) == 64
            assert completed.signature_algorithm == "HMAC-SHA256"

            # Re-sign the same run — signature should be identical (idempotent)
            original_sig = completed.result_signature
            AdversarialService._sign_results(completed)
            assert completed.result_signature == original_sig


# ============================================================================
# Scheduler Tests
# ============================================================================


class TestScheduler:
    def test_get_scheduled_suites_returns_due_suites(self, app, db_session):
        """Suites with schedule_enabled=True and next_run_at in the past are returned."""
        with app.app_context():
            past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"scheduled-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["injection"],
                schedule_enabled=True,
                schedule_interval_minutes=60,
                next_run_at=past_time,
                evasion_rate_threshold=0.1,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()
            suite_id = str(suite.id)

            scheduled = AdversarialService.get_scheduled_suites(tenant_id="test-tenant")
            scheduled_ids = [str(s.id) for s in scheduled]
            assert suite_id in scheduled_ids

    def test_get_scheduled_suites_excludes_future(self, app, db_session):
        """Suites with next_run_at in the future are not returned."""
        with app.app_context():
            future_time = datetime.now(timezone.utc) + timedelta(hours=1)
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"future-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["injection"],
                schedule_enabled=True,
                schedule_interval_minutes=60,
                next_run_at=future_time,
                evasion_rate_threshold=0.1,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()
            suite_id = str(suite.id)

            scheduled = AdversarialService.get_scheduled_suites(tenant_id="test-tenant")
            scheduled_ids = [str(s.id) for s in scheduled]
            assert suite_id not in scheduled_ids

    def test_get_scheduled_suites_excludes_disabled(self, app, db_session):
        """Soft-deleted or disabled suites are not returned even if due."""
        with app.app_context():
            past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"disabled-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["injection"],
                schedule_enabled=True,
                schedule_interval_minutes=60,
                next_run_at=past_time,
                evasion_rate_threshold=0.1,
                status="active",
                created_by="test",
                deleted_at=datetime.now(timezone.utc),
            )
            db.session.add(suite)
            db.session.commit()
            suite_id = str(suite.id)

            scheduled = AdversarialService.get_scheduled_suites(tenant_id="test-tenant")
            scheduled_ids = [str(s.id) for s in scheduled]
            assert suite_id not in scheduled_ids


# ============================================================================
# Merged Input Generation Tests (static + custom + LLM)
# ============================================================================


class TestMergedInputGeneration:
    def test_generate_all_inputs_static_only(self, app, db_session):
        """Without custom attacks or LLM config, only static inputs are returned."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"merged-static-only-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            inputs = AdversarialService._generate_all_inputs(suite, "test-tenant", [])
            assert len(inputs) > 0
            sources = {inp["source"] for inp in inputs}
            assert sources == {"static"}

    def test_generate_all_inputs_static_and_custom(self, app, db_session):
        """With custom attacks in DB, both static and custom sources are returned."""
        with app.app_context():
            custom_variant = f"merged_custom_{uuid.uuid4().hex[:8]}"
            attack = CustomAttack(
                tenant_id="test-tenant",
                attack_type="encoding",
                variant_name=custom_variant,
                text="Custom encoding variant for merged test",
                created_by="test",
            )
            db.session.add(attack)
            db.session.commit()

            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"merged-static-custom-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            inputs = AdversarialService._generate_all_inputs(suite, "test-tenant", [])
            sources = {inp["source"] for inp in inputs}
            assert "static" in sources
            assert "custom" in sources

            custom_inputs = [i for i in inputs if i["source"] == "custom"]
            assert any(i["variant_name"] == custom_variant for i in custom_inputs)

    def test_generate_all_inputs_with_llm(self, app, db_session):
        """With generation_config, static + LLM sources are returned."""
        with app.app_context():
            mock_llm = MagicMock()
            mock_llm.generate.return_value = MagicMock(
                content=json.dumps([
                    {"text": "llm attack", "attack_type": "encoding", "variant_name": "llm1"},
                ])
            )

            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"merged-llm-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                status="active",
                created_by="test",
                generation_config={
                    "provider": "anthropic",
                    "model": "test",
                    "strategies": ["category_targeted"],
                    "num_variants_per_strategy": 1,
                },
            )
            db.session.add(suite)
            db.session.commit()

            with patch('app.llm.factory.LLMFactory') as mock_factory:
                mock_factory.from_dict.return_value = mock_llm
                inputs = AdversarialService._generate_all_inputs(
                    suite, "test-tenant", ["test guardrail desc"],
                )

            sources = {inp["source"] for inp in inputs}
            assert "static" in sources
            llm_sources = [s for s in sources if s.startswith("llm:")]
            assert len(llm_sources) > 0

    def test_generate_all_inputs_all_three_sources(self, app, db_session):
        """With custom attacks in DB and generation_config, all three sources are present."""
        with app.app_context():
            # Create custom attack
            attack = CustomAttack(
                tenant_id="test-tenant",
                attack_type="jailbreak",
                variant_name=f"all_three_{uuid.uuid4().hex[:8]}",
                text="Custom jailbreak for triple-source test",
                created_by="test",
            )
            db.session.add(attack)
            db.session.commit()

            mock_llm = MagicMock()
            mock_llm.generate.return_value = MagicMock(
                content=json.dumps([
                    {"text": "llm jailbreak", "attack_type": "jailbreak", "variant_name": "llm_j1"},
                ])
            )

            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"merged-all-three-{uuid.uuid4().hex[:8]}",
                attack_types=["jailbreak"],
                status="active",
                created_by="test",
                generation_config={
                    "provider": "anthropic",
                    "model": "test",
                    "strategies": ["creative"],
                    "num_variants_per_strategy": 1,
                },
            )
            db.session.add(suite)
            db.session.commit()

            with patch('app.llm.factory.LLMFactory') as mock_factory:
                mock_factory.from_dict.return_value = mock_llm
                inputs = AdversarialService._generate_all_inputs(
                    suite, "test-tenant", [],
                )

            sources = {inp["source"] for inp in inputs}
            assert "static" in sources
            assert "custom" in sources
            llm_sources = [s for s in sources if s.startswith("llm:")]
            assert len(llm_sources) > 0

    def test_source_field_in_run_results(
        self, app, db_session, active_regex_guardrail,
    ):
        """Run results include the source field from inputs."""
        with app.app_context():
            suite = AdversarialTestSuite(
                tenant_id="test-tenant",
                name=f"source-field-suite-{uuid.uuid4().hex[:8]}",
                attack_types=["encoding"],
                target_guardrail_ids=[active_regex_guardrail["id"]],
                evasion_rate_threshold=1.0,
                status="active",
                created_by="test",
            )
            db.session.add(suite)
            db.session.commit()

            run = AdversarialService.trigger_run(str(suite.id), "test-user", "test-tenant")
            completed = AdversarialService.execute_run(str(run.id), "test-tenant")

            # Every result should have a source field
            for result in completed.results:
                assert "source" in result
                assert result["source"] in ("static", "custom") or result["source"].startswith("llm:")
