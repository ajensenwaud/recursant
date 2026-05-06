"""Integration tests for tool governance — tool registry, sidecar proxy, egress control.

Requires the Docker Compose stack to be running:
    docker compose up -d registry registry-db registry-redis

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    ADMIN_USERNAME / ADMIN_PASSWORD: Admin credentials
    MESH_API_KEY: Mesh API key
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://localhost:5000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", os.environ.get("REGISTRY_USERNAME", "admin"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", os.environ.get("REGISTRY_PASSWORD", "admin"))
MESH_API_KEY = os.environ.get("MESH_API_KEY", "mesh-dev-key")

TIMEOUT = 10.0


def _login() -> str:
    """Get a JWT token."""
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
        "Content-Type": "application/json",
    }


def _mesh_headers() -> dict:
    return {
        "X-Mesh-API-Key": MESH_API_KEY,
        "X-Tenant-ID": "default",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def jwt_token():
    return _login()


@pytest.fixture(scope="module")
def auth_headers(jwt_token):
    return _auth_headers(jwt_token)


@pytest.fixture(scope="module")
def mesh_headers():
    return _mesh_headers()


class TestToolCRUD:
    """Test tool creation, approval, assignment, and deletion."""

    def test_create_tool(self, auth_headers):
        unique_name = f"test-tool-{uuid.uuid4().hex[:8]}"
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "description": "Test tool",
                "endpoint_url": "http://localhost:9999/test",
                "http_method": "POST",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == unique_name
        assert data["status"] == "submitted"

        # Cleanup
        httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/tools/{data['id']}",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

    def test_approve_tool(self, auth_headers):
        unique_name = f"test-approve-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert create_resp.status_code == 201
        tool_id = create_resp.json()["id"]

        # Approve
        approve_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

    def test_revoke_tool(self, auth_headers):
        unique_name = f"test-revoke-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Approve first
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Revoke
        revoke_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/revoke",
            json={"justification": "No longer needed"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "revoked"
        assert revoke_resp.json()["revoked_by"] is not None

    def test_revoke_submitted_tool(self, auth_headers):
        """Can revoke a submitted (not yet approved) tool."""
        unique_name = f"test-revoke-sub-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        revoke_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/revoke",
            json={"justification": "Rejected during review"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "revoked"

    def test_create_tool_with_mcp_fields(self, auth_headers):
        """Create tool with MCP server metadata."""
        unique_name = f"test-mcp-{uuid.uuid4().hex[:8]}"
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "description": "Tool with MCP server",
                "endpoint_url": "http://localhost:9999/test",
                "http_method": "POST",
                "mcp_server_url": "http://mcp-test:8080/sse",
                "mcp_server_name": "Test MCP Server",
                "mcp_server_description": "MCP server for testing",
                "backend_services": [
                    {"url": "http://backend:6000/api", "method": "POST", "description": "Test API"}
                ],
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["mcp_server_url"] == "http://mcp-test:8080/sse"
        assert data["mcp_server_name"] == "Test MCP Server"
        assert data["mcp_server_description"] == "MCP server for testing"
        assert len(data["backend_services"]) == 1
        assert data["backend_services"][0]["method"] == "POST"

        # Cleanup
        httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/tools/{data['id']}",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

    def test_cannot_delete_approved_tool(self, auth_headers):
        unique_name = f"test-nodelete-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Approve
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Try to delete — should fail
        del_resp = httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert del_resp.status_code == 400

    def test_tool_assignment(self, auth_headers):
        unique_name = f"test-assign-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Approve
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Assign
        assign_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Test Agent"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert assign_resp.status_code == 201
        assert assign_resp.json()["agent_name"] == "Test Agent"

    def test_duplicate_assignment_returns_409(self, auth_headers):
        unique_name = f"test-dupassign-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Agent X"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        dup_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Agent X"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert dup_resp.status_code == 409


class TestSidecarFacingEndpoints:
    """Test the sidecar-facing tool/egress endpoints."""

    def test_tools_for_agent(self, auth_headers, mesh_headers):
        """Approved+assigned tools appear in for-agent query."""
        unique_name = f"test-foragent-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "ForAgent Test"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Query as sidecar
        tools_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "ForAgent Test"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert tools_resp.status_code == 200
        tools = tools_resp.json()["tools"]
        names = [t["name"] for t in tools]
        assert unique_name in names

    def test_tools_for_agent_excludes_unapproved(self, auth_headers, mesh_headers):
        """Draft tools do not appear in for-agent query."""
        unique_name = f"test-draft-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Assign without approving
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Draft Agent"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        tools_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Draft Agent"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert tools_resp.status_code == 200
        names = [t["name"] for t in tools_resp.json()["tools"]]
        assert unique_name not in names


    def test_tool_not_assigned_to_agent_excluded(self, auth_headers, mesh_headers):
        """Tool approved and assigned to Agent A does NOT appear for Agent B."""
        unique_name = f"test-notassigned-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Approve
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Assign to Agent A only
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Agent A"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Agent B queries — should NOT see the tool
        tools_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Agent B"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert tools_resp.status_code == 200
        names = [t["name"] for t in tools_resp.json()["tools"]]
        assert unique_name not in names, (
            f"Tool '{unique_name}' assigned to Agent A should not appear for Agent B"
        )

        # Agent A queries — SHOULD see the tool
        tools_resp_a = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Agent A"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        names_a = [t["name"] for t in tools_resp_a.json()["tools"]]
        assert unique_name in names_a

    def test_revoked_tool_excluded_from_for_agent(self, auth_headers, mesh_headers):
        """Revoked tool does NOT appear in for-agent query."""
        unique_name = f"test-revoked-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Approve → assign → revoke
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/approve",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Revoked Test Agent"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools/{tool_id}/revoke",
            json={"justification": "Testing revocation"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        tools_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Revoked Test Agent"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert tools_resp.status_code == 200
        names = [t["name"] for t in tools_resp.json()["tools"]]
        assert unique_name not in names, (
            f"Revoked tool '{unique_name}' should not appear in for-agent"
        )

    def test_assign_unapproved_tool_still_excluded(self, auth_headers, mesh_headers):
        """Assigning a draft tool does not make it available — must be approved first."""
        unique_name = f"test-draftassign-{uuid.uuid4().hex[:8]}"
        create_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tools",
            json={
                "name": unique_name,
                "endpoint_url": "http://localhost:9999/test",
            },
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        tool_id = create_resp.json()["id"]

        # Assign WITHOUT approving
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id, "agent_name": "Draft Assign Agent"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        tools_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Draft Assign Agent"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert tools_resp.status_code == 200
        names = [t["name"] for t in tools_resp.json()["tools"]]
        assert unique_name not in names


class TestEgressRules:
    """Test egress rule CRUD."""

    def test_create_egress_rule(self, mesh_headers):
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/egress-rules",
            json={
                "agent_name": "*",
                "url_pattern": "http://test.example.com/*",
                "action": "allow",
                "priority": 50,
            },
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url_pattern"] == "http://test.example.com/*"

        # Cleanup
        httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/egress-rules/{data['id']}",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )

    def test_egress_rules_for_agent(self, mesh_headers):
        """Egress rules returned for matching agent or wildcard."""
        rule_resp = httpx.post(
            f"{REGISTRY_URL}/v1/mesh/egress-rules",
            json={
                "agent_name": "*",
                "url_pattern": "http://integ-test.com/*",
                "action": "allow",
                "priority": 0,
            },
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        rule_id = rule_resp.json()["id"]

        rules_resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/egress-rules/for-agent",
            params={"agent_name": "Any Agent"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert rules_resp.status_code == 200
        patterns = [r["url_pattern"] for r in rules_resp.json()["rules"]]
        assert "http://integ-test.com/*" in patterns

        # Cleanup
        httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/egress-rules/{rule_id}",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )


class TestWithAssignmentsEndpoint:
    """Test the /mesh/tools/with-assignments visualiser endpoint."""

    def test_with_assignments_returns_tools(self, mesh_headers):
        """The with-assignments endpoint returns tools with assignment data."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        # Seeded mortgage tools should be present
        names = [t["name"] for t in data["tools"]]
        assert "verify_customer" in names

    def test_with_assignments_includes_mcp_fields(self, mesh_headers):
        """Seeded tools have MCP server metadata."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = resp.json()["tools"]
        verify_customer = next(t for t in tools if t["name"] == "verify_customer")
        assert verify_customer["mcp_server_url"] is not None
        assert "mcp-customer-master" in verify_customer["mcp_server_url"]
        assert verify_customer["mcp_server_name"] == "Customer Master"
        assert verify_customer["backend_services"] is not None
        assert len(verify_customer["backend_services"]) >= 1

    def test_with_assignments_includes_assignments(self, mesh_headers):
        """Seeded tools have agent assignments inlined."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = resp.json()["tools"]
        verify_customer = next(t for t in tools if t["name"] == "verify_customer")
        assert "assignments" in verify_customer
        assert len(verify_customer["assignments"]) >= 1
        assert "agent_name" in verify_customer["assignments"][0]

    def test_for_agent_includes_mcp_server_url(self, mesh_headers):
        """The for-agent endpoint includes mcp_server_url for sidecar routing."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/for-agent",
            params={"agent_name": "Authentication Agent"},
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert len(tools) >= 1
        vc = next((t for t in tools if t["name"] == "verify_customer"), None)
        assert vc is not None
        assert vc["mcp_server_url"] is not None
        assert "mcp-customer-master" in vc["mcp_server_url"]


class TestMCPToolMetadata:
    """Verify all seeded mortgage tools have complete MCP metadata."""

    def test_all_seeded_tools_have_mcp_server_url(self, mesh_headers):
        """Every seeded mortgage tool must have an mcp_server_url."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = resp.json()["tools"]
        expected = {"verify_customer", "verify_identity", "assess_credit_capacity",
                    "make_credit_decision", "disburse_loan"}
        for tool in tools:
            if tool["name"] in expected:
                assert tool["mcp_server_url"] is not None, (
                    f"Tool '{tool['name']}' missing mcp_server_url"
                )
                assert tool["mcp_server_url"].endswith("/sse"), (
                    f"Tool '{tool['name']}' mcp_server_url should end with /sse"
                )

    def test_all_seeded_tools_have_backend_services(self, mesh_headers):
        """Every seeded mortgage tool must have backend_services metadata."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = resp.json()["tools"]
        expected = {"verify_customer", "verify_identity", "assess_credit_capacity",
                    "make_credit_decision", "disburse_loan"}
        for tool in tools:
            if tool["name"] in expected:
                assert tool["backend_services"] is not None, (
                    f"Tool '{tool['name']}' missing backend_services"
                )
                assert len(tool["backend_services"]) >= 1
                svc = tool["backend_services"][0]
                assert "url" in svc
                assert "method" in svc

    def test_credit_engine_tools_share_mcp_server(self, mesh_headers):
        """assess_credit_capacity and make_credit_decision share the same MCP server."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = {t["name"]: t for t in resp.json()["tools"]}
        assert tools["assess_credit_capacity"]["mcp_server_url"] == \
               tools["make_credit_decision"]["mcp_server_url"]
        assert tools["assess_credit_capacity"]["mcp_server_name"] == "Credit Engine"

    def test_each_tool_has_exactly_one_assignment(self, mesh_headers):
        """Every seeded mortgage tool is assigned to exactly one agent."""
        resp = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/tools/with-assignments",
            headers=mesh_headers,
            timeout=TIMEOUT,
        )
        tools = resp.json()["tools"]
        expected = {"verify_customer", "verify_identity", "assess_credit_capacity",
                    "make_credit_decision", "disburse_loan"}
        for tool in tools:
            if tool["name"] in expected:
                assert len(tool["assignments"]) == 1, (
                    f"Tool '{tool['name']}' should have 1 assignment, got {len(tool['assignments'])}"
                )
