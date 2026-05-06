"""
Test cases for Agent Submission API.

Tests the agent creation, retrieval, update, deletion, and listing endpoints.
Validates REQ-SUB requirements from the specification.
"""

import pytest
import json
import uuid
from copy import deepcopy

from tests.conftest import unique_agent_name


class TestAgentCreation:
    """Test cases for POST /v1/agents - Agent creation."""

    def test_create_agent_with_valid_payload(self, client, db_session, auth_headers, valid_agent_payload):
        """Test successful agent creation with a valid payload."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()

        # Verify response contains expected fields
        assert 'id' in data
        assert data['name'] == payload['name']
        assert data['version'] == payload['version']
        assert data['description'] == payload['description']
        assert data['status'] == 'draft'
        assert 'created_at' in data
        assert 'updated_at' in data

    def test_create_agent_with_minimal_payload(self, client, db_session, auth_headers, minimal_valid_payload):
        """Test agent creation with minimal required fields only."""
        payload = deepcopy(minimal_valid_payload)
        payload['name'] = unique_agent_name("minimal")

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == payload['name']
        assert data['status'] == 'draft'

    def test_create_agent_with_tools(self, client, db_session, auth_headers, valid_agent_payload_with_tools):
        """Test agent creation with tool dependencies."""
        payload = deepcopy(valid_agent_payload_with_tools)
        payload['name'] = unique_agent_name("with-tools")

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == payload['name']
        assert data['data_sensitivity'] == 'pii'
        assert data['risk_tier'] == 'medium'

    def test_create_agent_with_resource_quota(self, client, db_session, auth_headers, valid_agent_payload_with_relationships):
        """Test agent creation with resource quota configuration."""
        payload = deepcopy(valid_agent_payload_with_relationships)
        payload['name'] = unique_agent_name("with-quota")

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()

        # Check resource quota is returned
        assert data.get('resource_quota') is not None or data.get('max_tokens_per_request') is not None

    def test_create_agent_with_multiple_capabilities(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with multiple capabilities (REQ-SUB-006)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name("multi-cap")
        payload['capabilities'] = [
            {"name": "capability-1", "description": "First capability"},
            {"name": "capability-2", "description": "Second capability"},
            {"name": "capability-3", "description": "Third capability"}
        ]

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()
        assert len(data.get('capabilities', [])) == 3

    def test_create_agent_with_all_endpoint_types(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with different endpoint types."""
        endpoint_types = ['langchain', 'crewai', 'langgraph', 'agentforce', 'databricks', 'openai', 'custom']

        for endpoint_type in endpoint_types:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{endpoint_type}")
            payload['endpoint']['type'] = endpoint_type

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Failed for endpoint type: {endpoint_type}"
            data = response.get_json()
            assert data['endpoint']['type'] == endpoint_type

    def test_create_agent_with_all_auth_methods(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with different authentication methods."""
        auth_methods = ['mtls', 'oauth2', 'api_key', 'iam']

        for auth_method in auth_methods:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{auth_method}")
            payload['endpoint']['auth_method'] = auth_method

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Failed for auth method: {auth_method}"
            data = response.get_json()
            assert data['endpoint']['auth_method'] == auth_method

    def test_create_agent_with_all_risk_tiers(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with different risk tiers."""
        risk_tiers = ['low', 'medium', 'high', 'critical']

        for risk_tier in risk_tiers:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{risk_tier}")
            payload['risk_tier'] = risk_tier

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Failed for risk tier: {risk_tier}"
            data = response.get_json()
            assert data['risk_tier'] == risk_tier

    def test_create_agent_with_all_classifications(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with different classifications."""
        classifications = ['internal', 'confidential', 'restricted', 'public']

        for classification in classifications:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{classification}")
            payload['classification'] = classification

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Failed for classification: {classification}"
            data = response.get_json()
            assert data['classification'] == classification

    def test_create_agent_with_all_data_sensitivities(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent creation with different data sensitivity levels."""
        sensitivities = ['none', 'pii', 'phi', 'financial', 'secret']

        for sensitivity in sensitivities:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{sensitivity}")
            payload['data_sensitivity'] = sensitivity

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Failed for data sensitivity: {sensitivity}"
            data = response.get_json()
            assert data['data_sensitivity'] == sensitivity


class TestAgentCreationValidation:
    """Test cases for validation errors during agent creation."""

    def test_create_agent_missing_name(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that missing name field returns validation error (REQ-SUB-001)."""
        payload = deepcopy(valid_agent_payload)
        del payload['name']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'name' in str(data.get('messages', {})).lower()

    def test_create_agent_missing_version(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that missing version field returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        del payload['version']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_version_format(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid version format returns validation error (REQ-SUB-003)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        invalid_versions = ['1.0', 'v1.0.0', '1.0.0.0', 'abc', '1.a.0', '']

        for invalid_version in invalid_versions:
            payload['version'] = invalid_version

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 400, f"Should reject invalid version: {invalid_version}"

    def test_create_agent_valid_semver_versions(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that valid semantic versions are accepted (REQ-SUB-003)."""
        valid_versions = ['0.0.1', '1.0.0', '2.15.3', '10.20.30']

        for version in valid_versions:
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"semver-{version.replace('.', '-')}")
            payload['version'] = version

            response = client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

            assert response.status_code == 201, f"Should accept valid version: {version}"

    def test_create_agent_missing_capabilities(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that missing capabilities returns validation error (REQ-SUB-006)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        del payload['capabilities']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_empty_capabilities(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that empty capabilities array returns validation error (REQ-SUB-006)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['capabilities'] = []

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_missing_endpoint(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that missing endpoint returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        del payload['endpoint']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_endpoint_url(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid endpoint URL returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['endpoint']['url'] = 'not-a-valid-url'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_email(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid email returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['contact_email'] = 'not-an-email'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_endpoint_type(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid endpoint type returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['endpoint']['type'] = 'invalid-type'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_auth_method(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid auth method returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['endpoint']['auth_method'] = 'invalid-auth'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_risk_tier(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid risk tier returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['risk_tier'] = 'invalid-tier'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_invalid_classification(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid classification returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['classification'] = 'invalid-class'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_timeout_out_of_range(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that timeout outside valid range returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Too low
        payload['endpoint']['timeout_ms'] = 50

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

        # Too high
        payload['endpoint']['timeout_ms'] = 500000

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_empty_payload(self, client, db_session, auth_headers):
        """Test that empty payload returns validation error."""
        response = client.post(
            '/v1/agents',
            data=json.dumps({}),
            headers=auth_headers
        )

        assert response.status_code == 400


class TestAgentDuplicateValidation:
    """Test cases for duplicate agent name validation (REQ-SUB-002)."""

    def test_create_agent_duplicate_name_same_tenant(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that duplicate agent name in same tenant returns conflict error (REQ-SUB-002)."""
        payload = deepcopy(valid_agent_payload)
        agent_name = unique_agent_name("duplicate-test")
        payload['name'] = agent_name

        # Create first agent
        response1 = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        assert response1.status_code == 201

        # Try to create second agent with same name
        response2 = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response2.status_code == 409
        data = response2.get_json()
        assert 'duplicate' in data.get('error', '').lower() or 'exists' in str(data).lower()

    def test_create_agent_same_name_different_tenant(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that same agent name in different tenant is allowed."""
        payload = deepcopy(valid_agent_payload)
        agent_name = unique_agent_name("cross-tenant")
        payload['name'] = agent_name

        # Create first agent in tenant-1
        headers1 = {**auth_headers, 'X-Tenant-ID': 'tenant-1'}
        response1 = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=headers1
        )
        assert response1.status_code == 201

        # Create second agent with same name in tenant-2
        headers2 = {**auth_headers, 'X-Tenant-ID': 'tenant-2'}
        response2 = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=headers2
        )

        assert response2.status_code == 201


class TestAgentRetrieval:
    """Test cases for GET /v1/agents/{id} - Agent retrieval."""

    def test_get_agent_by_id(self, client, db_session, auth_headers, valid_agent_payload):
        """Test retrieving an agent by ID."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        assert create_response.status_code == 201
        agent_id = create_response.get_json()['id']

        # Get agent
        get_response = client.get(
            f'/v1/agents/{agent_id}',
            headers=auth_headers
        )

        assert get_response.status_code == 200
        data = get_response.get_json()
        assert data['id'] == agent_id
        assert data['name'] == payload['name']

    def test_get_agent_not_found(self, client, db_session, auth_headers):
        """Test that non-existent agent returns 404."""
        fake_id = str(uuid.uuid4())

        response = client.get(
            f'/v1/agents/{fake_id}',
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_get_agent_invalid_uuid(self, client, db_session, auth_headers):
        """Test that invalid UUID returns 404."""
        response = client.get(
            '/v1/agents/not-a-uuid',
            headers=auth_headers
        )

        assert response.status_code == 404


class TestAgentUpdate:
    """Test cases for PUT /v1/agents/{id} - Agent update."""

    def test_update_agent_description(self, client, db_session, auth_headers, valid_agent_payload):
        """Test updating agent description."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Update description
        update_payload = {"description": "Updated description"}

        update_response = client.put(
            f'/v1/agents/{agent_id}',
            data=json.dumps(update_payload),
            headers=auth_headers
        )

        assert update_response.status_code == 200
        data = update_response.get_json()
        assert data['description'] == "Updated description"

    def test_update_agent_version(self, client, db_session, auth_headers, valid_agent_payload):
        """Test updating agent version."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Update version
        update_payload = {"version": "2.0.0"}

        update_response = client.put(
            f'/v1/agents/{agent_id}',
            data=json.dumps(update_payload),
            headers=auth_headers
        )

        assert update_response.status_code == 200
        data = update_response.get_json()
        assert data['version'] == "2.0.0"

    def test_update_agent_endpoint(self, client, db_session, auth_headers, valid_agent_payload):
        """Test updating agent endpoint configuration."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Update endpoint
        update_payload = {
            "endpoint": {
                "type": "langgraph",
                "url": "https://new-endpoint.example.com/agent",
                "auth_method": "oauth2",
                "timeout_ms": 45000
            }
        }

        update_response = client.put(
            f'/v1/agents/{agent_id}',
            data=json.dumps(update_payload),
            headers=auth_headers
        )

        assert update_response.status_code == 200
        data = update_response.get_json()
        assert data['endpoint']['type'] == 'langgraph'
        assert data['endpoint']['url'] == 'https://new-endpoint.example.com/agent'

    def test_update_agent_not_found(self, client, db_session, auth_headers):
        """Test updating non-existent agent returns 404."""
        fake_id = str(uuid.uuid4())

        response = client.put(
            f'/v1/agents/{fake_id}',
            data=json.dumps({"description": "New description"}),
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_update_agent_invalid_version_format(self, client, db_session, auth_headers, valid_agent_payload):
        """Test that invalid version format in update returns validation error."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Try to update with invalid version
        update_payload = {"version": "invalid-version"}

        update_response = client.put(
            f'/v1/agents/{agent_id}',
            data=json.dumps(update_payload),
            headers=auth_headers
        )

        assert update_response.status_code == 400


class TestAgentDeletion:
    """Test cases for DELETE /v1/agents/{id} - Agent deletion (soft delete)."""

    def test_delete_agent(self, client, db_session, auth_headers, valid_agent_payload):
        """Test soft deleting an agent."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Delete agent
        delete_response = client.delete(
            f'/v1/agents/{agent_id}',
            headers=auth_headers
        )

        assert delete_response.status_code == 204

        # Verify agent is not returned by default
        get_response = client.get(
            f'/v1/agents/{agent_id}',
            headers=auth_headers
        )

        assert get_response.status_code == 404

    def test_delete_agent_not_found(self, client, db_session, auth_headers):
        """Test deleting non-existent agent returns 404."""
        fake_id = str(uuid.uuid4())

        response = client.delete(
            f'/v1/agents/{fake_id}',
            headers=auth_headers
        )

        assert response.status_code == 404


class TestAgentListing:
    """Test cases for GET /v1/agents - Agent listing."""

    def test_list_agents_empty(self, client, db_session, auth_headers):
        """Test listing agents when none exist."""
        response = client.get(
            '/v1/agents',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'agents' in data
        assert len(data['agents']) == 0

    def test_list_agents_pagination(self, client, db_session, auth_headers, valid_agent_payload):
        """Test agent listing with pagination."""
        # Create multiple agents
        for i in range(5):
            payload = deepcopy(valid_agent_payload)
            payload['name'] = unique_agent_name(f"agent-{i}")

            client.post(
                '/v1/agents',
                data=json.dumps(payload),
                headers=auth_headers
            )

        # Get first page
        response = client.get(
            '/v1/agents?page=1&per_page=2',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert len(data['agents']) == 2
        assert 'pagination' in data
        assert data['pagination']['page'] == 1
        assert data['pagination']['per_page'] == 2

    def test_list_agents_filter_by_status(self, client, db_session, auth_headers, valid_agent_payload):
        """Test filtering agents by status."""
        # Create an agent (will be in DRAFT status)
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        # Filter by draft status
        response = client.get(
            '/v1/agents?status=draft',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        for agent in data['agents']:
            assert agent['status'] == 'draft'

    def test_list_agents_filter_by_team(self, client, db_session, auth_headers, valid_agent_payload):
        """Test filtering agents by team_id."""
        team_id = f"test-team-{uuid.uuid4().hex[:8]}"

        # Create agent with specific team
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['team_id'] = team_id

        client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        # Filter by team
        response = client.get(
            f'/v1/agents?team_id={team_id}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        for agent in data['agents']:
            assert agent['team_id'] == team_id


class TestAgentVersions:
    """Test cases for agent versioning endpoints."""

    def test_list_agent_versions(self, client, db_session, auth_headers, valid_agent_payload):
        """Test listing versions of an agent."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # List versions
        response = client.get(
            f'/v1/agents/{agent_id}/versions',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'versions' in data
        assert isinstance(data['versions'], list)

    def test_get_specific_version(self, client, db_session, auth_headers, valid_agent_payload):
        """Test getting a specific version of an agent."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        version = payload['version']

        # Create agent
        create_response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )
        agent_id = create_response.get_json()['id']

        # Get specific version
        response = client.get(
            f'/v1/agents/{agent_id}/versions/{version}',
            headers=auth_headers
        )

        assert response.status_code == 200


class TestAgentWithGuardrailProfile:
    """Test cases for agents with guardrail profiles (REQ-SUB-007)."""

    def test_create_agent_with_valid_guardrail_profile(
        self, client, db_session, auth_headers, valid_agent_payload, guardrail_profile
    ):
        """Test creating agent with valid guardrail profile (REQ-SUB-007)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['guardrail_profile_id'] = guardrail_profile['id']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data.get('guardrail_profile_id') == guardrail_profile['id']

    def test_create_agent_with_inactive_guardrail_profile(
        self, client, db_session, auth_headers, valid_agent_payload, inactive_guardrail_profile
    ):
        """Test that inactive guardrail profile returns error (REQ-SUB-007)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['guardrail_profile_id'] = inactive_guardrail_profile['id']

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400

    def test_create_agent_with_nonexistent_guardrail_profile(
        self, client, db_session, auth_headers, valid_agent_payload
    ):
        """Test that non-existent guardrail profile returns error (REQ-SUB-007)."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['guardrail_profile_id'] = 'nonexistent-profile-id'

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 400


class TestAgentCapabilitySchemas:
    """Test cases for capability input/output schemas."""

    def test_create_agent_with_capability_schemas(self, client, db_session, auth_headers, valid_agent_payload):
        """Test creating agent with detailed capability schemas."""
        payload = deepcopy(valid_agent_payload)
        payload['name'] = unique_agent_name()
        payload['capabilities'] = [
            {
                "name": "data-query",
                "description": "Query data from the system",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["query"]
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "results": {"type": "array"},
                        "count": {"type": "integer"}
                    }
                }
            }
        ]

        response = client.post(
            '/v1/agents',
            data=json.dumps(payload),
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.get_json()
        assert len(data['capabilities']) == 1
        assert 'input_schema' in data['capabilities'][0]
        assert 'output_schema' in data['capabilities'][0]
