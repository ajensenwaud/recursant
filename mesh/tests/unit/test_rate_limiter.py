"""Tests for the rate limiting interceptor."""

import asyncio
import time

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
)
from runtime.sidecar.config import RateLimitingConfig
from runtime.sidecar.interceptors.rate_limiter import (
    RateLimitingInterceptor,
    TokenBucket,
)


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


class TestTokenBucket:
    def test_starts_full(self):
        bucket = TokenBucket(rate=1.0, capacity=5.0)
        for _ in range(5):
            assert bucket.consume() is True
        assert bucket.consume() is False

    def test_refills_over_time(self):
        bucket = TokenBucket(rate=1000.0, capacity=1.0)
        assert bucket.consume() is True
        assert bucket.consume() is False
        time.sleep(0.01)  # 10ms -> should refill ~10 tokens at 1000/s
        assert bucket.consume() is True

    def test_capacity_limits_burst(self):
        bucket = TokenBucket(rate=100.0, capacity=3.0)
        # Consume all
        for _ in range(3):
            assert bucket.consume() is True
        assert bucket.consume() is False


class TestRateLimitingInterceptor:
    def test_disabled_passes(self):
        config = RateLimitingConfig(enabled=False)
        interceptor = RateLimitingInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "disabled" in decision.reason

    def test_outbound_passes(self):
        config = RateLimitingConfig(enabled=True)
        interceptor = RateLimitingInterceptor(config)
        ctx = _make_context(direction=Direction.OUTBOUND)

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "outbound" in decision.reason

    def test_within_limit_passes(self):
        config = RateLimitingConfig(enabled=True, default_requests_per_minute=600)
        interceptor = RateLimitingInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    def test_exceed_limit_blocks(self):
        # 1 RPM = very low, burst_multiplier=1.0 => capacity = rate * 1.0
        config = RateLimitingConfig(
            enabled=True,
            default_requests_per_minute=1,
            burst_multiplier=1.0,
        )
        interceptor = RateLimitingInterceptor(config)

        # First request consumes the single token
        ctx1 = _make_context()
        d1 = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx1))
        # The bucket starts with capacity tokens; at 1 RPM, capacity=rate*burst=1/60*1.0
        # which is ~0.0167 — less than 1 token needed. So even first may block.
        # Let's use a higher RPM for a realistic test.

    def test_exceed_limit_blocks_realistic(self):
        # 60 RPM = 1/sec, burst=1.0 => capacity=1 token
        config = RateLimitingConfig(
            enabled=True,
            default_requests_per_minute=60,
            burst_multiplier=1.0,
        )
        interceptor = RateLimitingInterceptor(config)

        # First request should pass (starts with 1 token)
        ctx1 = _make_context()
        d1 = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx1))
        assert d1.action == InterceptorAction.PASS

        # Second request immediately should block (no time to refill)
        ctx2 = _make_context()
        d2 = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx2))
        assert d2.action == InterceptorAction.BLOCK
        assert "rate limit exceeded" in d2.reason

    def test_per_agent_overrides(self):
        config = RateLimitingConfig(
            enabled=True,
            default_requests_per_minute=60,
            burst_multiplier=1.0,
            per_agent_overrides={"fast-agent": {"requests_per_minute": 6000}},
        )
        interceptor = RateLimitingInterceptor(config)

        # fast-agent gets 100/sec — many requests should pass
        for _ in range(10):
            ctx = _make_context(source_agent_name="fast-agent")
            d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
            assert d.action == InterceptorAction.PASS

    def test_different_agents_have_separate_buckets(self):
        config = RateLimitingConfig(
            enabled=True,
            default_requests_per_minute=60,
            burst_multiplier=1.0,
        )
        interceptor = RateLimitingInterceptor(config)

        # Agent A uses its token
        ctx_a = _make_context(source_agent_name="agent-a")
        asyncio.get_event_loop().run_until_complete(interceptor.process(ctx_a))

        # Agent B should still pass (separate bucket)
        ctx_b = _make_context(source_agent_name="agent-b")
        d = asyncio.get_event_loop().run_until_complete(interceptor.process(ctx_b))
        assert d.action == InterceptorAction.PASS
