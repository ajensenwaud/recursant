"""
Tests for governance configuration API endpoints.

Tests GET/PUT /v1/governance/config, access control, validation.
"""

import json
import uuid

import pytest

from app import create_app, db
from app.models.agent import GovernanceConfig
from app.models.user import User, Group, GroupType
from app.api.auth import create_token


@pytest.fixture
def regular_user(app, db_session):
    """Create a non-admin user for access-control tests."""
    with app.app_context():
        group = Group(
            name=f'users-{uuid.uuid4().hex[:8]}',
            group_type=GroupType.USER,
        )
        db.session.add(group)
        db.session.flush()

        user = User(
            username=f'testuser-{uuid.uuid4().hex[:8]}',
            email=f'user-{uuid.uuid4().hex[:8]}@test.com',
            first_name='Test',
            last_name='User',
            is_active=True,
        )
        user.set_password('testpass')
        user.groups = [group]
        db.session.add(user)
        db.session.commit()

        return {'id': str(user.id), 'username': user.username}


@pytest.fixture
def user_headers(app, regular_user):
    """Auth headers with a valid non-admin JWT token."""
    with app.app_context():
        user = db.session.get(User, regular_user['id'])
        token = create_token(user)
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-Tenant-ID': 'test-tenant',
        }


class TestGetGovernanceConfig:
    """Tests for GET /v1/governance/config."""

    def test_get_config_returns_defaults_when_none_exists(self, client, db_session, auth_headers):
        """When no GovernanceConfig exists for the tenant, return defaults."""
        response = client.get('/v1/governance/config', headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_enabled'] is False
        assert data['auto_approve_risk_tiers'] == []

    def test_get_config_returns_existing_config(self, client, app, db_session, auth_headers):
        """When a config exists, return its values."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id='test-tenant',
                auto_approve_enabled=True,
                auto_approve_risk_tiers=['low', 'medium'],
            )
            db.session.add(config)
            db.session.commit()

        response = client.get('/v1/governance/config', headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_enabled'] is True
        assert data['auto_approve_risk_tiers'] == ['low', 'medium']

    def test_get_config_requires_auth(self, client, db_session):
        """Unauthenticated requests should be rejected."""
        response = client.get('/v1/governance/config')
        assert response.status_code == 401

    def test_get_config_requires_admin_role(self, client, db_session, user_headers):
        """Non-admin users should be forbidden."""
        response = client.get('/v1/governance/config', headers=user_headers)
        assert response.status_code == 403


class TestUpdateGovernanceConfig:
    """Tests for PUT /v1/governance/config."""

    def test_update_creates_config_if_none_exists(self, client, db_session, auth_headers):
        """PUT should create a new config if none exists for the tenant."""
        response = client.put(
            '/v1/governance/config',
            data=json.dumps({'auto_approve_enabled': True}),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_enabled'] is True

    def test_update_enables_auto_approve(self, client, app, db_session, auth_headers):
        """Enable auto-approve and verify it persists."""
        with app.app_context():
            config = GovernanceConfig(tenant_id='test-tenant', auto_approve_enabled=False)
            db.session.add(config)
            db.session.commit()

        response = client.put(
            '/v1/governance/config',
            data=json.dumps({'auto_approve_enabled': True}),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_enabled'] is True

        # Verify the change persisted
        get_response = client.get('/v1/governance/config', headers=auth_headers)
        assert get_response.get_json()['auto_approve_enabled'] is True

    def test_update_risk_tiers(self, client, app, db_session, auth_headers):
        """Update auto_approve_risk_tiers and verify."""
        with app.app_context():
            config = GovernanceConfig(tenant_id='test-tenant')
            db.session.add(config)
            db.session.commit()

        response = client.put(
            '/v1/governance/config',
            data=json.dumps({
                'auto_approve_enabled': True,
                'auto_approve_risk_tiers': ['low', 'medium'],
            }),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_risk_tiers'] == ['low', 'medium']

    def test_update_rejects_invalid_risk_tiers(self, client, app, db_session, auth_headers):
        """Invalid risk tier values should be rejected."""
        with app.app_context():
            config = GovernanceConfig(tenant_id='test-tenant')
            db.session.add(config)
            db.session.commit()

        response = client.put(
            '/v1/governance/config',
            data=json.dumps({
                'auto_approve_risk_tiers': ['low', 'invalid_tier'],
            }),
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_update_rejects_non_list_risk_tiers(self, client, app, db_session, auth_headers):
        """Risk tiers must be a list."""
        with app.app_context():
            config = GovernanceConfig(tenant_id='test-tenant')
            db.session.add(config)
            db.session.commit()

        response = client.put(
            '/v1/governance/config',
            data=json.dumps({
                'auto_approve_risk_tiers': 'low',
            }),
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_update_requires_body(self, client, db_session, auth_headers):
        """PUT without a body should return 400."""
        response = client.put(
            '/v1/governance/config',
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_update_requires_auth(self, client, db_session):
        """Unauthenticated updates should be rejected."""
        response = client.put(
            '/v1/governance/config',
            data=json.dumps({'auto_approve_enabled': True}),
            content_type='application/json',
        )
        assert response.status_code == 401

    def test_update_requires_admin_role(self, client, db_session, user_headers):
        """Non-admin users should be forbidden from updating."""
        response = client.put(
            '/v1/governance/config',
            data=json.dumps({'auto_approve_enabled': True}),
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_update_empty_risk_tiers_means_all_eligible(self, client, app, db_session, auth_headers):
        """Empty risk_tiers list means all tiers are eligible."""
        with app.app_context():
            config = GovernanceConfig(
                tenant_id='test-tenant',
                auto_approve_risk_tiers=['low'],
            )
            db.session.add(config)
            db.session.commit()

        response = client.put(
            '/v1/governance/config',
            data=json.dumps({'auto_approve_risk_tiers': []}),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['auto_approve_risk_tiers'] == []
