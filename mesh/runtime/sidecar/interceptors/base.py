"""Base interceptor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.common.models import InterceptorContext, InterceptorDecision


class Interceptor(ABC):
    """Base class for all interceptors in the sidecar pipeline.

    Each interceptor inspects an A2A message and returns a decision:
    - pass: message continues to the next interceptor
    - block: message is rejected, pipeline stops
    - modify: message payload is changed, continues to next interceptor
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this interceptor (used in logs and audit records)."""

    @abstractmethod
    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        """Process an A2A message through this interceptor.

        Args:
            context: The interceptor context with message details.

        Returns:
            Decision to pass, block, or modify the message.
        """
