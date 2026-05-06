"""Unit tests for the YAML config loader and Pydantic config models."""

import pytest

from recursant.config import (
    AgentConfig,
    ComplianceRuleConfig,
    GuardrailConfig,
    MeshPolicyConfig,
    RegistryConfig,
    load_config,
    validate_config,
)
from recursant.exceptions import ConfigError


VALID_AGENT_YAML = """\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
spec:
  classification: confidential
  data_sensitivity: financial
  risk_tier: high
  description: A test agent
  endpoint:
    url: http://localhost:8001
    type: langchain
    auth_method: mtls
    timeout_seconds: 45
  capabilities:
    - name: cap1
      description: Capability one
"""

VALID_REGISTRY_YAML = """\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: test-tenant
guardrails:
  - name: pii-detector
    type: pre_processing
    mechanism: regex
    enforcement: block
mesh_policies:
  - source: agent-a
    destination: agent-b
    action: allow
compliance_rules:
  - name: eu-rule
    type: sovereignty
    source_zone: eu
    dest_value: us
    action: block
"""


class TestAgentConfigValidation:
    def test_load_valid_agent(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        cfg = load_config(str(f))
        assert isinstance(cfg, AgentConfig)
        assert cfg.metadata.name == "test-agent"
        assert cfg.spec.classification == "confidential"

    def test_missing_metadata_name(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: Agent
metadata:
  version: "1.0.0"
spec:
  endpoint:
    url: http://localhost:8001
""")
        with pytest.raises(ConfigError):
            load_config(str(f))

    def test_missing_endpoint(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: test
spec:
  classification: internal
""")
        with pytest.raises(ConfigError):
            load_config(str(f))

    def test_wrong_kind(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: Service
metadata:
  name: test
spec:
  endpoint:
    url: http://localhost:8001
""")
        with pytest.raises(ConfigError, match="Unknown config kind"):
            load_config(str(f))

    def test_kind_agent_wrong_case(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: agent
metadata:
  name: test
spec:
  endpoint:
    url: http://localhost:8001
""")
        with pytest.raises(ConfigError, match="Unknown config kind"):
            load_config(str(f))

    def test_malformed_yaml(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("key: [invalid\n  broken")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(str(f))

    def test_yaml_list_not_mapping(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="YAML mapping"):
            load_config(str(f))


class TestAgentConfigPayload:
    def test_timeout_conversion(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        cfg = load_config(str(f))
        payload = cfg.to_api_payload()
        assert payload["endpoint"]["timeout_ms"] == 45000

    def test_empty_capabilities_gets_default(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: no-caps
  version: "1.0.0"
spec:
  description: An agent
  endpoint:
    url: http://localhost:8001
""")
        cfg = load_config(str(f))
        payload = cfg.to_api_payload()
        assert len(payload["capabilities"]) == 1
        assert payload["capabilities"][0]["name"] == "default"

    def test_with_quotas(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text("""\
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
""")
        cfg = load_config(str(f))
        payload = cfg.to_api_payload()
        assert "resource_quota" in payload
        assert payload["resource_quota"]["max_tokens_per_request"] == 4096

    def test_without_quotas(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        cfg = load_config(str(f))
        payload = cfg.to_api_payload()
        assert "resource_quota" not in payload

    def test_all_fields_in_payload(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        cfg = load_config(str(f))
        payload = cfg.to_api_payload()
        expected_keys = {
            "name", "version", "description", "owner_id", "team_id",
            "contact_email", "tenant_id", "classification",
            "data_sensitivity", "risk_tier", "endpoint", "capabilities",
        }
        assert expected_keys.issubset(set(payload.keys()))
        assert payload["endpoint"]["agent_protocol"] == "A2A"


class TestRegistryConfigValidation:
    def test_full_registry_config(self, tmp_path):
        f = tmp_path / "reg.yaml"
        f.write_text(VALID_REGISTRY_YAML)
        cfg = load_config(str(f))
        assert isinstance(cfg, RegistryConfig)
        assert len(cfg.guardrails) == 1
        assert len(cfg.mesh_policies) == 1
        assert len(cfg.compliance_rules) == 1

    def test_empty_sections(self, tmp_path):
        f = tmp_path / "reg.yaml"
        f.write_text("""\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
""")
        cfg = load_config(str(f))
        assert isinstance(cfg, RegistryConfig)
        assert cfg.guardrails == []
        assert cfg.mesh_policies == []
        assert cfg.compliance_rules == []

    def test_kind_dispatch(self, tmp_path):
        """Agent YAML loads as AgentConfig, not RegistryConfig."""
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        cfg = load_config(str(f))
        assert isinstance(cfg, AgentConfig)
        assert not isinstance(cfg, RegistryConfig)


class TestConfigSubmodels:
    def test_guardrail_defaults(self):
        gc = GuardrailConfig(name="test")
        assert gc.type == "pre_processing"
        assert gc.mechanism == "regex"
        assert gc.enforcement == "block"
        assert gc.scope == "all_agents"
        assert gc.priority == 0
        assert gc.config == {}

    def test_mesh_policy_defaults(self):
        mp = MeshPolicyConfig(source="a", destination="b")
        assert mp.action == "allow"
        assert mp.priority == 0

    def test_compliance_rule_source_zone(self):
        cr = ComplianceRuleConfig(name="r", type="sovereignty", source_zone="eu")
        assert cr.rule_type == "sovereignty"
        assert cr.source == "eu"

    def test_compliance_rule_source_value_fallback(self):
        cr = ComplianceRuleConfig(name="r", type="classification", source_value="pii")
        assert cr.source == "pii"

    def test_compliance_rule_destination_zone(self):
        cr = ComplianceRuleConfig(name="r", type="sovereignty", destination_zone="us")
        assert cr.destination == "us"

    def test_compliance_rule_destination_value_fallback(self):
        cr = ComplianceRuleConfig(name="r", type="classification", dest_value="public")
        assert cr.destination == "public"

    def test_compliance_rule_empty_source(self):
        cr = ComplianceRuleConfig(name="r", type="sovereignty")
        assert cr.source == ""
        assert cr.destination == ""


class TestConfigLoader:
    def test_file_not_found(self):
        with pytest.raises(ConfigError, match="not found"):
            load_config("/nonexistent/path.yaml")

    def test_validate_valid_returns_empty(self, tmp_path):
        f = tmp_path / "agent.yaml"
        f.write_text(VALID_AGENT_YAML)
        errors = validate_config(str(f))
        assert errors == []

    def test_validate_invalid_returns_errors(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("kind: Unknown\n")
        errors = validate_config(str(f))
        assert len(errors) > 0
