"""Tests for the A2A inbound server and Flask app."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from runtime.sidecar.app import create_app
from runtime.sidecar.config import (
    AuditConfig,
    AuthenticationConfig,
    AuthorisationConfig,
    FallbackRule,
    SidecarConfig,
)
from runtime.sidecar.server import (
    JSONRPCError,
    make_error_response,
    make_success_response,
    parse_jsonrpc_request,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ===========================================================================
# JSON-RPC Parsing Tests
# ===========================================================================

class TestParseJsonrpcRequest:
    def test_valid_message_send(self):
        data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "message/send",
            "params": {"message": {"role": "user", "parts": []}},
        }
        method, req_id, params, error = parse_jsonrpc_request(data)

        assert method == "message/send"
        assert req_id == "req-1"
        assert params == {"message": {"role": "user", "parts": []}}
        assert error is None

    def test_valid_tasks_get(self):
        data = {"jsonrpc": "2.0", "id": "req-2", "method": "tasks/get", "params": {"id": "task-1"}}
        method, req_id, params, error = parse_jsonrpc_request(data)

        assert method == "tasks/get"
        assert error is None

    def test_valid_tasks_cancel(self):
        data = {"jsonrpc": "2.0", "id": "req-3", "method": "tasks/cancel", "params": {"id": "task-1"}}
        method, req_id, params, error = parse_jsonrpc_request(data)

        assert method == "tasks/cancel"
        assert error is None

    def test_missing_jsonrpc_version(self):
        data = {"id": "req-1", "method": "message/send"}
        _, _, _, error = parse_jsonrpc_request(data)

        assert error is not None
        assert error["error"]["code"] == JSONRPCError.INVALID_REQUEST

    def test_wrong_jsonrpc_version(self):
        data = {"jsonrpc": "1.0", "id": "req-1", "method": "message/send"}
        _, _, _, error = parse_jsonrpc_request(data)

        assert error is not None
        assert error["error"]["code"] == JSONRPCError.INVALID_REQUEST

    def test_missing_method(self):
        data = {"jsonrpc": "2.0", "id": "req-1"}
        _, _, _, error = parse_jsonrpc_request(data)

        assert error is not None
        assert error["error"]["code"] == JSONRPCError.INVALID_REQUEST

    def test_unsupported_method(self):
        data = {"jsonrpc": "2.0", "id": "req-1", "method": "tasks/subscribe"}
        method, _, _, error = parse_jsonrpc_request(data)

        assert method == "tasks/subscribe"
        assert error is not None
        assert error["error"]["code"] == JSONRPCError.METHOD_NOT_FOUND

    def test_non_dict_input(self):
        _, _, _, error = parse_jsonrpc_request("not a dict")

        assert error is not None
        assert error["error"]["code"] == JSONRPCError.PARSE_ERROR

    def test_missing_params_defaults_to_empty_dict(self):
        data = {"jsonrpc": "2.0", "id": "req-1", "method": "message/send"}
        _, _, params, error = parse_jsonrpc_request(data)

        assert error is None
        assert params == {}

    def test_request_id_preserved_in_error(self):
        data = {"jsonrpc": "2.0", "id": "my-req-id", "method": "nonexistent/method"}
        _, _, _, error = parse_jsonrpc_request(data)

        assert error["id"] == "my-req-id"


class TestMakeResponses:
    def test_error_response_structure(self):
        resp = make_error_response("req-1", -32600, "bad request")

        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "req-1"
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "bad request"
        assert "data" not in resp["error"]

    def test_error_response_with_data(self):
        resp = make_error_response("req-1", -32600, "bad", data={"detail": "xyz"})

        assert resp["error"]["data"] == {"detail": "xyz"}

    def test_success_response_structure(self):
        resp = make_success_response("req-1", {"status": "completed"})

        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "req-1"
        assert resp["result"] == {"status": "completed"}


# ===========================================================================
# Flask App Tests
# ===========================================================================

def _make_test_config() -> SidecarConfig:
    """Config with auth disabled so tests can focus on routing."""
    return SidecarConfig(
        agent_card_path=str(FIXTURES / "agent-card-fact-checker.yaml"),
        interceptors={
            "authentication": {"enabled": False},
            "authorisation": {"enabled": False},
            "audit": {"enabled": True},
        },
    )


def _make_auth_config() -> SidecarConfig:
    """Config with API key auth enabled."""
    return SidecarConfig(
        agent_card_path=str(FIXTURES / "agent-card-fact-checker.yaml"),
        interceptors={
            "authentication": {
                "enabled": True,
                "schemes": ["api_key"],
                "api_key": "test-key",
            },
            "authorisation": {
                "enabled": True,
                "default_action": "deny",
                "fallback_rules": [
                    {"source": "*", "destination": "*", "action": "allow"},
                ],
            },
            "audit": {"enabled": True},
        },
    )


class TestAgentCardEndpoint:
    def test_serves_agent_card(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.get("/.well-known/agent.json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Fact Checker Agent"
        assert data["version"] == "1.0.0"
        assert len(data["skills"]) == 2

    def test_agent_card_has_correct_content_type(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.get("/.well-known/agent.json")

        assert "application/json" in resp.content_type

    def test_placeholder_when_card_missing(self):
        config = SidecarConfig(agent_card_path="/nonexistent/card.yaml")
        app = create_app(config)
        client = app.test_client()

        resp = client.get("/.well-known/agent.json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "unconfigured-sidecar"


class TestHealthEndpoints:
    def test_healthz_returns_ok(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.get("/healthz")

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_readyz_returns_not_ready_when_registry_unreachable(self):
        config = SidecarConfig(
            agent_card_path=str(FIXTURES / "agent-card-fact-checker.yaml"),
            registry_url="http://localhost:59999",  # nothing listening
        )
        app = create_app(config)
        client = app.test_client()

        resp = client.get("/readyz")

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "not ready"
        assert data["registry"] == "unreachable"


class TestA2AEndpoint:
    def _make_jsonrpc(self, method="message/send", params=None, req_id="req-1"):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {"message": {"role": "user", "parts": [{"kind": "text", "text": "hello"}]}},
        }

    def test_invalid_json_returns_parse_error(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a",
            data="not json",
            content_type="application/json",
        )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"]["code"] == -32700

    def test_unsupported_method_returns_method_not_found(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a",
            json=self._make_jsonrpc(method="tasks/subscribe"),
        )

        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"]["code"] == JSONRPCError.METHOD_NOT_FOUND

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_valid_request_proxied_to_agent(self, mock_proxy):
        mock_proxy.return_value = make_success_response(
            "req-1", {"status": "completed"}
        )
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "completed"
        mock_proxy.assert_called_once()

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_proxy_receives_original_request(self, mock_proxy):
        mock_proxy.return_value = make_success_response("req-1", {})

        app = create_app(_make_test_config())
        client = app.test_client()

        request_data = self._make_jsonrpc()
        client.post("/a2a", json=request_data)

        call_args = mock_proxy.call_args
        assert call_args[0][1]["method"] == "message/send"

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_agent_connect_error_returns_502(self, mock_proxy):
        import httpx
        mock_proxy.side_effect = httpx.ConnectError("connection refused")

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 502
        data = resp.get_json()
        assert data["error"]["code"] == JSONRPCError.AGENT_UNAVAILABLE

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_agent_timeout_returns_502(self, mock_proxy):
        import httpx
        mock_proxy.side_effect = httpx.TimeoutException("timed out")

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 502

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_audit_record_created_on_success(self, mock_proxy):
        mock_proxy.return_value = make_success_response("req-1", {})

        app = create_app(_make_test_config())
        client = app.test_client()

        client.post("/a2a", json=self._make_jsonrpc())

        audit = app.config["AUDIT_INTERCEPTOR"]
        # One from pipeline run + one from create_record_from_result
        assert len(audit.all_records) >= 1

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_request_id_preserved_in_response(self, mock_proxy):
        mock_proxy.return_value = make_success_response("my-custom-id", {"ok": True})

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a",
            json=self._make_jsonrpc(req_id="my-custom-id"),
        )

        data = resp.get_json()
        assert data["id"] == "my-custom-id"


class TestA2AEndpointWithAuth:
    def _make_jsonrpc(self, method="message/send", params=None, req_id="req-1"):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {"message": {"role": "user", "parts": [{"kind": "text", "text": "hello"}]}},
        }

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_api_key_auth_passes(self, mock_proxy):
        mock_proxy.return_value = make_success_response("req-1", {})

        app = create_app(_make_auth_config())
        client = app.test_client()

        resp = client.post(
            "/a2a",
            json=self._make_jsonrpc(),
            headers={"X-Sidecar-API-Key": "test-key"},
        )

        assert resp.status_code == 200

    def test_missing_api_key_returns_401(self):
        app = create_app(_make_auth_config())
        client = app.test_client()

        resp = client.post("/a2a", json=self._make_jsonrpc())

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"]["code"] == JSONRPCError.AUTHENTICATION_FAILED

    def test_wrong_api_key_returns_401(self):
        app = create_app(_make_auth_config())
        client = app.test_client()

        resp = client.post(
            "/a2a",
            json=self._make_jsonrpc(),
            headers={"X-Sidecar-API-Key": "wrong-key"},
        )

        assert resp.status_code == 401

    @patch("runtime.sidecar.server._proxy_to_agent", new_callable=AsyncMock)
    def test_cert_cn_header_used_for_auth(self, mock_proxy):
        mock_proxy.return_value = make_success_response("req-1", {})

        config = SidecarConfig(
            agent_card_path=str(FIXTURES / "agent-card-fact-checker.yaml"),
            interceptors={
                "authentication": {"enabled": True, "schemes": ["mtls"]},
                "authorisation": {
                    "enabled": True,
                    "default_action": "allow",
                },
                "audit": {"enabled": True},
            },
        )
        app = create_app(config)
        client = app.test_client()

        resp = client.post(
            "/a2a",
            json=self._make_jsonrpc(),
            headers={"X-Client-Cert-CN": "sidecar-a"},
        )

        assert resp.status_code == 200
