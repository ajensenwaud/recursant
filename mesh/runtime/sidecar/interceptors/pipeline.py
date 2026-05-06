"""Interceptor pipeline — runs an ordered chain of interceptors."""

from __future__ import annotations

import structlog

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.telemetry import record_interceptor_decision, trace_span

logger = structlog.get_logger()


class PipelineResult:
    """Result of running the full interceptor pipeline."""

    def __init__(
        self,
        allowed: bool,
        decisions: list[InterceptorDecision],
        context: InterceptorContext,
    ):
        self.allowed = allowed
        self.decisions = decisions
        self.context = context

    @property
    def blocking_decision(self) -> InterceptorDecision | None:
        """Return the decision that blocked the message, if any."""
        for d in self.decisions:
            if d.action == InterceptorAction.BLOCK:
                return d
        return None


async def run_pipeline(
    interceptors: list[Interceptor],
    context: InterceptorContext,
) -> PipelineResult:
    """Run a message through an ordered chain of interceptors.

    Stops on the first BLOCK decision. For MODIFY decisions, the
    modified payload is applied to the context before continuing.

    Args:
        interceptors: Ordered list of interceptors to run.
        context: The interceptor context (will be mutated on MODIFY).

    Returns:
        PipelineResult with the outcome and all decisions.
    """
    decisions: list[InterceptorDecision] = []

    with trace_span("interceptor_pipeline", {
        "direction": context.direction.value,
        "a2a_method": context.a2a_method or "",
        "source_agent": context.source_agent_name or "",
        "dest_agent": context.dest_agent_name or "",
    }):
        for interceptor in interceptors:
            with trace_span(f"interceptor.{interceptor.name}"):
                decision = await interceptor.process(context)

            decisions.append(decision)
            record_interceptor_decision(interceptor.name, decision.action.value)

            logger.info(
                "interceptor_decision",
                interceptor=interceptor.name,
                action=decision.action.value,
                reason=decision.reason,
                direction=context.direction.value,
                a2a_method=context.a2a_method,
                source_agent=context.source_agent_name,
                dest_agent=context.dest_agent_name,
            )

            if decision.action == InterceptorAction.BLOCK:
                return PipelineResult(
                    allowed=False,
                    decisions=decisions,
                    context=context,
                )

            if decision.action == InterceptorAction.MODIFY and decision.modified_payload:
                context.payload = decision.modified_payload

    return PipelineResult(
        allowed=True,
        decisions=decisions,
        context=context,
    )
