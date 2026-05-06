"""Integration tests for the MeshClient — policies, compliance rules, registrations.

Run inside the Kind cluster via kubectl exec against the running registry API.
Mesh write endpoints require API key auth (X-Mesh-API-Key), not JWT.
"""

import pytest

from tests.conftest import unique_name


@pytest.mark.integration
class TestMeshPolicies:
    """Create, list, and delete mesh authorization policies."""

    def test_create_policy(self, mesh_client):
        src = unique_name("src-agent")
        dst = unique_name("dst-agent")
        policy = mesh_client.mesh.create_policy(
            source_agent_name=src,
            dest_agent_name=dst,
            action="allow",
        )
        assert policy.id is not None
        assert policy.action == "allow"

    def test_list_policies_contains_created(self, mesh_client):
        src = unique_name("src-list")
        dst = unique_name("dst-list")
        created = mesh_client.mesh.create_policy(
            source_agent_name=src,
            dest_agent_name=dst,
            action="deny",
        )
        policies = mesh_client.mesh.list_policies()
        assert any(str(p.id) == str(created.id) for p in policies)

    def test_delete_policy(self, mesh_client):
        src = unique_name("src-del")
        dst = unique_name("dst-del")
        created = mesh_client.mesh.create_policy(
            source_agent_name=src,
            dest_agent_name=dst,
            action="allow",
        )
        mesh_client.mesh.delete_policy(str(created.id))
        policies = mesh_client.mesh.list_policies()
        assert not any(str(p.id) == str(created.id) for p in policies)


@pytest.mark.integration
class TestComplianceRules:
    """Create, list, and delete compliance rules."""

    def test_create_compliance_rule(self, mesh_client):
        rule = mesh_client.mesh.create_compliance_rule(
            rule_type="sovereignty",
            source_value="eu",
            dest_value="us",
            action="block",
        )
        assert rule.id is not None
        assert rule.action == "block"

    def test_list_compliance_rules(self, mesh_client):
        created = mesh_client.mesh.create_compliance_rule(
            rule_type="classification",
            source_value="restricted",
            dest_value="public",
            action="block",
        )
        rules = mesh_client.mesh.list_compliance_rules()
        assert any(str(r.id) == str(created.id) for r in rules)

    def test_delete_compliance_rule(self, mesh_client):
        created = mesh_client.mesh.create_compliance_rule(
            rule_type="sovereignty",
            source_value="us",
            dest_value="cn",
            action="block",
        )
        mesh_client.mesh.delete_compliance_rule(str(created.id))
        rules = mesh_client.mesh.list_compliance_rules()
        assert not any(str(r.id) == str(created.id) for r in rules)


@pytest.mark.integration
class TestRegistrations:
    """Test sidecar registrations listing (JWT auth works for GET)."""

    def test_list_registrations_returns_list(self, client):
        registrations = client.mesh.list_registrations()
        # May be empty but should be a list
        assert isinstance(registrations, list)
