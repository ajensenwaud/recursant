"""Rate limiting interceptor — token bucket per source agent.

Enforces per-source-agent rate limits using an in-memory token bucket
algorithm. Outbound requests are not rate-limited (we trust our own agent).
"""

from __future__ import annotations

import threading
import time

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import RateLimitingConfig
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.telemetry import record_rate_limit_rejected


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    __slots__ = ("rate", "capacity", "tokens", "last_refill", "_lock")

    def __init__(self, rate: float, capacity: float):
        self.rate = rate  # tokens per second
        self.capacity = capacity  # max burst
        self.tokens = capacity  # start full
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, n: float = 1.0) -> bool:
        """Try to consume n tokens. Returns True if allowed."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


class RateLimitingInterceptor(Interceptor):
    """Enforces per-source-agent rate limits using token buckets."""

    def __init__(self, config: RateLimitingConfig):
        self._config = config
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "rate_limiting"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="rate limiting disabled",
            )

        # Skip outbound — we trust our own agent
        if context.direction and context.direction.value == "outbound":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="outbound — not rate limited",
            )

        source = context.source_agent_name or "unknown"
        bucket = self._get_or_create_bucket(source)

        if not bucket.consume():
            record_rate_limit_rejected(source)
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=f"rate limit exceeded for source '{source}'",
            )

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="within rate limit",
        )

    def _get_or_create_bucket(self, source: str) -> TokenBucket:
        with self._lock:
            if source not in self._buckets:
                rpm = self._config.default_requests_per_minute
                # Check per-agent overrides
                override = self._config.per_agent_overrides.get(source)
                if override and "requests_per_minute" in override:
                    rpm = override["requests_per_minute"]

                rate = rpm / 60.0  # tokens per second
                capacity = rate * self._config.burst_multiplier * 60.0 / rpm * rpm / 60.0
                # Simplified: capacity = burst_multiplier * rate (burst in tokens)
                capacity = rate * self._config.burst_multiplier
                self._buckets[source] = TokenBucket(rate=rate, capacity=capacity)
            return self._buckets[source]
