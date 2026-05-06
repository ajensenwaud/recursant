"""Tests for SSE streaming support."""

import json

import pytest

from runtime.sidecar.app import create_app
from runtime.sidecar.config import (
    AuthenticationConfig,
    AuthorisationConfig,
    InterceptorsConfig,
    SidecarConfig,
)
from runtime.sidecar.server import SUPPORTED_METHODS


class TestSSESupport:
    def test_send_subscribe_is_supported(self):
        assert "tasks/sendSubscribe" in SUPPORTED_METHODS

    def test_sse_endpoint_returns_event_stream(self):
        """The /a2a endpoint with tasks/sendSubscribe should return SSE content type.

        Since there's no real agent to stream from, this verifies the endpoint
        handles the SSE path (returns 502 when agent is unavailable rather than
        a JSON-RPC error about unsupported method).
        """
        config = SidecarConfig(
            interceptors=InterceptorsConfig(
                authentication=AuthenticationConfig(enabled=False),
                authorisation=AuthorisationConfig(enabled=False, default_action="allow"),
            ),
        )
        app = create_app(config)

        with app.test_client() as client:
            data = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/sendSubscribe",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "stream this"}],
                    }
                },
            }
            resp = client.post("/a2a", json=data)

            # Agent is not running so we get an error,
            # but the key point is it didn't return "method not found"
            # and it attempted to stream (502 = agent unavailable)
            assert resp.status_code in (200, 502)
            response_data = resp.get_json()
            if response_data and "error" in response_data:
                assert response_data["error"]["code"] != -32601  # not "method not found"

    def test_regular_method_still_works(self):
        """Standard JSON-RPC methods should still work normally."""
        config = SidecarConfig(
            interceptors=InterceptorsConfig(
                authentication=AuthenticationConfig(enabled=False),
                authorisation=AuthorisationConfig(enabled=False, default_action="allow"),
            ),
        )
        app = create_app(config)

        with app.test_client() as client:
            data = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "hello"}],
                    }
                },
            }
            resp = client.post("/a2a", json=data)
            # Will fail at agent proxy (no agent running) but not at method validation
            response_data = resp.get_json()
            if "error" in response_data:
                # Should be agent unavailable, not method not found
                assert response_data["error"]["code"] != -32601

    def test_blocked_sse_request_returns_json(self):
        """If interceptors block an SSE request, return JSON error, not SSE stream."""
        config = SidecarConfig(
            interceptors=InterceptorsConfig(
                authentication=AuthenticationConfig(enabled=True, schemes=["api_key"], api_key="secret"),
            ),
        )
        app = create_app(config)

        with app.test_client() as client:
            data = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/sendSubscribe",
                "params": {},
            }
            # No API key provided — should be blocked
            resp = client.post("/a2a", json=data)
            assert resp.status_code in (401, 403, 500)
            response_data = resp.get_json()
            assert "error" in response_data
