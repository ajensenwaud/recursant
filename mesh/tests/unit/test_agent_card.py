"""Tests for Agent Card loading, enrichment, and serialisation."""

from pathlib import Path

import pytest
from a2a.types import AgentCard

from runtime.sidecar.agent_card import (
    RECURSANT_EXTENSION_URI,
    agent_card_to_json,
    build_agent_card,
    load_agent_card_yaml,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestLoadAgentCardYaml:
    def test_load_full_card(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        assert raw["name"] == "Fact Checker Agent"
        assert len(raw["skills"]) == 2
        assert raw["skills"][0]["id"] == "fact-check"

    def test_load_minimal_card(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        assert raw["name"] == "Minimal Agent"
        assert len(raw["skills"]) == 1

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_agent_card_yaml("/nonexistent.yaml")


class TestBuildAgentCard:
    def test_full_card_builds_valid_a2a_type(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert isinstance(card, AgentCard)
        assert card.name == "Fact Checker Agent"
        assert card.description == "Verifies factual claims using multiple sources"
        assert card.version == "1.0.0"
        assert card.url == "https://host-b:8443"

    def test_skills_mapped_correctly(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert len(card.skills) == 2
        assert card.skills[0].id == "fact-check"
        assert card.skills[0].name == "Fact Check"
        assert "verification" in card.skills[0].tags
        assert card.skills[0].examples == ["Is the Eiffel Tower 330m tall?"]
        assert card.skills[1].id == "summarise"

    def test_capabilities_set(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert card.capabilities.streaming is False
        assert card.capabilities.push_notifications is False

    def test_provider_mapped(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert card.provider is not None
        assert card.provider.organization == "Recursant"
        assert card.provider.url == "https://recursant.ai"

    def test_security_schemes_mapped(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert card.security_schemes is not None
        assert "mtls" in card.security_schemes
        assert card.security == [{"mtls": []}]

    def test_default_io_modes(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(raw, sidecar_url="https://host-b:8443")

        assert card.default_input_modes == ["text"]
        assert card.default_output_modes == ["text"]

    def test_minimal_card_uses_defaults(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(raw, sidecar_url="http://localhost:8443")

        assert card.name == "Minimal Agent"
        assert card.version == "0.0.0"  # default
        assert card.description == ""  # default
        assert card.default_input_modes == ["text"]  # default
        assert len(card.skills) == 1
        assert card.provider is None
        assert card.security_schemes is None

    def test_sidecar_url_becomes_card_url(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(raw, sidecar_url="https://my-host:9999")

        assert card.url == "https://my-host:9999"


class TestRecursantExtension:
    def test_extension_added_by_default(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(raw, sidecar_url="http://localhost:8443")

        extensions = card.capabilities.extensions
        assert extensions is not None
        assert len(extensions) == 1
        assert extensions[0].uri == RECURSANT_EXTENSION_URI
        assert extensions[0].params["sidecar_version"] == "0.1.0"

    def test_extension_includes_registry_url(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(
            raw,
            sidecar_url="http://localhost:8443",
            registry_url="http://registry:5000",
        )

        params = card.capabilities.extensions[0].params
        assert params["registry_url"] == "http://registry:5000"

    def test_extension_includes_tenant_id(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(
            raw,
            sidecar_url="http://localhost:8443",
            tenant_id="acme-corp",
        )

        params = card.capabilities.extensions[0].params
        assert params["tenant_id"] == "acme-corp"

    def test_extension_not_required(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(raw, sidecar_url="http://localhost:8443")

        assert card.capabilities.extensions[0].required is False


class TestAgentCardToJson:
    def test_serialises_to_dict(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(
            raw,
            sidecar_url="https://host-b:8443",
            registry_url="http://registry:5000",
        )
        result = agent_card_to_json(card)

        assert isinstance(result, dict)
        assert result["name"] == "Fact Checker Agent"
        assert result["url"] == "https://host-b:8443"
        assert result["version"] == "1.0.0"
        assert len(result["skills"]) == 2

    def test_excludes_none_fields(self):
        raw = load_agent_card_yaml(FIXTURES / "agent-card-minimal.yaml")
        card = build_agent_card(raw, sidecar_url="http://localhost:8443")
        result = agent_card_to_json(card)

        assert "provider" not in result
        assert "security_schemes" not in result
        assert "documentation_url" not in result

    def test_json_serialisable(self):
        """The output must be JSON-serialisable (no datetime, UUID, etc.)."""
        import json

        raw = load_agent_card_yaml(FIXTURES / "agent-card-fact-checker.yaml")
        card = build_agent_card(
            raw,
            sidecar_url="https://host-b:8443",
            registry_url="http://registry:5000",
            tenant_id="default",
        )
        result = agent_card_to_json(card)

        # Should not raise
        json_str = json.dumps(result)
        assert '"Fact Checker Agent"' in json_str
