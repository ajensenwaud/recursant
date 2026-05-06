"""Tests for RecursantA2AClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from runtime.client.a2a_client import (
    A2AResponse,
    AgentNotFoundError,
    AuthorisationDeniedError,
    RecursantA2AClient,
    RecursantClientError,
    SidecarTimeoutError,
    SidecarUnavailableError,
)


# ===========================================================================
# A2AResponse tests
# ===========================================================================


class TestA2AResponse:
    def test_defaults(self):
        resp = A2AResponse(status="completed")
        assert resp.status == "completed"
        assert resp.task_id is None
        assert resp.artifacts == []
        assert resp.raw == {}

    def test_with_artifacts(self):
        resp = A2AResponse(
            status="completed",
            task_id="task-1",
            artifacts=[{"kind": "text", "text": "hello"}],
        )
        assert resp.task_id == "task-1"
        assert len(resp.artifacts) == 1
        assert resp.artifacts[0]["text"] == "hello"


# ===========================================================================
# Client init tests
# ===========================================================================


class TestRecursantA2AClientInit:
    def test_default_sidecar_url(self):
        client = RecursantA2AClient()
        assert client.sidecar_url == "http://localhost:9901"

    def test_custom_sidecar_url(self):
        client = RecursantA2AClient(sidecar_url="http://sidecar:9901")
        assert client.sidecar_url == "http://sidecar:9901"

    def test_strips_trailing_slash(self):
        client = RecursantA2AClient(sidecar_url="http://localhost:9901/")
        assert client.sidecar_url == "http://localhost:9901"

    def test_custom_timeout(self):
        client = RecursantA2AClient(timeout=60.0)
        assert client._timeout == 60.0


# ===========================================================================
# Async send tests
# ===========================================================================


class TestAsyncSendTask:
    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_sends_to_sidecar(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "status": "completed",
                "id": "task-abc",
                "artifacts": [{"kind": "text", "text": "Yes, the Eiffel Tower is 330m tall."}],
            },
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient(sidecar_url="http://localhost:9901")
        resp = await client.async_send_task(
            skill="fact-check",
            message="Is the Eiffel Tower 330m tall?",
        )

        assert resp.status == "completed"
        assert resp.task_id == "task-abc"
        assert len(resp.artifacts) == 1
        assert "330m" in resp.artifacts[0]["text"]

        # Verify URL and payload
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:9901/a2a/send"
        payload = call_args[1]["json"]
        assert payload["skill"] == "fact-check"
        assert payload["message"] == "Is the Eiffel Tower 330m tall?"

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_sends_destination_url_when_provided(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": "1", "result": {}}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        await client.async_send_task(
            skill="fact-check",
            message="test",
            destination_url="https://host-b:8444",
        )

        payload = mock_client.post.call_args[1]["json"]
        assert payload["destination_url"] == "https://host-b:8444"

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_custom_timeout_override(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": "1", "result": {}}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient(timeout=10.0)
        await client.async_send_task(skill="s", message="m", timeout=60.0)

        # AsyncClient was created with timeout=60.0
        assert mock_client_cls.call_args[1]["timeout"] == 60.0

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_authorisation_denied_on_403(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "error": "policy denies agent-a -> agent-b",
            "blocked": True,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(AuthorisationDeniedError, match="policy denies"):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_authorisation_denied_on_blocked_flag(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200  # Some implementations return 200 with blocked
        mock_response.json.return_value = {
            "error": "source agent identity unknown",
            "blocked": True,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(AuthorisationDeniedError):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_agent_not_found_on_502(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32003, "message": "Remote sidecar unreachable"},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(AgentNotFoundError, match="unreachable"):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    async def test_sidecar_unavailable_on_connect_error(self):
        client = RecursantA2AClient(sidecar_url="http://localhost:59999")

        with pytest.raises(SidecarUnavailableError, match="Cannot connect"):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_sidecar_timeout(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(SidecarTimeoutError, match="timed out"):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_generic_error_on_400(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "skill and message are required"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(RecursantClientError, match="400"):
            await client.async_send_task(skill="s", message="m")

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_result_with_empty_result(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        resp = await client.async_send_task(skill="s", message="m")

        assert resp.status == "completed"
        assert resp.artifacts == []

    @pytest.mark.asyncio
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    async def test_raw_response_preserved(self, mock_client_cls):
        raw = {"jsonrpc": "2.0", "id": "req-1", "result": {"status": "completed"}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = raw

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        resp = await client.async_send_task(skill="s", message="m")

        assert resp.raw == raw


# ===========================================================================
# Sync send tests
# ===========================================================================


class TestSyncSendTask:
    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    def test_sync_send_works(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"status": "completed", "artifacts": []},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        resp = client.send_task(skill="fact-check", message="test")

        assert resp.status == "completed"

    @patch("runtime.client.a2a_client.httpx.AsyncClient")
    def test_sync_send_raises_on_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "blocked", "blocked": True}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = RecursantA2AClient()
        with pytest.raises(AuthorisationDeniedError):
            client.send_task(skill="s", message="m")


# ===========================================================================
# Import tests
# ===========================================================================


class TestImports:
    def test_import_from_package(self):
        from runtime.client import RecursantA2AClient as Client
        assert Client is not None

    def test_import_exceptions(self):
        from runtime.client import (
            AuthorisationDeniedError,
            AgentNotFoundError,
            SidecarTimeoutError,
            SidecarUnavailableError,
        )
        assert all([
            AuthorisationDeniedError,
            AgentNotFoundError,
            SidecarTimeoutError,
            SidecarUnavailableError,
        ])

    def test_exception_hierarchy(self):
        assert issubclass(AuthorisationDeniedError, RecursantClientError)
        assert issubclass(AgentNotFoundError, RecursantClientError)
        assert issubclass(SidecarTimeoutError, RecursantClientError)
        assert issubclass(SidecarUnavailableError, RecursantClientError)
