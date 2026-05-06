"""Tests for sidecar configuration loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from runtime.sidecar.config import LogLevel, SidecarConfig

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestSidecarConfigFromYaml:
    """Test loading config from YAML files."""

    def test_load_valid_full_config(self):
        config = SidecarConfig.from_yaml(FIXTURES / "valid-sidecar-config.yaml")

        assert config.port == 9901
        assert config.a2a_port == 8443
        assert config.agent_port == 5010
        assert config.registry_url == "http://localhost:5000"
        assert config.registry_api_key == "test-mesh-api-key"
        assert config.agent_card_path == "./agent_card.yaml"
        assert config.agent_id == "550e8400-e29b-41d4-a716-446655440000"
        assert config.log_level == LogLevel.INFO

    def test_load_tls_config(self):
        config = SidecarConfig.from_yaml(FIXTURES / "valid-sidecar-config.yaml")

        assert config.tls is not None
        assert config.tls.cert_path == "/certs/sidecar-a.pem"
        assert config.tls.key_path == "/certs/sidecar-a-key.pem"
        assert config.tls.ca_path == "/certs/ca.pem"

    def test_load_interceptor_config(self):
        config = SidecarConfig.from_yaml(FIXTURES / "valid-sidecar-config.yaml")

        assert config.interceptors.authentication.enabled is True
        assert "mtls" in config.interceptors.authentication.schemes
        assert config.interceptors.authentication.api_key == "dev-sidecar-key"

        assert config.interceptors.authorisation.enabled is True
        assert config.interceptors.authorisation.default_action == "deny"
        assert len(config.interceptors.authorisation.fallback_rules) == 2
        assert config.interceptors.authorisation.fallback_rules[0].source == "research-assistant"
        assert config.interceptors.authorisation.fallback_rules[0].action == "allow"

        assert config.interceptors.audit.enabled is True
        assert config.interceptors.audit.log_file == "/tmp/audit.log"

    def test_load_sync_intervals(self):
        config = SidecarConfig.from_yaml(FIXTURES / "valid-sidecar-config.yaml")

        assert config.heartbeat_interval_seconds == 30
        assert config.policy_sync_interval_seconds == 30
        assert config.discovery_cache_ttl_seconds == 60

    def test_load_minimal_config(self):
        config = SidecarConfig.from_yaml(FIXTURES / "minimal-sidecar-config.yaml")

        assert config.port == 9901
        assert config.registry_url == "http://registry:5000"
        assert config.agent_card_path == "./agent_card.yaml"
        # Defaults
        assert config.a2a_port == 8443
        assert config.log_level == LogLevel.INFO
        assert config.tls is None
        assert config.interceptors.authentication.enabled is True
        assert config.interceptors.authorisation.default_action == "deny"
        assert config.interceptors.audit.enabled is True
        assert config.heartbeat_interval_seconds == 30

    def test_invalid_config_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            SidecarConfig.from_yaml(FIXTURES / "invalid-sidecar-config.yaml")

        errors = exc_info.value.errors()
        error_fields = [e["loc"] for e in errors]
        # Should complain about invalid default_action and fallback rule action
        assert any("default_action" in str(loc) for loc in error_fields)

    def test_nonexistent_file_raises_error(self):
        with pytest.raises(FileNotFoundError):
            SidecarConfig.from_yaml("/nonexistent/path.yaml")


class TestSidecarConfigDefaults:
    """Test that defaults produce a valid config."""

    def test_all_defaults(self):
        config = SidecarConfig()

        assert config.port == 9901
        assert config.a2a_port == 8443
        assert config.agent_port == 5010
        assert config.registry_url == "http://localhost:5000"
        assert config.registry_api_key is None
        assert config.tls is None
        assert config.log_level == LogLevel.INFO
        assert config.interceptors.authentication.enabled is True
        assert config.interceptors.authorisation.enabled is True
        assert config.interceptors.audit.enabled is True

    def test_override_individual_fields(self):
        config = SidecarConfig(port=9999, log_level="debug")

        assert config.port == 9999
        assert config.log_level == LogLevel.DEBUG


class TestSidecarConfigNestedYaml:
    """Test that both nested and flat YAML structures work."""

    def test_nested_recursant_sidecar_key(self):
        """The valid config uses recursant.sidecar nesting."""
        config = SidecarConfig.from_yaml(FIXTURES / "valid-sidecar-config.yaml")
        assert config.port == 9901

    def test_flat_structure(self):
        """The minimal config uses flat structure."""
        config = SidecarConfig.from_yaml(FIXTURES / "minimal-sidecar-config.yaml")
        assert config.port == 9901
