"""Tests for mesh WebSocket (Socket.IO) events.

Validates that:
1. WebSocket connection requires valid JWT
2. Registration events are emitted when agents register/deregister
3. Audit events are emitted when audit records are submitted
4. Invalid tokens are rejected on connect
"""

import uuid
from datetime import datetime, timezone

import pytest

from app import create_app, db
from app.api.auth import create_token
from app.models.agent import Agent, AgentStatus, AuthMethod, Capability, Classification, DataSensitivity, EndpointType, RiskTier
from app.models.user import Group, GroupType, User
from app.services.mesh_events import socketio


@pytest.fixture(scope='module')
def app():
    """Create application for the tests."""
    import os
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'TEST_DATABASE_URL',
        'postgresql://registry:registry@db:5432/registry_test',
    )
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean up all tables between tests."""
    with app.app_context():
        yield
        db.session.rollback()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


@pytest.fixture
def admin_token(app):
    """Create an admin user and return a valid JWT token."""
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
        return create_token(user)


@pytest.fixture
def mesh_headers(app):
    return {
        'Content-Type': 'application/json',
        'X-Tenant-ID': 'default',
        'X-Mesh-API-Key': app.config.get('MESH_API_KEY', ''),
    }


@pytest.fixture
def active_agent(app):
    """Create an ACTIVE agent ready for mesh registration."""
    with app.app_context():
        name = f'ws-test-agent-{uuid.uuid4().hex[:8]}'
        agent = Agent(
            name=name,
            version='1.0.0',
            description='WebSocket test agent',
            owner_id='test',
            team_id='test',
            contact_email='test@test.com',
            classification=Classification.INTERNAL,
            data_sensitivity=DataSensitivity.NONE,
            risk_tier=RiskTier.LOW,
            status=AgentStatus.ACTIVE,
            tenant_id='default',
            endpoint_type=EndpointType.LANGGRAPH,
            endpoint_url='http://test:5010',
            endpoint_auth_method=AuthMethod.MTLS,
        )
        db.session.add(agent)
        db.session.flush()
        cap = Capability(
            agent_id=agent.id,
            name='ws-test-skill',
            description='Test skill',
        )
        db.session.add(cap)
        db.session.commit()
        return {'id': str(agent.id), 'name': name}


@pytest.fixture
def ws_client(app, admin_token):
    """Create a Socket.IO test client connected to the /mesh namespace."""
    client = socketio.test_client(
        app,
        namespace='/mesh',
        query_string=f'token={admin_token}',
    )
    yield client
    client.disconnect(namespace='/mesh')


class TestWebSocketAuth:
    """Test WebSocket authentication on the /mesh namespace."""

    def test_connect_with_valid_token(self, app, admin_token):
        """Valid JWT should allow WebSocket connection."""
        client = socketio.test_client(
            app,
            namespace='/mesh',
            query_string=f'token={admin_token}',
        )
        assert client.is_connected(namespace='/mesh')
        client.disconnect(namespace='/mesh')

    def test_connect_without_token_rejected(self, app):
        """Missing JWT should reject WebSocket connection."""
        client = socketio.test_client(
            app,
            namespace='/mesh',
        )
        assert not client.is_connected(namespace='/mesh')

    def test_connect_with_invalid_token_rejected(self, app):
        """Invalid JWT should reject WebSocket connection."""
        client = socketio.test_client(
            app,
            namespace='/mesh',
            query_string='token=invalid-token-here',
        )
        assert not client.is_connected(namespace='/mesh')


class TestRegistrationEvents:
    """Test that registration/deregistration emits WebSocket events."""

    def test_register_emits_event(self, app, active_agent, mesh_headers, ws_client):
        """Registering a sidecar should emit a 'registration' event."""
        # Clear any events from connection
        ws_client.get_received(namespace='/mesh')

        client = app.test_client()
        resp = client.post('/v1/mesh/register', json={
            'agent_id': active_agent['id'],
            'sidecar_url': 'http://test-host:9901',
            'agent_card': {
                'name': active_agent['name'],
                'version': '1.0.0',
                'skills': [{'id': 'ws-test-skill', 'name': 'ws-test-skill'}],
            },
        }, headers=mesh_headers)
        assert resp.status_code == 200

        received = ws_client.get_received(namespace='/mesh')
        reg_events = [e for e in received if e['name'] == 'registration']
        assert len(reg_events) >= 1
        data = reg_events[0]['args'][0]
        assert data['type'] == 'register'
        assert data['agent_name'] == active_agent['name']
        assert data['sidecar_url'] == 'http://test-host:9901'

    def test_deregister_emits_event(self, app, active_agent, mesh_headers, ws_client):
        """Deregistering a sidecar should emit a 'registration' event with type='deregister'."""
        client = app.test_client()

        # First register
        client.post('/v1/mesh/register', json={
            'agent_id': active_agent['id'],
            'sidecar_url': 'http://test-host:9901',
            'agent_card': {'name': active_agent['name'], 'version': '1.0.0', 'skills': []},
        }, headers=mesh_headers)

        # Clear received events from registration
        ws_client.get_received(namespace='/mesh')

        # Now deregister
        resp = client.post('/v1/mesh/deregister', json={
            'agent_id': active_agent['id'],
        }, headers=mesh_headers)
        assert resp.status_code == 200

        received = ws_client.get_received(namespace='/mesh')
        reg_events = [e for e in received if e['name'] == 'registration']
        assert len(reg_events) >= 1
        data = reg_events[0]['args'][0]
        assert data['type'] == 'deregister'
        assert data['agent_name'] == active_agent['name']


class TestAuditEvents:
    """Test that audit submission emits WebSocket events."""

    def test_audit_emits_events(self, app, mesh_headers, ws_client):
        """Submitting audit records should emit 'audit' events."""
        # Clear any events from connection
        ws_client.get_received(namespace='/mesh')

        client = app.test_client()
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post('/v1/mesh/audit', json={
            'records': [
                {
                    'timestamp': now,
                    'source_agent_name': 'Agent A',
                    'dest_agent_name': 'Agent B',
                    'a2a_method': 'message/send',
                    'message_hash': 'a' * 64,
                    'direction': 'outbound',
                    'decision': 'allow',
                    'outcome': 'allowed',
                },
                {
                    'timestamp': now,
                    'source_agent_name': 'Agent C',
                    'dest_agent_name': 'Agent D',
                    'a2a_method': 'message/send',
                    'message_hash': 'b' * 64,
                    'direction': 'outbound',
                    'decision': 'block',
                    'outcome': 'blocked',
                },
            ],
        }, headers=mesh_headers)
        assert resp.status_code == 201

        received = ws_client.get_received(namespace='/mesh')
        audit_events = [e for e in received if e['name'] == 'audit']
        assert len(audit_events) == 2

        data0 = audit_events[0]['args'][0]
        assert data0['source_agent_name'] == 'Agent A'
        assert data0['dest_agent_name'] == 'Agent B'
        assert data0['outcome'] == 'allowed'

        data1 = audit_events[1]['args'][0]
        assert data1['source_agent_name'] == 'Agent C'
        assert data1['dest_agent_name'] == 'Agent D'
        assert data1['outcome'] == 'blocked'

    def test_audit_event_contains_required_fields(self, app, mesh_headers, ws_client):
        """Audit events should contain all fields needed by the visualiser."""
        # Clear any events from connection
        ws_client.get_received(namespace='/mesh')

        client = app.test_client()
        now = datetime.now(timezone.utc).isoformat()
        resp = client.post('/v1/mesh/audit', json={
            'records': [{
                'timestamp': now,
                'source_agent_name': 'Sender',
                'dest_agent_name': 'Receiver',
                'a2a_method': 'tasks/send',
                'message_hash': 'x' * 64,
                'direction': 'outbound',
                'decision': 'allow',
                'outcome': 'allowed',
                'task_id': 'task-123',
            }],
        }, headers=mesh_headers)
        assert resp.status_code == 201

        received = ws_client.get_received(namespace='/mesh')
        audit_events = [e for e in received if e['name'] == 'audit']
        assert len(audit_events) == 1

        data = audit_events[0]['args'][0]
        assert 'source_agent_name' in data
        assert 'dest_agent_name' in data
        assert 'a2a_method' in data
        assert 'outcome' in data
        assert 'decision' in data
        assert 'timestamp' in data
        assert 'task_id' in data
        assert data['task_id'] == 'task-123'
