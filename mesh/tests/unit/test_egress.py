"""Unit tests for the sidecar egress proxy handler."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from runtime.sidecar.tools import _evaluate_egress_rules, handle_egress_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit():
    audit = MagicMock()
    audit.buffer_record = MagicMock()
    return audit


# ---------------------------------------------------------------------------
# _evaluate_egress_rules tests
# ---------------------------------------------------------------------------


class TestEvaluateEgressRules:

    def test_empty_rules_default_deny(self):
        """No rules → default deny."""
        assert _evaluate_egress_rules("http://example.com/api", []) == "deny"

    def test_exact_match_allow(self):
        rules = [{"url_pattern": "http://example.com/*", "action": "allow"}]
        assert _evaluate_egress_rules("http://example.com/api", rules) == "allow"

    def test_exact_match_deny(self):
        rules = [{"url_pattern": "http://evil.com/*", "action": "deny"}]
        assert _evaluate_egress_rules("http://evil.com/api", rules) == "deny"

    def test_no_match_default_deny(self):
        rules = [{"url_pattern": "http://allowed.com/*", "action": "allow"}]
        assert _evaluate_egress_rules("http://other.com/api", rules) == "deny"

    def test_first_match_wins(self):
        """Rules are already sorted by priority; first match wins."""
        rules = [
            {"url_pattern": "http://stub-apis:6000/*", "action": "allow", "priority": 0},
            {"url_pattern": "*", "action": "deny", "priority": 100},
        ]
        assert _evaluate_egress_rules("http://stub-apis:6000/api/test", rules) == "allow"

    def test_catch_all_deny(self):
        """Catch-all deny blocks unmatched URLs."""
        rules = [
            {"url_pattern": "http://stub-apis:6000/*", "action": "allow", "priority": 0},
            {"url_pattern": "*", "action": "deny", "priority": 100},
        ]
        assert _evaluate_egress_rules("http://evil.com/data", rules) == "deny"

    def test_wildcard_glob_matching(self):
        """fnmatch-style glob patterns work."""
        rules = [{"url_pattern": "http://*.internal.com/*", "action": "allow"}]
        assert _evaluate_egress_rules("http://api.internal.com/v1/data", rules) == "allow"

    def test_priority_ordering_matters(self):
        """Lower-priority (first in list) rule takes precedence."""
        rules = [
            {"url_pattern": "http://api.com/public/*", "action": "allow", "priority": 0},
            {"url_pattern": "http://api.com/*", "action": "deny", "priority": 10},
        ]
        assert _evaluate_egress_rules("http://api.com/public/data", rules) == "allow"
        assert _evaluate_egress_rules("http://api.com/private/data", rules) == "deny"


# ---------------------------------------------------------------------------
# handle_egress_request tests
# ---------------------------------------------------------------------------


class TestHandleEgressRequest:

    @patch("runtime.sidecar.tools.httpx.request")
    def test_allowed_url_succeeds(self, mock_request):
        """Request to allowed URL succeeds and creates audit record."""
        mock_request.return_value = MagicMock(
            status_code=200,
            text='{"data": "ok"}',
            json=lambda: {"data": "ok"},
        )

        rules = [
            {"url_pattern": "http://stub-apis:6000/*", "action": "allow"},
            {"url_pattern": "*", "action": "deny"},
        ]
        audit = _make_audit()

        result, status = handle_egress_request(
            method="GET",
            url="http://stub-apis:6000/api/test",
            headers=None,
            body=None,
            source_agent_name="Test Agent",
            cached_egress_rules=rules,
            audit_interceptor=audit,
        )

        assert status == 200
        assert result["result"]["data"] == "ok"
        audit.buffer_record.assert_called_once()
        record = audit.buffer_record.call_args[0][0]
        assert record.a2a_method == "egress/http"
        assert record.outcome == "success"

    def test_denied_url_returns_403(self):
        """Request to denied URL returns 403."""
        rules = [
            {"url_pattern": "http://allowed.com/*", "action": "allow"},
            {"url_pattern": "*", "action": "deny"},
        ]
        audit = _make_audit()

        result, status = handle_egress_request(
            method="GET",
            url="http://evil.com/steal-data",
            headers=None,
            body=None,
            source_agent_name="Test Agent",
            cached_egress_rules=rules,
            audit_interceptor=audit,
        )

        assert status == 403
        assert "denied" in result["error"]
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "blocked"
        assert record.decision == "block"

    def test_no_rules_default_deny(self):
        """No rules → default deny."""
        audit = _make_audit()

        result, status = handle_egress_request(
            method="GET",
            url="http://any.com",
            headers=None,
            body=None,
            source_agent_name="Test Agent",
            cached_egress_rules=[],
            audit_interceptor=audit,
        )

        assert status == 403

    def test_none_rules_default_deny(self):
        """None rules → default deny."""
        audit = _make_audit()

        result, status = handle_egress_request(
            method="GET",
            url="http://any.com",
            headers=None,
            body=None,
            source_agent_name="Test Agent",
            cached_egress_rules=None,
            audit_interceptor=audit,
        )

        assert status == 403

    @patch("runtime.sidecar.tools.httpx.request")
    def test_egress_endpoint_unreachable(self, mock_request):
        """ConnectError returns 502."""
        mock_request.side_effect = httpx.ConnectError("connection refused")

        rules = [{"url_pattern": "*", "action": "allow"}]
        audit = _make_audit()

        result, status = handle_egress_request(
            method="GET",
            url="http://unreachable.com",
            headers=None,
            body=None,
            source_agent_name="Test Agent",
            cached_egress_rules=rules,
            audit_interceptor=audit,
        )

        assert status == 502
        record = audit.buffer_record.call_args[0][0]
        assert record.outcome == "error"

    @patch("runtime.sidecar.tools.httpx.request")
    def test_egress_audit_record_details(self, mock_request):
        """Audit record includes method, url, response_status."""
        mock_request.return_value = MagicMock(
            status_code=200,
            text='{}',
            json=lambda: {},
        )

        rules = [{"url_pattern": "*", "action": "allow"}]
        audit = _make_audit()

        handle_egress_request(
            method="POST",
            url="http://api.com/data",
            headers={"X-Custom": "value"},
            body={"key": "value"},
            source_agent_name="Test Agent",
            cached_egress_rules=rules,
            audit_interceptor=audit,
        )

        record = audit.buffer_record.call_args[0][0]
        assert record.details["method"] == "POST"
        assert record.details["url"] == "http://api.com/data"
        assert record.details["response_status"] == 200

    def test_no_audit_interceptor_does_not_crash(self):
        """Passing None audit interceptor does not raise."""
        result, status = handle_egress_request(
            method="GET",
            url="http://any.com",
            headers=None,
            body=None,
            source_agent_name="test",
            cached_egress_rules=[],
            audit_interceptor=None,
        )

        assert status == 403
