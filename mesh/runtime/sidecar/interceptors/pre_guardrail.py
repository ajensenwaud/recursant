"""Pre-processing guardrail interceptor.

Runs active pre-processing guardrails against inbound messages before
they reach the agent. Evaluates guardrails in priority order.
"""

from __future__ import annotations

import structlog

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.guardrail_eval import GuardrailEvaluator
from runtime.sidecar.interceptors.base import Interceptor

logger = structlog.get_logger()


class PreProcessingGuardrailInterceptor(Interceptor):
    """Evaluates pre-processing guardrails on inbound messages."""

    def __init__(self, evaluator: GuardrailEvaluator, enabled: bool = True):
        self._evaluator = evaluator
        self._enabled = enabled
        self._guardrails: list[dict] = []

    @property
    def name(self) -> str:
        return "pre_guardrail"

    def update_guardrails(self, guardrails: list[dict]) -> None:
        """Update cached guardrail configs from registry sync."""
        self._guardrails = sorted(
            [g for g in guardrails if g.get('type') == 'pre_processing'],
            key=lambda g: g.get('priority', 100),
        )
        logger.info("pre_guardrails_updated", count=len(self._guardrails))

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._enabled or not self._guardrails:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="no pre-processing guardrails active",
            )

        # Extract text from message payload
        text = _extract_message_text(context.payload)
        if not text:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="no message text to evaluate",
            )

        # Evaluate guardrails in priority order (already sorted)
        for guardrail in self._guardrails:
            result = await self._evaluator.evaluate(guardrail, text)

            logger.info(
                "pre_guardrail_result",
                guardrail_id=result.guardrail_id,
                guardrail_name=result.guardrail_name,
                action=result.action,
                reasoning=result.reasoning,
                latency_ms=result.latency_ms,
            )

            if result.action == 'block':
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"Guardrail '{result.guardrail_name}': {result.reasoning}",
                    details={'triggered_spans': result.triggered_spans} if result.triggered_spans else None,
                )
            elif result.action == 'warn':
                logger.warning(
                    "pre_guardrail_warning",
                    guardrail_name=result.guardrail_name,
                    reasoning=result.reasoning,
                )
            elif result.action == 'redact':
                # For pre-processing, redact = modify the payload
                modified = context.payload.copy()
                msg = modified.get('message', {})
                if isinstance(msg, dict) and 'parts' in msg:
                    parts = msg.get('parts', [])
                    for part in parts:
                        if isinstance(part, dict) and 'text' in part:
                            part['text'] = '[REDACTED by guardrail]'
                    modified['message'] = msg
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.MODIFY,
                    reason=f"Guardrail '{result.guardrail_name}': content redacted",
                    modified_payload=modified,
                    details={'triggered_spans': result.triggered_spans} if result.triggered_spans else None,
                )

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="all pre-processing guardrails passed",
        )


def _extract_message_text(payload: dict) -> str:
    """Extract text from an A2A message payload."""
    # A2A message/send params contain a 'message' with 'parts'
    message = payload.get('message', {})
    if isinstance(message, dict):
        parts = message.get('parts', [])
        texts = []
        for part in parts:
            if isinstance(part, dict) and 'text' in part:
                texts.append(part['text'])
            elif isinstance(part, str):
                texts.append(part)
        if texts:
            return ' '.join(texts)

    # Fallback: try to find text in payload directly
    if 'text' in payload:
        return payload['text']
    if 'content' in payload:
        return str(payload['content'])

    return ''
