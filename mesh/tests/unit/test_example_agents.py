"""Tests for the example LangGraph agents.

Tests run without LLM keys — agents use their fallback logic.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add examples to path so we can import agent modules
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))

from agent_a.agent import (
    compile_result,
    create_agent_app as create_agent_a_app,
    generate_claim,
    _extract_message_text,
)
from agent_b.agent import (
    create_agent_app as create_agent_b_app,
    format_evidence,
    parse_claim,
    verify_claim,
)


# ===========================================================================
# Agent A: Research Assistant
# ===========================================================================


class TestAgentANodes:
    def test_generate_claim_fallback(self):
        """Without LLM, should return a claim based on the query."""
        with patch("agent_a.agent._get_llm", return_value=None):
            claim = generate_claim("height of the Eiffel Tower")
        assert "Eiffel Tower" in claim

    def test_compile_result_fallback(self):
        with patch("agent_a.agent._get_llm", return_value=None):
            result = compile_result(
                query="Eiffel Tower height",
                claim="The Eiffel Tower is 330m tall",
                fact_check="Verified: TRUE",
            )
        assert "Eiffel Tower" in result
        assert "330m" in result
        assert "Verified" in result


class TestAgentAApp:
    def _make_jsonrpc(self, text="Is the Eiffel Tower 330m tall?"):
        return {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                }
            },
        }

    def test_health_endpoint(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.get_json()["agent"] == "research-assistant"

    def test_message_send_returns_result(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "req-1"
        assert data["result"]["status"] == "completed"
        assert len(data["result"]["artifacts"]) >= 1

    def test_message_send_artifact_contains_query(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc("population of Tokyo"))

        data = resp.get_json()
        text = data["result"]["artifacts"][0]["text"]
        assert "Tokyo" in text

    def test_invalid_json_returns_error(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.post("/a2a", data="not json", content_type="application/json")

        assert resp.status_code == 400

    def test_unsupported_method(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.post("/a2a", json={
            "jsonrpc": "2.0", "id": "1", "method": "tasks/subscribe", "params": {},
        })

        assert resp.status_code == 404

    def test_missing_message_text(self):
        app = create_agent_a_app()
        client = app.test_client()

        resp = client.post("/a2a", json={
            "jsonrpc": "2.0", "id": "1", "method": "message/send",
            "params": {"message": {"role": "user", "parts": []}},
        })

        data = resp.get_json()
        assert data["result"]["status"] == "failed"


# ===========================================================================
# Agent B: Fact Checker
# ===========================================================================


class TestAgentBNodes:
    def test_parse_claim_fallback(self):
        with patch("agent_b.agent._get_llm", return_value=None):
            parsed = parse_claim("The Eiffel Tower is 330m tall")
        assert parsed["claim"] == "The Eiffel Tower is 330m tall"
        assert parsed["original"] == "The Eiffel Tower is 330m tall"

    def test_verify_claim_fallback(self):
        with patch("agent_b.agent._get_llm", return_value=None):
            result = verify_claim({"claim": "The Eiffel Tower is 330m tall"})
        assert result["verdict"] == "unverifiable"
        assert "Eiffel Tower" in result["raw_response"]

    def test_format_evidence_fallback(self):
        parsed = {"claim": "The sky is blue", "original": "The sky is blue"}
        verification = {"verdict": "unverifiable", "raw_response": "No LLM"}

        with patch("agent_b.agent._get_llm", return_value=None):
            evidence = format_evidence(parsed, verification)
        assert "sky is blue" in evidence
        assert "unverifiable" in evidence


class TestAgentBApp:
    def _make_jsonrpc(self, text="Is the Eiffel Tower 330m tall?"):
        return {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                }
            },
        }

    def test_health_endpoint(self):
        app = create_agent_b_app()
        client = app.test_client()

        resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.get_json()["agent"] == "fact-checker"

    def test_message_send_returns_result(self):
        app = create_agent_b_app()
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["jsonrpc"] == "2.0"
        assert data["result"]["status"] == "completed"
        assert len(data["result"]["artifacts"]) >= 1

    def test_message_send_contains_claim(self):
        app = create_agent_b_app()
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc("Humans landed on the Moon in 1969"))

        data = resp.get_json()
        text = data["result"]["artifacts"][0]["text"]
        assert "Moon" in text

    def test_invalid_json_returns_error(self):
        app = create_agent_b_app()
        client = app.test_client()

        resp = client.post("/a2a", data="not json", content_type="application/json")

        assert resp.status_code == 400

    def test_unsupported_method(self):
        app = create_agent_b_app()
        client = app.test_client()

        resp = client.post("/a2a", json={
            "jsonrpc": "2.0", "id": "1", "method": "tasks/subscribe", "params": {},
        })

        assert resp.status_code == 404


# ===========================================================================
# Message text extraction
# ===========================================================================


class TestExtractMessageText:
    def test_extracts_text_part(self):
        params = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "hello world"}],
            }
        }
        assert _extract_message_text(params) == "hello world"

    def test_returns_none_for_empty_parts(self):
        params = {"message": {"role": "user", "parts": []}}
        assert _extract_message_text(params) is None

    def test_returns_none_for_missing_message(self):
        assert _extract_message_text({}) is None

    def test_skips_non_text_parts(self):
        params = {
            "message": {
                "role": "user",
                "parts": [
                    {"kind": "image", "data": "..."},
                    {"kind": "text", "text": "found it"},
                ],
            }
        }
        assert _extract_message_text(params) == "found it"


# ===========================================================================
# Agent Card YAML files
# ===========================================================================


class TestAgentCardYAML:
    def test_agent_a_card_exists(self):
        card_path = EXAMPLES_DIR / "agent_a" / "agent_card.yaml"
        assert card_path.exists()

    def test_agent_b_card_exists(self):
        card_path = EXAMPLES_DIR / "agent_b" / "agent_card.yaml"
        assert card_path.exists()

    def test_agent_a_card_loads(self):
        import yaml
        card_path = EXAMPLES_DIR / "agent_a" / "agent_card.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        assert card["name"] == "Research Assistant"
        assert len(card["skills"]) == 2
        assert card["skills"][0]["id"] == "research"

    def test_agent_b_card_loads(self):
        import yaml
        card_path = EXAMPLES_DIR / "agent_b" / "agent_card.yaml"
        with open(card_path) as f:
            card = yaml.safe_load(f)
        assert card["name"] == "Fact Checker Agent"
        assert len(card["skills"]) == 1
        assert card["skills"][0]["id"] == "fact-check"


# ===========================================================================
# Sidecar config YAML files
# ===========================================================================


class TestSidecarConfigs:
    def test_agent_a_sidecar_config_loads(self):
        from runtime.sidecar.config import SidecarConfig
        config = SidecarConfig.from_yaml(EXAMPLES_DIR / "agent_a" / "recursant-sidecar.yaml")
        assert config.port == 9901
        assert config.a2a_port == 8443
        assert config.agent_port == 5010

    def test_agent_b_sidecar_config_loads(self):
        from runtime.sidecar.config import SidecarConfig
        config = SidecarConfig.from_yaml(EXAMPLES_DIR / "agent_b" / "recursant-sidecar.yaml")
        assert config.port == 9902
        assert config.a2a_port == 8444
        assert config.agent_port == 5011
