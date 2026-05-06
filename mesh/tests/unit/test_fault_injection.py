"""Tests for the fault injection interceptor."""

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
)
from runtime.sidecar.config import (
    AbortFaultConfig,
    DelayFaultConfig,
    FaultInjectionConfig,
)
from runtime.sidecar.interceptors.fault_injection import FaultInjectionInterceptor


def _make_context(**overrides) -> InterceptorContext:
    defaults = dict(
        direction=Direction.INBOUND,
        a2a_method="message/send",
        payload={"message": "hello"},
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


class TestFaultInjectionInterceptor:
    def test_disabled_passes(self):
        config = FaultInjectionConfig(enabled=False)
        interceptor = FaultInjectionInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "disabled" in decision.reason

    def test_abort_100_percent_blocks(self):
        config = FaultInjectionConfig(
            enabled=True,
            abort=AbortFaultConfig(enabled=True, http_status=503, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "abort 503" in decision.reason

    def test_abort_0_percent_never_triggers(self):
        config = FaultInjectionConfig(
            enabled=True,
            abort=AbortFaultConfig(enabled=True, http_status=503, percentage=0.0),
        )
        interceptor = FaultInjectionInterceptor(config)
        ctx = _make_context()

        # Run many times — should never block
        for _ in range(100):
            decision = asyncio.get_event_loop().run_until_complete(
                interceptor.process(ctx)
            )
            assert decision.action == InterceptorAction.PASS

    @patch("runtime.sidecar.interceptors.fault_injection.asyncio.sleep", new_callable=AsyncMock)
    def test_delay_adds_latency(self, mock_sleep):
        config = FaultInjectionConfig(
            enabled=True,
            delay=DelayFaultConfig(enabled=True, fixed_delay_ms=500, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        mock_sleep.assert_called_once_with(0.5)

    @patch("runtime.sidecar.interceptors.fault_injection.asyncio.sleep", new_callable=AsyncMock)
    def test_delay_and_abort_both_trigger(self, mock_sleep):
        config = FaultInjectionConfig(
            enabled=True,
            delay=DelayFaultConfig(enabled=True, fixed_delay_ms=100, percentage=100.0),
            abort=AbortFaultConfig(enabled=True, http_status=500, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        # Delay should run first, then abort blocks
        mock_sleep.assert_called_once_with(0.1)
        assert decision.action == InterceptorAction.BLOCK
        assert "abort 500" in decision.reason

    def test_source_filter_matches(self):
        config = FaultInjectionConfig(
            enabled=True,
            match_source="agent-a",
            abort=AbortFaultConfig(enabled=True, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)

        # Matching source — should abort
        ctx = _make_context(source_agent_name="agent-a")
        d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert d.action == InterceptorAction.BLOCK

    def test_source_filter_no_match_passes(self):
        config = FaultInjectionConfig(
            enabled=True,
            match_source="agent-a",
            abort=AbortFaultConfig(enabled=True, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)

        # Non-matching source — should pass
        ctx = _make_context(source_agent_name="agent-b")
        d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert d.action == InterceptorAction.PASS
        assert "filters do not match" in d.reason

    def test_destination_filter(self):
        config = FaultInjectionConfig(
            enabled=True,
            match_destination="agent-b",
            abort=AbortFaultConfig(enabled=True, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)

        ctx = _make_context(dest_agent_name="agent-b")
        d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert d.action == InterceptorAction.BLOCK

        ctx2 = _make_context(dest_agent_name="agent-c")
        d2 = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx2))
        assert d2.action == InterceptorAction.PASS

    def test_direction_filter(self):
        config = FaultInjectionConfig(
            enabled=True,
            match_direction="outbound",
            abort=AbortFaultConfig(enabled=True, percentage=100.0),
        )
        interceptor = FaultInjectionInterceptor(config)

        # Inbound — no match
        ctx = _make_context(direction=Direction.INBOUND)
        d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert d.action == InterceptorAction.PASS

        # Outbound — matches
        ctx2 = _make_context(direction=Direction.OUTBOUND)
        d2 = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx2))
        assert d2.action == InterceptorAction.BLOCK
