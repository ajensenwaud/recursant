"""Tests for failover routing in outbound requests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.client import OutboundClient, handle_outbound_request
from runtime.sidecar.config import AuthorisationConfig
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.resilience import CircuitOpenError


class _PassInterceptor(Interceptor):
    @property
    def name(self) -> str:
        return "pass"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="pass",
        )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFailoverRouting:
    def test_primary_succeeds_only_one_call(self):
        """When primary succeeds, no failover attempts."""
        client = OutboundClient()
        client.send_a2a_request = AsyncMock(return_value={"jsonrpc": "2.0", "result": {"status": "ok"}})

        async def resolve_destinations(skill):
            return [
                ("http://primary:8443", "agent-primary"),
                ("http://secondary:8443", "agent-secondary"),
            ]

        result = _run(handle_outbound_request(
            skill="test-skill",
            message="hello",
            interceptors=[_PassInterceptor()],
            source_agent_name="agent-a",
            outbound_client=client,
            resolve_destinations=resolve_destinations,
        ))

        assert "error" not in result
        assert client.send_a2a_request.call_count == 1
        call_url = client.send_a2a_request.call_args[1]["destination_url"]
        assert call_url == "http://primary:8443"

    def test_primary_fails_secondary_succeeds(self):
        """When primary fails, try secondary."""
        client = OutboundClient()

        call_count = 0

        async def mock_send(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs["destination_url"] == "http://primary:8443":
                raise httpx.ConnectError("refused")
            return {"jsonrpc": "2.0", "result": {"status": "ok"}}

        client.send_a2a_request = mock_send

        async def resolve_destinations(skill):
            return [
                ("http://primary:8443", "agent-primary"),
                ("http://secondary:8443", "agent-secondary"),
            ]

        result = _run(handle_outbound_request(
            skill="test-skill",
            message="hello",
            interceptors=[_PassInterceptor()],
            source_agent_name="agent-a",
            outbound_client=client,
            resolve_destinations=resolve_destinations,
        ))

        assert "error" not in result
        assert call_count == 2

    def test_all_destinations_exhausted(self):
        """When all destinations fail, return error."""
        client = OutboundClient()

        async def mock_send(**kwargs):
            raise httpx.ConnectError("refused")

        client.send_a2a_request = mock_send

        async def resolve_destinations(skill):
            return [
                ("http://primary:8443", "agent-primary"),
                ("http://secondary:8443", "agent-secondary"),
            ]

        result = _run(handle_outbound_request(
            skill="test-skill",
            message="hello",
            interceptors=[_PassInterceptor()],
            source_agent_name="agent-a",
            outbound_client=client,
            resolve_destinations=resolve_destinations,
        ))

        assert "error" in result
        assert "exhausted" in result["error"]["message"]

    def test_circuit_open_primary_skipped(self):
        """When primary circuit is open, skip to secondary."""
        client = OutboundClient()

        async def mock_send(**kwargs):
            if kwargs["destination_url"] == "http://primary:8443":
                raise CircuitOpenError("http://primary:8443", 30.0)
            return {"jsonrpc": "2.0", "result": {"status": "ok"}}

        client.send_a2a_request = mock_send

        async def resolve_destinations(skill):
            return [
                ("http://primary:8443", "agent-primary"),
                ("http://secondary:8443", "agent-secondary"),
            ]

        result = _run(handle_outbound_request(
            skill="test-skill",
            message="hello",
            interceptors=[_PassInterceptor()],
            source_agent_name="agent-a",
            outbound_client=client,
            resolve_destinations=resolve_destinations,
        ))

        assert "error" not in result

    def test_single_destination_no_failover(self):
        """With a single destination (direct URL), no failover."""
        client = OutboundClient()

        async def mock_send(**kwargs):
            raise httpx.ConnectError("refused")

        client.send_a2a_request = mock_send

        result = _run(handle_outbound_request(
            skill="test-skill",
            message="hello",
            interceptors=[_PassInterceptor()],
            source_agent_name="agent-a",
            dest_sidecar_url="http://direct:8443",
            outbound_client=client,
        ))

        assert "error" in result
