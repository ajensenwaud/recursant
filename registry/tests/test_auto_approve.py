"""
Tests for auto-approval governance logic.

Verifies that the evaluation service correctly auto-approves agents
based on GovernanceConfig settings when all evaluations pass.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app import db
from app.models.agent import (
    Agent, AgentStatus, Classification, DataSensitivity,
    RiskTier, EndpointType, AuthMethod, GovernanceConfig,
)
from app.models.evaluation import (
    Evaluation, EvaluationSuite, EvaluationStatus, LLMProvider,
)


@pytest.fixture
def test_agent(app, db_session):
    """Create an agent in EVALUATING status for testing."""
    with app.app_context():
        agent = Agent(
            name=f"auto-approve-test-{uuid.uuid4().hex[:8]}",
            version="1.0.0",
            description="Agent for auto-approve testing",
            owner_id="test-owner",
            team_id="test-team",
            contact_email="test@example.com",
            classification=Classification.INTERNAL,
            data_sensitivity=DataSensitivity.NONE,
            risk_tier=RiskTier.LOW,
            endpoint_type=EndpointType.LANGCHAIN,
            endpoint_url="https://example.com/agent",
            endpoint_auth_method=AuthMethod.API_KEY,
            endpoint_timeout_ms=30000,
            status=AgentStatus.EVALUATING,
            tenant_id="test-tenant",
        )
        db.session.add(agent)
        db.session.commit()
        return {"id": str(agent.id), "name": agent.name, "tenant_id": agent.tenant_id}


@pytest.fixture
def test_suite(app, db_session):
    """Create a minimal evaluation suite."""
    with app.app_context():
        suite = EvaluationSuite(
            name=f"test-suite-{uuid.uuid4().hex[:8]}",
            description="Test suite",
            version="1.0.0",
            applicable_risk_tiers=["low", "medium"],
            is_baseline=True,
            judge_provider=LLMProvider.OPENAI,
            judge_model="gpt-4",
            judge_config={"provider": "openai", "model": "gpt-4"},
            is_active=True,
            tenant_id="test-tenant",
        )
        db.session.add(suite)
        db.session.commit()
        return {"id": str(suite.id)}


def create_completed_evaluation(agent_id, suite_id, all_blocking_passed=True,
                                 triggered_by="automatic"):
    """Helper: create a completed evaluation record."""
    evaluation = Evaluation(
        agent_id=agent_id,
        suite_id=suite_id,
        status=EvaluationStatus.COMPLETED,
        total_tests=3,
        passed_count=3 if all_blocking_passed else 1,
        failed_count=0 if all_blocking_passed else 2,
        error_count=0,
        weighted_score=Decimal("0.9") if all_blocking_passed else Decimal("0.3"),
        all_blocking_passed=all_blocking_passed,
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


def apply_post_evaluation_status(agent, evaluation):
    """Simulate the status transition logic from evaluation_service.py.

    This mirrors the logic at lines 316-353 of evaluation_service.py
    so we can test the auto-approval branching without needing LLM calls.
    """
    from sqlalchemy import and_
    from app.models.agent import GovernanceConfig

    all_blocking_passed = evaluation.all_blocking_passed

    other_in_progress = Evaluation.query.filter(
        and_(
            Evaluation.agent_id == agent.id,
            Evaluation.id != evaluation.id,
            Evaluation.status.in_([EvaluationStatus.PENDING, EvaluationStatus.RUNNING])
        )
    ).count()

    if other_in_progress == 0:
        batch_evals = Evaluation.query.filter(
            and_(
                Evaluation.agent_id == agent.id,
                Evaluation.triggered_by == evaluation.triggered_by,
                Evaluation.status.in_([EvaluationStatus.COMPLETED, EvaluationStatus.FAILED])
            )
        ).all()

        all_passed = all_blocking_passed and all(
            e.all_blocking_passed for e in batch_evals if e.id != evaluation.id
        )

        if all_passed:
            gov_config = GovernanceConfig.query.filter_by(
                tenant_id=agent.tenant_id
            ).first()
            if (gov_config and gov_config.auto_approve_enabled and
                    (not gov_config.auto_approve_risk_tiers or
                     agent.risk_tier.value in gov_config.auto_approve_risk_tiers)):
                agent.status = AgentStatus.APPROVED
            else:
                agent.status = AgentStatus.PENDING_APPROVAL
        else:
            agent.status = AgentStatus.EVALUATION_FAILED

        agent.updated_at = datetime.now(timezone.utc)

    db.session.commit()


class TestAutoApproveEnabled:
    """Tests for when auto-approve is enabled."""

    def test_auto_approve_when_enabled_and_all_tiers(self, app, db_session, test_agent, test_suite):
        """Agent should be APPROVED when auto-approve is on with empty risk tiers (all eligible)."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=True,
                auto_approve_risk_tiers=[],
            )
            db.session.add(config)
            db.session.commit()

            agent = db.session.get(Agent, test_agent["id"])
            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=True,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.APPROVED

    def test_auto_approve_matching_risk_tier(self, app, db_session, test_agent, test_suite):
        """Agent should be APPROVED when its risk tier is in the eligible list."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=True,
                auto_approve_risk_tiers=["low", "medium"],
            )
            db.session.add(config)
            db.session.commit()

            agent = db.session.get(Agent, test_agent["id"])
            assert agent.risk_tier == RiskTier.LOW  # matches ["low", "medium"]

            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=True,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.APPROVED

    def test_no_auto_approve_when_risk_tier_not_eligible(self, app, db_session, test_suite):
        """Agent should go to PENDING_APPROVAL when its risk tier is not in the eligible list."""
        with app.app_context():
            agent = Agent(
                name=f"high-risk-{uuid.uuid4().hex[:8]}",
                version="1.0.0",
                description="High risk agent",
                owner_id="test-owner",
                team_id="test-team",
                contact_email="test@example.com",
                classification=Classification.RESTRICTED,
                data_sensitivity=DataSensitivity.PII,
                risk_tier=RiskTier.HIGH,
                endpoint_type=EndpointType.LANGCHAIN,
                endpoint_url="https://example.com/agent",
                endpoint_auth_method=AuthMethod.API_KEY,
                status=AgentStatus.EVALUATING,
                tenant_id="test-tenant",
            )
            db.session.add(agent)

            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=True,
                auto_approve_risk_tiers=["low"],  # Only low tier
            )
            db.session.add(config)
            db.session.commit()

            evaluation = create_completed_evaluation(
                agent_id=str(agent.id),
                suite_id=test_suite["id"],
                all_blocking_passed=True,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.PENDING_APPROVAL


class TestAutoApproveDisabled:
    """Tests for when auto-approve is disabled."""

    def test_pending_approval_when_disabled(self, app, db_session, test_agent, test_suite):
        """Agent should go to PENDING_APPROVAL when auto-approve is disabled."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=False,
                auto_approve_risk_tiers=[],
            )
            db.session.add(config)
            db.session.commit()

            agent = db.session.get(Agent, test_agent["id"])
            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=True,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.PENDING_APPROVAL

    def test_pending_approval_when_no_config(self, app, db_session, test_agent, test_suite):
        """Agent should go to PENDING_APPROVAL when no GovernanceConfig exists."""
        with app.app_context():
            agent = db.session.get(Agent, test_agent["id"])
            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=True,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.PENDING_APPROVAL


class TestEvaluationFailure:
    """Tests for when evaluations fail."""

    def test_evaluation_failed_when_blocking_test_fails(self, app, db_session, test_agent, test_suite):
        """Agent should be EVALUATION_FAILED when blocking tests fail."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=True,
                auto_approve_risk_tiers=[],
            )
            db.session.add(config)
            db.session.commit()

            agent = db.session.get(Agent, test_agent["id"])
            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=False,
            )

            apply_post_evaluation_status(agent, evaluation)

            assert agent.status == AgentStatus.EVALUATION_FAILED

    def test_no_auto_approve_when_evaluation_fails(self, app, db_session, test_agent, test_suite):
        """Even with auto-approve enabled, failed evaluations should not approve."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id="test-tenant",
                auto_approve_enabled=True,
                auto_approve_risk_tiers=[],
            )
            db.session.add(config)
            db.session.commit()

            agent = db.session.get(Agent, test_agent["id"])
            evaluation = create_completed_evaluation(
                agent_id=test_agent["id"],
                suite_id=test_suite["id"],
                all_blocking_passed=False,
            )

            apply_post_evaluation_status(agent, evaluation)

            # Should never be APPROVED
            assert agent.status != AgentStatus.APPROVED
            assert agent.status == AgentStatus.EVALUATION_FAILED
