"""Unit tests for the sidecar tool call handler."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from runtime.sidecar.tools import handle_tool_call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit():
    """Create a mock AuditInterceptor."""
    audit = MagicMock()
    audit.buffer_record = MagicMock()
    return audit


def _make_tools():
    """Sample cached tool list."""
    return [
        {
            "name": "verify_customer",
            "endpoint_url": "http://stub-apis:6000/api/customer-master/verify",
            "http_method": "POST",
            "parameters_schema": None,
        },
        {
            "name": "assess_credit",
            "endpoint_url": "http://stub-apis:6000/api/credit/assess",
            "http_method": "POST",
            "parameters_schema": None,
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHandleToolCall:

    @patch("runtime.sidecar.tools.httpx.request")
    def test_tool_found_success(self, mock_request):
        """Approved+assigned tool call succeeds and returns result."""
        mock_request.return_value = MagicMock(
            status_code=200,
            text='{"verified": true}',
            json=lambda: {"verified": True},
        )

        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={"ban": "12345", "pin": "9999"},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 200
        assert result["tool_name"] == "verify_customer"
        assert result["result"]["verified"] is True
        audit.buffer_record.assert_called_once()
        record = audit.buffer_record.call_args[0][0]
        assert record.a2a_method == "tools/call"
        assert record.outcome == "success"

    def test_tool_not_found_returns_403(self):
        """Tool not in cached list returns 403."""
        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="unknown_tool",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 403
        assert "not found" in result["error"]
        audit.buffer_record.assert_called_once()
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "blocked"
        assert record.decision == "block"

    def test_tool_not_found_empty_cache(self):
        """Empty cache returns 403."""
        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=[],
            audit_interceptor=audit,
        )

        assert status == 403

    def test_tool_not_found_none_cache(self):
        """None cache returns 403."""
        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=None,
            audit_interceptor=audit,
        )

        assert status == 403

    @patch("runtime.sidecar.tools.httpx.request")
    def test_tool_endpoint_error(self, mock_request):
        """HTTP error from tool endpoint returns 200 with error status."""
        mock_request.return_value = MagicMock(
            status_code=500,
            text='{"error": "internal"}',
            json=lambda: {"error": "internal"},
        )

        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={"ban": "12345"},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 200
        assert result["status"] == 500
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "error"

    @patch("runtime.sidecar.tools.httpx.request")
    def test_tool_endpoint_unreachable(self, mock_request):
        """ConnectError returns 502."""
        mock_request.side_effect = httpx.ConnectError("connection refused")

        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 502
        assert "unreachable" in result["error"]
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "error"

    @patch("runtime.sidecar.tools.httpx.request")
    def test_tool_endpoint_timeout(self, mock_request):
        """TimeoutException returns 502."""
        mock_request.side_effect = httpx.TimeoutException("timed out")

        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 502

    @patch("runtime.sidecar.tools.httpx.request")
    def test_audit_record_includes_details(self, mock_request):
        """Audit record includes tool_name, endpoint_url, arguments_hash."""
        mock_request.return_value = MagicMock(
            status_code=200,
            text='{}',
            json=lambda: {},
        )

        audit = _make_audit()
        handle_tool_call(
            tool_name="verify_customer",
            arguments={"ban": "12345"},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        record = audit.buffer_record.call_args[0][0]
        assert record.details["tool_name"] == "verify_customer"
        assert "endpoint_url" in record.details
        assert "arguments_hash" in record.details
        assert record.details["response_status"] == 200

    def test_no_audit_interceptor_does_not_crash(self):
        """Passing None audit interceptor does not raise."""
        result, status = handle_tool_call(
            tool_name="unknown",
            arguments={},
            source_agent_name="test",
            cached_tools=[],
            audit_interceptor=None,
        )

        assert status == 403

    def test_tool_exists_but_not_assigned_to_caller(self):
        """Agent's cached tools only include its own assignments — calling
        a tool that exists globally but isn't in the agent's cache returns 403."""
        audit = _make_audit()
        # Agent B's cached tools only has assess_credit — verify_customer is
        # assigned to Agent A, so it's not in Agent B's cache.
        agent_b_tools = [
            {
                "name": "assess_credit",
                "endpoint_url": "http://stub-apis:6000/api/credit/assess",
                "http_method": "POST",
                "parameters_schema": None,
            },
        ]

        result, status = handle_tool_call(
            tool_name="verify_customer",  # exists globally but not assigned to Agent B
            arguments={"ban": "12345"},
            source_agent_name="Agent B",
            cached_tools=agent_b_tools,
            audit_interceptor=audit,
        )

        assert status == 403
        assert "not found" in result["error"]
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "blocked"
        assert record.decision == "block"
        assert record.source_agent_name == "Agent B"

    @patch("runtime.sidecar.tools.httpx.request")
    def test_non_json_response(self, mock_request):
        """Non-JSON response from endpoint is returned as raw text."""
        mock_request.return_value = MagicMock(
            status_code=200,
            text='plain text result',
        )
        mock_request.return_value.json.side_effect = ValueError("not json")

        audit = _make_audit()
        result, status = handle_tool_call(
            tool_name="verify_customer",
            arguments={},
            source_agent_name="Auth Agent",
            cached_tools=_make_tools(),
            audit_interceptor=audit,
        )

        assert status == 200
        assert result["result"]["raw"] == "plain text result"
