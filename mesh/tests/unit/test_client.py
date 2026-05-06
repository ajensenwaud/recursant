"""Tests for the A2A outbound client and /a2a/send endpoint."""

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from runtime.sidecar.app import create_app
from runtime.sidecar.client import OutboundClient, handle_outbound_request
from runtime.sidecar.config import SidecarConfig
from runtime.sidecar.server import JSONRPCError, make_error_response, make_success_response

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ===========================================================================
# OutboundClient unit tests
# ===========================================================================


class TestOutboundClient:
    def test_default_timeout(self):
        client = OutboundClient()
        assert client._timeout == 30.0

    def test_custom_timeout(self):
        client = OutboundClient(timeout=10.0)
        assert client._timeout == 10.0

    def test_no_ssl_context_without_certs(self):
        client = OutboundClient()
        ctx = client._build_ssl_context()
        assert ctx is None

    @pytest.mark.asyncio
    @patch("runtime.sidecar.client.httpx.AsyncClient")
    async def test_send_a2a_request_constructs_jsonrpc(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = make_success_response("req-1", {"status": "completed"})
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = OutboundClient()
        result = await client.send_a2a_request(
            destination_url="https://host-b:8444",
            method="message/send",
            params={"message": {"role": "user", "parts": []}},
            request_id="req-1",
        )

        # Verify the call
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://host-b:8444/a2a"
        sent_json = call_args[1]["json"]
        assert sent_json["jsonrpc"] == "2.0"
        assert sent_json["id"] == "req-1"
        assert sent_json["method"] == "message/send"
        assert result["result"]["status"] == "completed"

    @pytest.mark.asyncio
    @patch("runtime.sidecar.client.httpx.AsyncClient")
    async def test_send_generates_request_id_if_not_provided(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": "auto", "result": {}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = OutboundClient()
        await client.send_a2a_request(
            destination_url="https://host-b:8444",
            method="message/send",
            params={},
        )

        sent_json = mock_client.post.call_args[1]["json"]
        # Should have a UUID string as request ID
        assert sent_json["id"] is not None
        uuid.UUID(sent_json["id"])  # Should not raise

    @pytest.mark.asyncio
    @patch("runtime.sidecar.client.httpx.AsyncClient")
    async def test_send_raises_on_connect_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = OutboundClient()
        with pytest.raises(httpx.ConnectError):
            await client.send_a2a_request(
                destination_url="https://host-b:8444",
                method="message/send",
                params={},
            )

    @pytest.mark.asyncio
    @patch("runtime.sidecar.client.httpx.AsyncClient")
    async def test_send_raises_on_timeout(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = OutboundClient()
        with pytest.raises(httpx.TimeoutException):
            await client.send_a2a_request(
                destination_url="https://host-b:8444",
                method="message/send",
                params={},
            )


# ===========================================================================
# handle_outbound_request tests
# ===========================================================================


class TestHandleOutboundRequest:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_destination(self):
        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[],
            source_agent_name="agent-a",
        )
        assert "error" in result
        assert "No destination sidecar URL" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_uses_resolve_destination(self):
        mock_resolve = AsyncMock(return_value=("https://host-b:8444", "fact-checker"))
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.return_value = make_success_response("req-1", {"ok": True})

        result = await handle_outbound_request(
            skill="fact-check",
            message="test claim",
            interceptors=[],
            source_agent_name="agent-a",
            outbound_client=mock_client,
            resolve_destination=mock_resolve,
        )

        mock_resolve.assert_called_once_with("fact-check")
        mock_client.send_a2a_request.assert_called_once()
        assert result["result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_returns_error_on_discovery_failure(self):
        mock_resolve = AsyncMock(side_effect=Exception("registry down"))

        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[],
            source_agent_name="agent-a",
            resolve_destination=mock_resolve,
        )

        assert "error" in result
        assert "registry down" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_direct_destination_url_skips_discovery(self):
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.return_value = make_success_response("req-1", {})

        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
        )

        assert "error" not in result
        call_args = mock_client.send_a2a_request.call_args
        assert call_args[1]["destination_url"] == "https://host-b:8444"

    @pytest.mark.asyncio
    async def test_blocked_by_interceptor(self):
        from runtime.sidecar.config import AuthorisationConfig
        from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor

        authz_config = AuthorisationConfig(
            enabled=True,
            default_action="deny",
        )
        authz = AuthorisationInterceptor(authz_config)

        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[authz],
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
            dest_sidecar_url="https://host-b:8444",
        )

        assert result.get("blocked") is True
        assert "error" in result

    @pytest.mark.asyncio
    async def test_constructs_a2a_message(self):
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.return_value = make_success_response("req-1", {})

        await handle_outbound_request(
            skill="fact-check",
            message="Is the sky blue?",
            interceptors=[],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
        )

        call_args = mock_client.send_a2a_request.call_args
        assert call_args[1]["method"] == "message/send"
        params = call_args[1]["params"]
        assert params["message"]["parts"][0]["text"] == "Is the sky blue?"
        assert params["message"]["role"] == "user"

    @pytest.mark.asyncio
    async def test_connect_error_returns_agent_unavailable(self):
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.side_effect = httpx.ConnectError("refused")

        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
        )

        assert result["error"]["code"] == JSONRPCError.AGENT_UNAVAILABLE
        assert "unreachable" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_timeout_returns_agent_unavailable(self):
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.side_effect = httpx.TimeoutException("timed out")

        result = await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
        )

        assert result["error"]["code"] == JSONRPCError.AGENT_UNAVAILABLE
        assert "timed out" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_audit_record_on_success(self):
        from runtime.sidecar.config import AuditConfig
        from runtime.sidecar.interceptors.audit import AuditInterceptor

        audit = AuditInterceptor(AuditConfig(enabled=True))
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.return_value = make_success_response("req-1", {})

        await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[audit],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
            audit_interceptor=audit,
        )

        # Should have records from pipeline run + final result
        assert len(audit.all_records) >= 1

    @pytest.mark.asyncio
    async def test_audit_record_on_blocked(self):
        from runtime.sidecar.config import AuditConfig, AuthorisationConfig
        from runtime.sidecar.interceptors.audit import AuditInterceptor
        from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor

        audit = AuditInterceptor(AuditConfig(enabled=True))
        authz = AuthorisationInterceptor(AuthorisationConfig(enabled=True, default_action="deny"))

        await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[authz, audit],
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
            dest_sidecar_url="https://host-b:8444",
            audit_interceptor=audit,
        )

        blocked_records = [r for r in audit.all_records if r.outcome == "blocked"]
        assert len(blocked_records) >= 1

    @pytest.mark.asyncio
    async def test_audit_record_on_error(self):
        from runtime.sidecar.config import AuditConfig
        from runtime.sidecar.interceptors.audit import AuditInterceptor

        audit = AuditInterceptor(AuditConfig(enabled=True))
        mock_client = AsyncMock(spec=OutboundClient)
        mock_client.send_a2a_request.side_effect = httpx.ConnectError("refused")

        await handle_outbound_request(
            skill="fact-check",
            message="test",
            interceptors=[audit],
            source_agent_name="agent-a",
            dest_sidecar_url="https://host-b:8444",
            outbound_client=mock_client,
            audit_interceptor=audit,
        )

        error_records = [r for r in audit.all_records if r.outcome == "error"]
        assert len(error_records) >= 1


# ===========================================================================
# Flask /a2a/send endpoint tests
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


class TestA2ASendEndpoint:
    def test_invalid_json_returns_400(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a/send",
            data="not json",
            content_type="application/json",
        )

        assert resp.status_code == 400

    def test_missing_skill_returns_400(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post("/a2a/send", json={"message": "hello"})

        assert resp.status_code == 400
        assert "skill" in resp.get_json()["error"]

    def test_missing_message_returns_400(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post("/a2a/send", json={"skill": "fact-check"})

        assert resp.status_code == 400
        assert "message" in resp.get_json()["error"]

    def test_no_destination_returns_error(self):
        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a/send",
            json={"skill": "fact-check", "message": "hello"},
        )

        # No destination URL or resolver configured
        assert resp.status_code == 502

    @patch("runtime.sidecar.client.OutboundClient.send_a2a_request", new_callable=AsyncMock)
    def test_sends_to_direct_destination(self, mock_send):
        mock_send.return_value = make_success_response("req-1", {"status": "completed"})

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a/send",
            json={
                "skill": "fact-check",
                "message": "Is the sky blue?",
                "destination_url": "https://host-b:8444",
            },
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "completed"
        mock_send.assert_called_once()

    @patch("runtime.sidecar.client.OutboundClient.send_a2a_request", new_callable=AsyncMock)
    def test_destination_connect_error(self, mock_send):
        mock_send.side_effect = httpx.ConnectError("refused")

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a/send",
            json={
                "skill": "fact-check",
                "message": "test",
                "destination_url": "https://host-b:8444",
            },
        )

        assert resp.status_code == 502

    @patch("runtime.sidecar.client.OutboundClient.send_a2a_request", new_callable=AsyncMock)
    def test_destination_timeout(self, mock_send):
        mock_send.side_effect = httpx.TimeoutException("timed out")

        app = create_app(_make_test_config())
        client = app.test_client()

        resp = client.post(
            "/a2a/send",
            json={
                "skill": "fact-check",
                "message": "test",
                "destination_url": "https://host-b:8444",
            },
        )

        assert resp.status_code == 502

    @patch("runtime.sidecar.client.OutboundClient.send_a2a_request", new_callable=AsyncMock)
    def test_audit_record_created(self, mock_send):
        mock_send.return_value = make_success_response("req-1", {})

        app = create_app(_make_test_config())
        client = app.test_client()

        client.post(
            "/a2a/send",
            json={
                "skill": "fact-check",
                "message": "test",
                "destination_url": "https://host-b:8444",
            },
        )

        audit = app.config["AUDIT_INTERCEPTOR"]
        assert len(audit.all_records) >= 1
