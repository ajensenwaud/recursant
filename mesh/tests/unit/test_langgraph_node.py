"""Tests for RecursantA2ANode LangGraph integration."""

from unittest.mock import MagicMock, patch

import pytest

from runtime.client.a2a_client import A2AResponse, RecursantClientError
from runtime.client.langgraph_node import RecursantA2ANode


class TestNodeInit:
    def test_default_sidecar_url(self):
        node = RecursantA2ANode(skill="fact-check")
        assert node._client.sidecar_url == "http://localhost:9901"

    def test_custom_sidecar_port(self):
        node = RecursantA2ANode(skill="fact-check", sidecar_port=9902)
        assert node._client.sidecar_url == "http://localhost:9902"

    def test_custom_sidecar_url(self):
        node = RecursantA2ANode(skill="fact-check", sidecar_url="http://custom:8080")
        assert node._client.sidecar_url == "http://custom:8080"

    def test_sidecar_url_overrides_port(self):
        node = RecursantA2ANode(
            skill="fact-check", sidecar_port=9999, sidecar_url="http://custom:8080"
        )
        assert node._client.sidecar_url == "http://custom:8080"

    def test_default_keys(self):
        node = RecursantA2ANode(skill="fact-check")
        assert node.input_key == "query"
        assert node.output_key == "result"

    def test_custom_keys(self):
        node = RecursantA2ANode(
            skill="fact-check", input_key="question", output_key="answer"
        )
        assert node.input_key == "question"
        assert node.output_key == "answer"

    def test_timeout_propagated(self):
        node = RecursantA2ANode(skill="fact-check", timeout_seconds=60)
        assert node._timeout == 60


class TestNodeCall:
    def test_calls_sidecar_with_correct_skill(self):
        node = RecursantA2ANode(skill="fact-check")
        mock_response = A2AResponse(
            status="completed",
            artifacts=[{"text": "True"}],
        )
        node._client.send_task = MagicMock(return_value=mock_response)

        result = node({"query": "Is the sky blue?"})

        node._client.send_task.assert_called_once_with(
            skill="fact-check",
            message="Is the sky blue?",
            timeout=30.0,
        )
        assert result == {"result": "True"}

    def test_uses_custom_input_key(self):
        node = RecursantA2ANode(skill="fact-check", input_key="question")
        mock_response = A2AResponse(status="completed", artifacts=[{"text": "Yes"}])
        node._client.send_task = MagicMock(return_value=mock_response)

        result = node({"question": "Is water wet?"})

        node._client.send_task.assert_called_once_with(
            skill="fact-check",
            message="Is water wet?",
            timeout=30.0,
        )

    def test_uses_custom_output_key(self):
        node = RecursantA2ANode(skill="fact-check", output_key="answer")
        mock_response = A2AResponse(status="completed", artifacts=[{"text": "42"}])
        node._client.send_task = MagicMock(return_value=mock_response)

        result = node({"query": "What is the meaning of life?"})
        assert "answer" in result
        assert result["answer"] == "42"

    def test_fallback_skill_on_primary_failure(self):
        node = RecursantA2ANode(
            skill="fact-check-v1", fallback_skill="fact-check-v2"
        )
        mock_response = A2AResponse(status="completed", artifacts=[{"text": "Fallback"}])

        call_count = 0

        def side_effect(skill, message, timeout):
            nonlocal call_count
            call_count += 1
            if skill == "fact-check-v1":
                raise RecursantClientError("Primary failed")
            return mock_response

        node._client.send_task = MagicMock(side_effect=side_effect)

        result = node({"query": "test"})
        assert result == {"result": "Fallback"}
        assert call_count == 2

    def test_raises_when_no_fallback(self):
        node = RecursantA2ANode(skill="fact-check")
        node._client.send_task = MagicMock(
            side_effect=RecursantClientError("Failed")
        )

        with pytest.raises(RecursantClientError):
            node({"query": "test"})

    def test_raises_when_fallback_also_fails(self):
        node = RecursantA2ANode(skill="primary", fallback_skill="fallback")
        node._client.send_task = MagicMock(
            side_effect=RecursantClientError("Both failed")
        )

        with pytest.raises(RecursantClientError, match="Both failed"):
            node({"query": "test"})

    def test_multiple_artifacts_joined(self):
        node = RecursantA2ANode(skill="fact-check")
        mock_response = A2AResponse(
            status="completed",
            artifacts=[{"text": "Line 1"}, {"text": "Line 2"}],
        )
        node._client.send_task = MagicMock(return_value=mock_response)

        result = node({"query": "test"})
        assert result == {"result": "Line 1\nLine 2"}


class TestQueryExtraction:
    def test_extracts_from_input_key(self):
        node = RecursantA2ANode(skill="test")
        assert node._extract_query({"query": "hello"}) == "hello"

    def test_extracts_from_skill_name(self):
        node = RecursantA2ANode(skill="fact-check", input_key="query")
        assert node._extract_query({"fact-check": "check this"}) == "check this"

    def test_extracts_from_input_fallback(self):
        node = RecursantA2ANode(skill="test", input_key="query")
        assert node._extract_query({"input": "from input"}) == "from input"

    def test_extracts_from_messages(self):
        node = RecursantA2ANode(skill="test", input_key="query")
        state = {"messages": [{"content": "first"}, {"content": "last"}]}
        assert node._extract_query(state) == "last"

    def test_raises_on_missing_key(self):
        node = RecursantA2ANode(skill="test")
        with pytest.raises(ValueError, match="Cannot extract query"):
            node._extract_query({"unrelated": "data"})

    def test_non_string_value_converted(self):
        node = RecursantA2ANode(skill="test")
        result = node._extract_query({"query": 42})
        assert result == "42"


class TestResponseFormatting:
    def test_artifact_text_extracted(self):
        response = A2AResponse(
            status="completed", artifacts=[{"text": "result text"}]
        )
        assert RecursantA2ANode._format_response(response) == "result text"

    def test_no_artifacts_uses_raw(self):
        response = A2AResponse(status="completed", artifacts=[], raw={"foo": "bar"})
        result = RecursantA2ANode._format_response(response)
        assert "foo" in result

    def test_artifact_without_text_skipped(self):
        response = A2AResponse(
            status="completed",
            artifacts=[{"type": "binary"}, {"text": "valid"}],
        )
        assert RecursantA2ANode._format_response(response) == "valid"


class TestImports:
    def test_import_from_package(self):
        from runtime.client import RecursantA2ANode
        assert RecursantA2ANode is not None

    def test_node_is_callable(self):
        node = RecursantA2ANode(skill="test")
        assert callable(node)
