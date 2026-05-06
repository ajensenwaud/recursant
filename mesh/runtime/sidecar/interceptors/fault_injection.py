"""Fault injection interceptor — delay + abort for chaos testing.

Simulates infrastructure-level failures before any application logic runs.
Supports configurable delay (fixed duration) and abort (HTTP status code),
each with a percentage-based probability and optional source/destination/direction filters.
"""

from __future__ import annotations

import asyncio
import random

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import FaultInjectionConfig
from runtime.sidecar.interceptors.base import Interceptor


class FaultInjectionInterceptor(Interceptor):
    """Injects delays and/or aborts for chaos testing."""

    def __init__(self, config: FaultInjectionConfig):
        self._config = config

    @property
    def name(self) -> str:
        return "fault_injection"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="fault injection disabled",
            )

        # Check filters
        if not self._matches_filters(context):
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="fault injection filters do not match",
            )

        # Apply delay first
        if self._config.delay.enabled and self._config.delay.percentage > 0:
            if random.random() * 100 < self._config.delay.percentage:
                delay_seconds = self._config.delay.fixed_delay_ms / 1000.0
                await asyncio.sleep(delay_seconds)

        # Then check abort
        if self._config.abort.enabled and self._config.abort.percentage > 0:
            if random.random() * 100 < self._config.abort.percentage:
                status = self._config.abort.http_status
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"fault injection: abort {status}",
                )

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="fault injection passed",
        )

    def _matches_filters(self, context: InterceptorContext) -> bool:
        """Check if the request matches configured filters."""
        if self._config.match_source:
            if context.source_agent_name != self._config.match_source:
                return False
        if self._config.match_destination:
            if context.dest_agent_name != self._config.match_destination:
                return False
        if self._config.match_direction:
            if context.direction and context.direction.value != self._config.match_direction:
                return False
        return True
