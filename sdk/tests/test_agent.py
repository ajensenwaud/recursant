"""Unit tests for the Agent class."""

import pytest

from recursant.agent import Agent
from recursant.exceptions import ConfigError


VALID_AGENT_YAML = """\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: yaml-agent
  version: "2.0.0"
  tenant: my-tenant
spec:
  classification: confidential
  data_sensitivity: financial
  risk_tier: high
  description: From YAML
  owner_id: yaml-owner
  team_id: yaml-team
  contact_email: yaml@test.com
  endpoint:
    url: http://yaml-agent:8001
    type: langchain
    auth_method: mtls
    timeout_seconds: 60
    protocol: custom
  capabilities:
    - name: analyze
      description: Analyze data
"""

VALID_AGENT_WITH_QUOTAS = """\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: quota-agent
  version: "1.0.0"
spec:
  endpoint:
    url: http://localhost:8001
  quotas:
    max_tokens_per_request: 4096
    max_requests_per_minute: 100
    max_cost_per_day_usd: 50.0
"""


class TestAgentConstructor:
    def test_minimal_constructor(self):
        a = Agent(name="foo")
        assert a.name == "foo"
        assert a.version == "0.1.0"
        assert a.description == "foo agent"
        assert a.tenant_id == "default"
        assert a.classification == "internal"
        assert a.data_sensitivity == "none"
        assert a.risk_tier == "low"
        assert a.resource_quota is None
        assert len(a.capabilities) == 1
        assert a.capabilities[0]["name"] == "default"
        assert a.capabilities[0]["description"] == "foo agent"

    def test_all_fields_constructor(self):
        caps = [{"name": "cap1", "description": "d1"}]
        quota = {"max_tokens_per_request": 4096}
        a = Agent(
            name="full",
            version="3.0.0",
            endpoint_url="http://full:8001",
            endpoint_type="langchain",
            classification="confidential",
            data_sensitivity="financial",
            risk_tier="critical",
            description="Full agent",
            owner_id="owner-1",
            team_id="team-1",
            contact_email="full@test.com",
            tenant_id="custom-tenant",
            auth_method="mtls",
            timeout_seconds=120,
            protocol="grpc",
            capabilities=caps,
            resource_quota=quota,
        )
        assert a.name == "full"
        assert a.version == "3.0.0"
        assert a.endpoint_url == "http://full:8001"
        assert a.classification == "confidential"
        assert a.resource_quota == quota
        assert a.capabilities == caps
        assert a.protocol == "grpc"
        assert a.timeout_seconds == 120

    def test_description_defaults_to_name_agent(self):
        a = Agent(name="my-bot")
        assert a.description == "my-bot agent"

    def test_explicit_description(self):
        a = Agent(name="my-bot", description="Custom desc")
        assert a.description == "Custom desc"

    def test_empty_description_uses_default(self):
        a = Agent(name="my-bot", description="")
        assert a.description == "my-bot agent"

    def test_capabilities_default(self):
        a = Agent(name="x")
        assert len(a.capabilities) == 1
        assert a.capabilities[0] == {"name": "default", "description": "x agent"}

    def test_capabilities_explicit(self):
        caps = [{"name": "cap1", "description": "d"}]
        a = Agent(name="x", capabilities=caps)
        assert a.capabilities == caps


class TestAgentFromConfig:
    def test_from_config_valid(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        a = Agent.from_config(str(f))
        assert a.name == "yaml-agent"
        assert a.version == "2.0.0"
        assert a.tenant_id == "my-tenant"
        assert a.endpoint_url == "http://yaml-agent:8001"
        assert a.endpoint_type == "langchain"
        assert a.auth_method == "mtls"
        assert a.timeout_seconds == 60
        assert a.protocol == "custom"
        assert a.classification == "confidential"
        assert a.description == "From YAML"
        assert len(a.capabilities) == 1
        assert a.capabilities[0]["name"] == "analyze"

    def test_from_config_wrong_kind(self, tmp_path):
        f = tmp_path / "reg.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
""")
        with pytest.raises(ConfigError, match="Expected kind 'Agent'"):
            Agent.from_config(str(f))

    def test_from_config_missing_file(self):
        with pytest.raises(ConfigError, match="not found"):
            Agent.from_config("/nonexistent/file.yaml")

    def test_from_config_with_quotas(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_WITH_QUOTAS)
        a = Agent.from_config(str(f))
        assert a.resource_quota is not None
        assert a.resource_quota["max_tokens_per_request"] == 4096

    def test_from_config_without_quotas(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        a = Agent.from_config(str(f))
        assert a.resource_quota is None


class TestAgentToApiPayload:
    def test_payload_structure(self):
        a = Agent(name="test", endpoint_url="http://test:8001")
        payload = a.to_api_payload()
        expected_keys = {
            "name", "version", "description", "owner_id", "team_id",
            "contact_email", "tenant_id", "classification",
            "data_sensitivity", "risk_tier", "endpoint", "capabilities",
        }
        assert expected_keys.issubset(set(payload.keys()))

    def test_timeout_conversion(self):
        a = Agent(name="test", timeout_seconds=60)
        payload = a.to_api_payload()
        assert payload["endpoint"]["timeout_ms"] == 60000

    def test_protocol_in_payload(self):
        a = Agent(name="test", protocol="grpc")
        payload = a.to_api_payload()
        assert payload["endpoint"]["agent_protocol"] == "grpc"

    def test_resource_quota_present(self):
        a = Agent(name="test", resource_quota={"max_tokens_per_request": 4096})
        payload = a.to_api_payload()
        assert "resource_quota" in payload
        assert payload["resource_quota"]["max_tokens_per_request"] == 4096

    def test_resource_quota_absent(self):
        a = Agent(name="test")
        payload = a.to_api_payload()
        assert "resource_quota" not in payload
