"""
Pytest fixtures for Registry tests.

Provides common fixtures for testing the agent submission API and related endpoints.
"""

import pytest
import uuid
from typing import Generator, Dict, Any

from app import create_app, db
from app.models import GuardrailProfile
from app.models.user import User, Group, GroupType
from app.api.auth import create_token


@pytest.fixture(scope='session')
def app():
    """Create application for the tests."""
    import os
    app = create_app('testing')
    app.config['TESTING'] = True
    # Derive test DB URL from DATABASE_URL (works in both Docker Compose and K8s)
    base_url = os.environ.get('DATABASE_URL', 'postgresql://registry:registry@db:5432/registry')
    test_db_url = os.environ.get('TEST_DATABASE_URL', base_url.rsplit('/', 1)[0] + '/registry_test')
    app.config['SQLALCHEMY_DATABASE_URI'] = test_db_url

    with app.app_context():
        # Import all models to ensure they're registered with SQLAlchemy
        from app.models import (
            Agent, AgentVersion, Capability, GuardrailProfile,
            SecurityPolicy, SecurityTestCase, SecurityScan, SecurityScanResult,
            EvaluationSuite, EvaluationTestCase, Evaluation, EvaluationResult,
            AuditLog,
            Guardrail, GuardrailAssignment, GuardrailTestRun,
            CustomAttack,
        )
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create a fresh database session for each test."""
    with app.app_context():
        db.create_all()
        yield db
        db.session.rollback()
        # Clean up all tables
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


@pytest.fixture
def admin_user(app, db_session):
    """Create an admin user with JWT-compatible group membership."""
    with app.app_context():
        group = Group(
            name=f'admins-{uuid.uuid4().hex[:8]}',
            group_type=GroupType.ADMINISTRATOR,
        )
        db.session.add(group)
        db.session.flush()

        user = User(
            username=f'testadmin-{uuid.uuid4().hex[:8]}',
            email=f'admin-{uuid.uuid4().hex[:8]}@test.com',
            first_name='Test',
            last_name='Admin',
            is_active=True,
        )
        user.set_password('testpass')
        user.groups = [group]
        db.session.add(user)
        db.session.commit()

        return {'id': str(user.id), 'username': user.username}


@pytest.fixture
def auth_headers(app, admin_user) -> Dict[str, str]:
    """Authentication headers with a valid admin JWT token."""
    with app.app_context():
        user = db.session.get(User, admin_user['id'])
        token = create_token(user)
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-Tenant-ID': 'test-tenant',
        }


@pytest.fixture
def valid_agent_payload() -> Dict[str, Any]:
    """A valid agent creation payload with all required fields."""
    return {
        "name": "test-agent",
        "version": "1.0.0",
        "description": "A test agent for automated testing",
        "owner_id": "owner-123",
        "team_id": "team-456",
        "contact_email": "test@example.com",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {
                "name": "test-capability",
                "description": "A capability for testing purposes"
            }
        ],
        "endpoint": {
            "type": "langchain",
            "url": "https://example.com/agent/invoke",
            "auth_method": "api_key",
            "timeout_ms": 30000,
            "agent_protocol": "A2A"
        }
    }


@pytest.fixture
def valid_agent_payload_with_tools() -> Dict[str, Any]:
    """A valid agent payload including tool dependencies."""
    return {
        "name": "agent-with-tools",
        "version": "1.0.0",
        "description": "Agent with tool dependencies",
        "owner_id": "owner-123",
        "team_id": "team-456",
        "contact_email": "tools@example.com",
        "classification": "internal",
        "data_sensitivity": "pii",
        "risk_tier": "medium",
        "capabilities": [
            {
                "name": "data-lookup",
                "description": "Look up data from various sources",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}}
            }
        ],
        "endpoint": {
            "type": "langgraph",
            "url": "https://api.example.com/agent",
            "auth_method": "oauth2",
            "timeout_ms": 60000
        },
        "tools": [
            {"tool_id": "tool-database-query", "required": True},
            {"tool_id": "tool-api-call", "required": False}
        ]
    }


@pytest.fixture
def valid_agent_payload_with_relationships() -> Dict[str, Any]:
    """A valid agent payload with upstream/downstream agent relationships."""
    return {
        "name": "orchestrator-agent",
        "version": "2.0.0",
        "description": "Orchestration agent that coordinates other agents",
        "owner_id": "owner-456",
        "team_id": "team-789",
        "contact_email": "orchestrator@example.com",
        "classification": "confidential",
        "data_sensitivity": "financial",
        "risk_tier": "high",
        "capabilities": [
            {
                "name": "orchestration",
                "description": "Coordinates workflow between multiple agents"
            },
            {
                "name": "decision-making",
                "description": "Makes routing decisions based on context"
            }
        ],
        "endpoint": {
            "type": "crewai",
            "url": "https://orchestrator.example.com/invoke",
            "auth_method": "mtls",
            "timeout_ms": 120000,
            "agent_protocol": "A2A"
        },
        "resource_quota": {
            "max_tokens_per_request": 4000,
            "max_requests_per_minute": 100,
            "max_cost_per_day_usd": "50.00"
        }
    }


@pytest.fixture
def valid_agent_payload_high_risk() -> Dict[str, Any]:
    """A valid high-risk agent payload for testing extended evaluations."""
    return {
        "name": "high-risk-agent",
        "version": "1.0.0",
        "description": "A high-risk agent handling sensitive data",
        "owner_id": "secure-owner",
        "team_id": "security-team",
        "contact_email": "security@example.com",
        "classification": "restricted",
        "data_sensitivity": "secret",
        "risk_tier": "critical",
        "capabilities": [
            {
                "name": "sensitive-data-processing",
                "description": "Process highly sensitive data"
            }
        ],
        "endpoint": {
            "type": "custom",
            "url": "https://secure.internal.example.com/agent",
            "auth_method": "mtls",
            "timeout_ms": 60000,
            "agent_protocol": "A2A"
        }
    }


@pytest.fixture
def minimal_valid_payload() -> Dict[str, Any]:
    """Minimal valid payload with only required fields."""
    return {
        "name": "minimal-agent",
        "version": "0.1.0",
        "description": "Minimal agent",
        "owner_id": "owner",
        "team_id": "team",
        "contact_email": "min@example.com",
        "classification": "public",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {"name": "basic", "description": "Basic capability"}
        ],
        "endpoint": {
            "type": "openai",
            "url": "https://api.example.com/v1",
            "auth_method": "api_key"
        }
    }


@pytest.fixture
def guardrail_profile(app, db_session) -> Dict[str, Any]:
    """Create a test guardrail profile. Returns dict with profile data to avoid detached session issues."""
    with app.app_context():
        profile = GuardrailProfile(
            id="test-guardrail-profile",
            name="Test Guardrail Profile",
            description="A guardrail profile for testing",
            config={"max_output_tokens": 1000, "content_filter": True},
            is_active=True
        )
        db_session.session.add(profile)
        db_session.session.commit()
        # Return dict to avoid DetachedInstanceError
        return {"id": profile.id, "name": profile.name, "is_active": profile.is_active}


@pytest.fixture
def inactive_guardrail_profile(app, db_session) -> Dict[str, Any]:
    """Create an inactive guardrail profile. Returns dict with profile data to avoid detached session issues."""
    with app.app_context():
        profile = GuardrailProfile(
            id="inactive-profile",
            name="Inactive Profile",
            description="An inactive guardrail profile",
            config={},
            is_active=False
        )
        db_session.session.add(profile)
        db_session.session.commit()
        # Return dict to avoid DetachedInstanceError
        return {"id": profile.id, "name": profile.name, "is_active": profile.is_active}


def unique_agent_name(base_name: str = "test-agent") -> str:
    """Generate a unique agent name to avoid conflicts."""
    return f"{base_name}-{uuid.uuid4().hex[:8]}"
