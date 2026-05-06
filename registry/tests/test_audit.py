"""
Test cases for Audit Logging.

Verifies that API actions produce immutable audit log entries,
and that audit log endpoints enforce admin-only access.
"""

import json
import uuid

import pytest

from app import db
from app.api.auth import create_token
from app.models.user import User, Group, GroupType
from app.models.audit import AuditLog


# admin_user, auth_headers, and valid_agent_payload come from conftest.py.
# We alias auth_headers -> admin_headers so test signatures stay readable.
@pytest.fixture
def admin_headers(auth_headers):
    """Alias for the shared auth_headers fixture (admin JWT)."""
    return auth_headers


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


class TestAuditLogCreation:
    """Verify that API actions generate audit log entries."""

    def test_create_agent_creates_audit_entry(self, app, client, db_session,
                                               admin_headers, valid_agent_payload):
        """Creating an agent should produce an agent.created audit entry."""
        response = client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )
        assert response.status_code == 201
        agent_data = response.get_json()

        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='agent.created',
                resource_id=agent_data['id'],
                tenant_id='test-tenant',
            ).first()

            assert entry is not None
            assert entry.resource_type == 'agent'
            assert entry.resource_name == valid_agent_payload['name']
            assert entry.username is not None
            assert entry.ip_address is not None

    def test_delete_agent_creates_audit_entry(self, app, client, db_session,
                                               admin_headers, valid_agent_payload):
        """Deleting an agent should produce an agent.deleted audit entry."""
        resp = client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )
        agent_id = resp.get_json()['id']

        resp = client.delete(f'/v1/agents/{agent_id}', headers=admin_headers)
        assert resp.status_code == 204

        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='agent.deleted',
                resource_id=agent_id,
                tenant_id='test-tenant',
            ).first()
            assert entry is not None
            assert entry.resource_type == 'agent'

    def test_login_creates_audit_entry(self, app, client, db_session, admin_user):
        """Logging in should produce a user.login audit entry."""
        response = client.post(
            '/v1/auth/login',
            data=json.dumps({
                'username': admin_user['username'],
                'password': 'testpass',
            }),
            headers={'Content-Type': 'application/json', 'X-Tenant-ID': 'test-tenant'},
        )
        assert response.status_code == 200

        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='user.login',
                resource_id=admin_user['id'],
                tenant_id='test-tenant',
            ).first()
            assert entry is not None
            assert entry.resource_type == 'user'
            assert entry.resource_name == admin_user['username']


class TestAuditLogEndpoints:
    """Verify the audit log read-only API."""

    def test_list_audit_logs_as_admin(self, app, client, db_session,
                                      admin_headers, valid_agent_payload):
        """Admins can list audit log entries."""
        client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )

        response = client.get('/v1/audit-logs', headers=admin_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert 'logs' in data
        assert 'pagination' in data
        assert data['pagination']['total'] >= 1

    def test_list_audit_logs_filter_by_action(self, app, client, db_session,
                                               admin_headers, valid_agent_payload):
        """Filter audit logs by action type."""
        client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )

        response = client.get(
            '/v1/audit-logs?action=agent.created',
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        for log in data['logs']:
            assert log['action'] == 'agent.created'

    def test_list_audit_logs_filter_by_resource_type(self, app, client, db_session,
                                                      admin_headers, valid_agent_payload):
        """Filter audit logs by resource type."""
        client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )

        response = client.get(
            '/v1/audit-logs?resource_type=agent',
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        for log in data['logs']:
            assert log['resource_type'] == 'agent'

    def test_get_audit_log_detail(self, app, client, db_session,
                                  admin_headers, valid_agent_payload):
        """Fetch a single audit log entry with full detail."""
        client.post(
            '/v1/agents',
            data=json.dumps(valid_agent_payload),
            headers=admin_headers,
        )

        list_resp = client.get('/v1/audit-logs', headers=admin_headers)
        log_id = list_resp.get_json()['logs'][0]['id']

        detail_resp = client.get(f'/v1/audit-logs/{log_id}', headers=admin_headers)
        assert detail_resp.status_code == 200
        data = detail_resp.get_json()
        assert data['id'] == log_id
        assert 'action' in data
        assert 'timestamp' in data
        assert 'username' in data

    def test_get_audit_log_not_found(self, client, db_session, admin_headers):
        """Fetching a non-existent audit log returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(f'/v1/audit-logs/{fake_id}', headers=admin_headers)
        assert response.status_code == 404


class TestAuditLogAccessControl:
    """Verify that only administrators can access audit logs."""

    def test_non_admin_cannot_list_audit_logs(self, client, db_session, user_headers):
        """Non-admin users receive 403 when listing audit logs."""
        response = client.get('/v1/audit-logs', headers=user_headers)
        assert response.status_code == 403

    def test_non_admin_cannot_get_audit_log_detail(self, client, db_session, user_headers):
        """Non-admin users receive 403 when fetching audit log detail."""
        fake_id = str(uuid.uuid4())
        response = client.get(f'/v1/audit-logs/{fake_id}', headers=user_headers)
        assert response.status_code == 403

    def test_unauthenticated_cannot_list_audit_logs(self, client, db_session):
        """Unauthenticated requests receive 401."""
        response = client.get('/v1/audit-logs')
        assert response.status_code == 401


class TestAuditLogImmutability:
    """Verify that no write operations exist for audit logs."""

    def test_no_post_endpoint(self, client, db_session, admin_headers):
        """POST to audit-logs should return 405 Method Not Allowed."""
        response = client.post(
            '/v1/audit-logs',
            data=json.dumps({'action': 'test'}),
            headers=admin_headers,
        )
        assert response.status_code == 405

    def test_no_put_endpoint(self, client, db_session, admin_headers):
        """PUT to audit-logs should return 405 Method Not Allowed."""
        fake_id = str(uuid.uuid4())
        response = client.put(
            f'/v1/audit-logs/{fake_id}',
            data=json.dumps({'action': 'test'}),
            headers=admin_headers,
        )
        assert response.status_code == 405

    def test_no_delete_endpoint(self, client, db_session, admin_headers):
        """DELETE to audit-logs should return 405 Method Not Allowed."""
        fake_id = str(uuid.uuid4())
        response = client.delete(
            f'/v1/audit-logs/{fake_id}',
            headers=admin_headers,
        )
        assert response.status_code == 405
