"""Post-processing guardrail interceptor.

Runs active post-processing guardrails against agent responses before
they are returned to the caller. Called from server.py after the agent
responds, not as part of the inbound pipeline.
"""

from __future__ import annotations

import structlog

from runtime.sidecar.guardrail_eval import GuardrailEvaluator, GuardrailResult

logger = structlog.get_logger()


class PostProcessingGuardrailInterceptor:
    """Evaluates post-processing guardrails on agent responses.

    Unlike pre-processing interceptors which participate in the pipeline,
    this runs as a standalone evaluator on the agent's response text.
    """

    def __init__(self, evaluator: GuardrailEvaluator, enabled: bool = True):
        self._evaluator = evaluator
        self._enabled = enabled
        self._guardrails: list[dict] = []

    def update_guardrails(self, guardrails: list[dict]) -> None:
        """Update cached guardrail configs from registry sync."""
        self._guardrails = sorted(
            [g for g in guardrails if g.get('type') == 'post_processing'],
            key=lambda g: g.get('priority', 100),
        )
        logger.info("post_guardrails_updated", count=len(self._guardrails))

    async def evaluate_response(self, response_text: str) -> PostGuardrailResult:
        """Evaluate response text against all active post-processing guardrails.

        Returns:
            PostGuardrailResult indicating whether to pass, block, or modify the response.
        """
        if not self._enabled or not self._guardrails:
            return PostGuardrailResult(action="pass", reasoning="no post-processing guardrails active")

        if not response_text:
            return PostGuardrailResult(action="pass", reasoning="no response text to evaluate")

        for guardrail in self._guardrails:
            result = await self._evaluator.evaluate(guardrail, response_text)

            logger.info(
                "post_guardrail_result",
                guardrail_id=result.guardrail_id,
                guardrail_name=result.guardrail_name,
                action=result.action,
                reasoning=result.reasoning,
                latency_ms=result.latency_ms,
            )

            if result.action == 'block':
                return PostGuardrailResult(
                    action="block",
                    reasoning=f"Guardrail '{result.guardrail_name}': {result.reasoning}",
                    guardrail_result=result,
                )
            elif result.action == 'warn':
                logger.warning(
                    "post_guardrail_warning",
                    guardrail_name=result.guardrail_name,
                    reasoning=result.reasoning,
                )
            elif result.action == 'redact':
                return PostGuardrailResult(
                    action="redact",
                    reasoning=f"Guardrail '{result.guardrail_name}': content redacted",
                    guardrail_result=result,
                    redacted_text="[Response redacted by guardrail policy]",
                )

        return PostGuardrailResult(action="pass", reasoning="all post-processing guardrails passed")


class PostGuardrailResult:
    """Result of post-processing guardrail evaluation."""

    def __init__(
        self,
        action: str,
        reasoning: str,
        guardrail_result: GuardrailResult | None = None,
        redacted_text: str | None = None,
        triggered_spans: list[dict] | None = None,
    ):
        self.action = action  # "pass", "block", "redact"
        self.reasoning = reasoning
        self.guardrail_result = guardrail_result
        self.redacted_text = redacted_text
        self.triggered_spans = triggered_spans or (
            guardrail_result.triggered_spans if guardrail_result else None
        )
