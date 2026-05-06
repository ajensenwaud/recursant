"""
Tests for guardrail event buffering and shipping.

Tests cover:
- Event buffer initialisation (starts empty)
- Event emission on successful evaluation
- Event emission with is_error=True on evaluation error
- drain_events() returns all events and clears buffer
- drain_events() returns empty list when no events
- Buffer maxlen (deque capped at 5000)
- RegistryClient.ship_guardrail_events() sends POST with enriched events
- RegistryClient.ship_guardrail_events() no-op for empty events
- Event structure has all expected keys
"""

import asyncio
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from runtime.sidecar.guardrail_eval import GuardrailEvaluator, GuardrailResult
from runtime.sidecar.registry_client import RegistryClient, RegistryClientError


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _regex_guardrail_config(
    guardrail_id="g1",
    name="test",
    patterns=None,
    enforcement_mode="block",
):
    """Create a regex guardrail config dict."""
    if patterns is None:
        patterns = [{"name": "test", "pattern": "bad word", "action": "block"}]
    return {
        "id": guardrail_id,
        "name": name,
        "type": "pre_processing",
        "mechanism": "regex",
        "enforcement_mode": enforcement_mode,
        "config": {"patterns": patterns},
    }


# ============================================================================
# Event buffer initialisation
# ============================================================================


class TestEventBufferInit:
    def test_event_buffer_starts_empty(self):
        """GuardrailEvaluator._event_buffer starts as an empty deque."""
        evaluator = GuardrailEvaluator()
        assert len(evaluator._event_buffer) == 0
        assert isinstance(evaluator._event_buffer, deque)

    def test_buffer_maxlen_is_5000(self):
        """The event buffer deque should have maxlen=5000."""
        evaluator = GuardrailEvaluator()
        assert evaluator._event_buffer.maxlen == 5000


# ============================================================================
# Event emission on successful evaluation
# ============================================================================


class TestEventEmissionOnSuccess:
    def test_evaluate_emits_event_on_regex_match(self):
        """A successful regex evaluation that matches should emit an event."""
        evaluator = GuardrailEvaluator()
        config = _regex_guardrail_config()

        _run(evaluator.evaluate(config, "this contains a bad word"))

        assert len(evaluator._event_buffer) == 1
        event = evaluator._event_buffer[0]
        assert event["action"] == "block"
        assert event["is_error"] is False
        assert event["error_message"] == ""

    def test_evaluate_emits_event_on_regex_pass(self):
        """A successful regex evaluation with no match should also emit an event."""
        evaluator = GuardrailEvaluator()
        config = _regex_guardrail_config()

        _run(evaluator.evaluate(config, "this is a clean message"))

        assert len(evaluator._event_buffer) == 1
        event = evaluator._event_buffer[0]
        assert event["action"] == "pass"
        assert event["is_error"] is False


# ============================================================================
# Event emission on evaluation error
# ============================================================================


class TestEventEmissionOnError:
    def test_evaluate_emits_error_event(self):
        """When evaluation raises an exception, the event should have is_error=True."""
        from unittest.mock import AsyncMock

        mock_weaviate = AsyncMock()
        mock_weaviate.query_near_text.side_effect = Exception("Connection refused")
        evaluator = GuardrailEvaluator(weaviate_client=mock_weaviate)

        config = {
            "id": "g-err",
            "name": "error-guardrail",
            "type": "pre_processing",
            "mechanism": "vector_lookup",
            "enforcement_mode": "block",
            "config": {"collection_name": "Test"},
        }

        _run(evaluator.evaluate(config, "test input"))

        assert len(evaluator._event_buffer) == 1
        event = evaluator._event_buffer[0]
        assert event["is_error"] is True
        assert "Connection refused" in event["error_message"]
        assert event["action"] == "pass"  # fail-open


# ============================================================================
# drain_events()
# ============================================================================


class TestDrainEvents:
    def test_drain_returns_all_events_and_clears_buffer(self):
        """drain_events() should return all buffered events and clear the buffer."""
        evaluator = GuardrailEvaluator()
        config = _regex_guardrail_config()

        # Emit three events
        _run(evaluator.evaluate(config, "bad word one"))
        _run(evaluator.evaluate(config, "clean message"))
        _run(evaluator.evaluate(config, "another bad word"))

        assert len(evaluator._event_buffer) == 3

        drained = evaluator.drain_events()
        assert len(drained) == 3
        assert len(evaluator._event_buffer) == 0

    def test_drain_returns_empty_list_when_no_events(self):
        """drain_events() should return an empty list when the buffer is empty."""
        evaluator = GuardrailEvaluator()
        drained = evaluator.drain_events()
        assert drained == []
        assert isinstance(drained, list)


# ============================================================================
# Buffer maxlen enforcement
# ============================================================================


class TestBufferMaxlen:
    def test_buffer_does_not_exceed_5000(self):
        """The deque maxlen should prevent the buffer from growing beyond 5000."""
        evaluator = GuardrailEvaluator()

        # Directly append more than 5000 items to verify the deque enforces the cap
        for i in range(5100):
            evaluator._event_buffer.append({"index": i})

        assert len(evaluator._event_buffer) == 5000
        # The first 100 items should have been evicted; first remaining is index 100
        assert evaluator._event_buffer[0]["index"] == 100


# ============================================================================
# Event structure
# ============================================================================


class TestEventStructure:
    def test_emitted_event_has_all_expected_keys(self):
        """An emitted event should contain all the required keys."""
        evaluator = GuardrailEvaluator()
        config = _regex_guardrail_config(
            guardrail_id="g-struct",
            name="structure-test",
        )

        _run(evaluator.evaluate(config, "bad word triggers match"))

        assert len(evaluator._event_buffer) == 1
        event = evaluator._event_buffer[0]

        expected_keys = {
            "guardrail_id",
            "guardrail_name",
            "guardrail_type",
            "mechanism",
            "action",
            "reasoning",
            "latency_ms",
            "matched_pattern",
            "input_hash",
            "is_error",
            "error_message",
        }
        assert set(event.keys()) == expected_keys

        # Verify values are populated correctly
        assert event["guardrail_id"] == "g-struct"
        assert event["guardrail_name"] == "structure-test"
        assert event["mechanism"] == "regex"
        assert isinstance(event["latency_ms"], int)
        assert event["latency_ms"] >= 0


# ============================================================================
# RegistryClient.ship_guardrail_events()
# ============================================================================


class TestShipGuardrailEvents:
    def test_ships_events_with_post(self):
        """ship_guardrail_events() should POST to /v1/mesh/guardrail-events
        with agent_name enriched into each event."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "ok", "count": 2}

        with patch("httpx.request", return_value=mock_response) as mock_request:
            client = RegistryClient(
                registry_url="http://test-registry:5000",
                api_key="test-key",
                tenant_id="default",
            )

            events = [
                {"guardrail_id": "g1", "action": "block", "reasoning": "matched"},
                {"guardrail_id": "g2", "action": "pass", "reasoning": "clean"},
            ]
            result = client.ship_guardrail_events(events, agent_name="my-agent")

        # Verify the POST was made
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"  # method
        assert "/v1/mesh/guardrail-events" in call_args[0][1]  # URL

        # Verify events were enriched with agent_name
        sent_json = call_args[1]["json"]
        assert "events" in sent_json
        for event in sent_json["events"]:
            assert event["agent_name"] == "my-agent"

        # Verify return value
        assert result["count"] == 2

    def test_no_op_for_empty_events(self):
        """ship_guardrail_events() should return early without making a
        request when the events list is empty."""
        with patch("httpx.request") as mock_request:
            client = RegistryClient(registry_url="http://test-registry:5000")
            result = client.ship_guardrail_events([], agent_name="my-agent")

        mock_request.assert_not_called()
        assert result["status"] == "no events"
        assert result["count"] == 0
