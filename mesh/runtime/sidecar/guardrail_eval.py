"""Guardrail evaluator — dispatches evaluation based on mechanism type.

Supports regex, vector_lookup, llm_judge, and ml_classifier mechanisms.
Each evaluation returns a GuardrailResult with action, reasoning, and latency.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class GuardrailResult:
    """Result of evaluating a single guardrail against text."""

    guardrail_id: str
    guardrail_name: str
    action: str  # "pass", "block", "warn", "redact"
    reasoning: str
    latency_ms: int = 0
    matched_references: list[dict] | None = None
    triggered_spans: list[dict] | None = None


class GuardrailEvaluator:
    """Dispatches guardrail evaluation to the appropriate mechanism handler."""

    def __init__(
        self,
        llm_client=None,
        weaviate_client=None,
    ):
        self._llm_client = llm_client
        self._weaviate_client = weaviate_client
        self._consecutive_errors: dict[str, int] = {}
        self._max_consecutive_errors = 5
        # Event buffer for observability pipeline
        self._event_buffer: deque[dict] = deque(maxlen=5000)

    async def evaluate(
        self, guardrail_config: dict, text: str,
    ) -> GuardrailResult:
        """Evaluate a guardrail against the given text.

        Args:
            guardrail_config: Full guardrail config from registry
                (id, name, type, mechanism, config, enforcement_mode, priority).
            text: The text to evaluate (user message or agent response).

        Returns:
            GuardrailResult with the action to take.
        """
        guardrail_id = str(guardrail_config.get('id', ''))
        guardrail_name = guardrail_config.get('name', 'unknown')
        mechanism = guardrail_config.get('mechanism', '')
        enforcement_mode = guardrail_config.get('enforcement_mode', 'block')
        config = guardrail_config.get('config', {})

        # Check auto-disable
        if self._consecutive_errors.get(guardrail_id, 0) >= self._max_consecutive_errors:
            logger.warning(
                "guardrail_auto_disabled",
                guardrail_id=guardrail_id,
                name=guardrail_name,
            )
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action="pass",
                reasoning="Auto-disabled after consecutive errors",
            )

        start = time.monotonic()
        try:
            if mechanism == 'regex':
                result = await self._eval_regex(
                    guardrail_id, guardrail_name, config, text, enforcement_mode,
                )
            elif mechanism == 'vector_lookup':
                result = await self._eval_vector_lookup(
                    guardrail_id, guardrail_name, config, text, enforcement_mode,
                )
            elif mechanism == 'llm_judge':
                result = await self._eval_llm_judge(
                    guardrail_id, guardrail_name, config, text, enforcement_mode,
                )
            elif mechanism == 'ml_classifier':
                result = await self._eval_ml_classifier(
                    guardrail_id, guardrail_name, config, text, enforcement_mode,
                )
            else:
                result = GuardrailResult(
                    guardrail_id=guardrail_id,
                    guardrail_name=guardrail_name,
                    action="pass",
                    reasoning=f"Unknown mechanism: {mechanism}",
                )

            # Clear consecutive errors on success
            self._consecutive_errors.pop(guardrail_id, None)
            result.latency_ms = int((time.monotonic() - start) * 1000)
            self._emit_event(guardrail_config, result)
            return result

        except Exception as e:
            count = self._consecutive_errors.get(guardrail_id, 0) + 1
            self._consecutive_errors[guardrail_id] = count
            logger.warning(
                "guardrail_evaluation_error",
                guardrail_id=guardrail_id,
                name=guardrail_name,
                error=str(e),
                consecutive_errors=count,
            )
            latency = int((time.monotonic() - start) * 1000)
            error_result = GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action="pass",
                reasoning=f"Evaluation error: {e}",
                latency_ms=latency,
            )
            self._emit_event(guardrail_config, error_result, is_error=True, error_message=str(e))
            return error_result

    def _emit_event(
        self,
        guardrail_config: dict,
        result: GuardrailResult,
        is_error: bool = False,
        error_message: str | None = None,
    ) -> None:
        """Buffer a guardrail evaluation event for the observability pipeline."""
        event = {
            "guardrail_id": str(guardrail_config.get("id", "")),
            "guardrail_name": guardrail_config.get("name", "unknown"),
            "guardrail_type": guardrail_config.get("type", ""),
            "mechanism": guardrail_config.get("mechanism", ""),
            "action": result.action,
            "reasoning": result.reasoning[:500] if result.reasoning else "",
            "latency_ms": result.latency_ms,
            "matched_pattern": (
                result.matched_references[0].get("text", "")[:200]
                if result.matched_references
                else result.reasoning[:200] if result.action != "pass" else ""
            ),
            "input_hash": "",  # Populated by caller if needed
            "is_error": is_error,
            "error_message": error_message or "",
            "metric_id": str(guardrail_config.get("metric_id", "")) or None,
            "triggered_spans": result.triggered_spans,
        }
        self._event_buffer.append(event)

    def drain_events(self) -> list[dict]:
        """Remove and return all pending guardrail events."""
        events = list(self._event_buffer)
        self._event_buffer.clear()
        return events

    async def _eval_regex(
        self,
        guardrail_id: str,
        guardrail_name: str,
        config: dict,
        text: str,
        enforcement_mode: str,
    ) -> GuardrailResult:
        """Evaluate regex patterns against text."""
        patterns = config.get('patterns', [])
        for p in patterns:
            pattern_str = p.get('pattern', '')
            try:
                match = re.search(pattern_str, text, re.IGNORECASE)
                if match:
                    action = p.get('action', enforcement_mode)
                    spans = [{
                        'start': match.start(),
                        'end': match.end(),
                        'text': match.group(),
                        'reason': f"Matched pattern: {p.get('name', pattern_str)}",
                        'confidence': 1.0,
                    }]
                    # Collect additional matches
                    for m in re.finditer(pattern_str, text[match.end():], re.IGNORECASE):
                        spans.append({
                            'start': match.end() + m.start(),
                            'end': match.end() + m.end(),
                            'text': m.group(),
                            'reason': f"Matched pattern: {p.get('name', pattern_str)}",
                            'confidence': 1.0,
                        })
                    return GuardrailResult(
                        guardrail_id=guardrail_id,
                        guardrail_name=guardrail_name,
                        action=action,
                        reasoning=f"Matched pattern: {p.get('name', pattern_str)}",
                        triggered_spans=spans,
                    )
            except re.error as e:
                logger.warning("invalid_regex", pattern=pattern_str, error=str(e))
                continue

        return GuardrailResult(
            guardrail_id=guardrail_id,
            guardrail_name=guardrail_name,
            action="pass",
            reasoning="No patterns matched",
        )

    async def _eval_vector_lookup(
        self,
        guardrail_id: str,
        guardrail_name: str,
        config: dict,
        text: str,
        enforcement_mode: str,
    ) -> GuardrailResult:
        """Evaluate via Weaviate similarity search."""
        if self._weaviate_client is None:
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action="pass",
                reasoning="Weaviate client not configured",
            )

        collection_name = config.get('collection_name', 'GuardrailReference')
        threshold = config.get('similarity_threshold', 0.7)

        matches = await self._weaviate_client.query_near_text(
            collection=collection_name,
            text=text,
            guardrail_id=guardrail_id,
            limit=5,
            threshold=threshold,
        )

        if matches:
            best = matches[0]
            action = best.get('action', enforcement_mode)
            spans = [{
                'start': 0,
                'end': len(text),
                'text': text[:200],
                'reason': f"Similar to reference: \"{best['text'][:100]}\" (similarity: {best['similarity']})",
                'confidence': float(best.get('similarity', 0.0)),
            }]
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action=action,
                reasoning=f"Similar to: \"{best['text']}\" (similarity: {best['similarity']})",
                matched_references=matches,
                triggered_spans=spans,
            )

        return GuardrailResult(
            guardrail_id=guardrail_id,
            guardrail_name=guardrail_name,
            action="pass",
            reasoning="No similar references found",
        )

    async def _eval_llm_judge(
        self,
        guardrail_id: str,
        guardrail_name: str,
        config: dict,
        text: str,
        enforcement_mode: str,
    ) -> GuardrailResult:
        """Evaluate using LLM-as-judge."""
        if self._llm_client is None:
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action="pass",
                reasoning="LLM client not configured",
            )

        system_prompt = config.get('system_prompt', '')
        provider = config.get('provider', 'anthropic')
        model = config.get('model', 'claude-sonnet-4-5-20250929')
        temperature = config.get('temperature', 0.0)
        max_tokens = config.get('max_tokens', 256)
        timeout_ms = config.get('timeout_ms', 5000)

        user_prompt = (
            f"Evaluate the following text against the guardrail policy.\n\n"
            f"Text to evaluate:\n{text}\n\n"
            f"Respond with a JSON object: "
            f'{{"action": "pass" or "{enforcement_mode}", "reasoning": "...", '
            f'"triggered_spans": [{{"text": "exact quote from input", "reason": "why flagged"}}]}}'
        )

        response = await self._llm_client.chat(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_ms=timeout_ms,
        )

        # Parse LLM response
        import json
        triggered_spans = None
        try:
            result = json.loads(response)
            action = result.get('action', 'pass')
            reasoning = result.get('reasoning', '')
            raw_spans = result.get('triggered_spans', [])
            if raw_spans and isinstance(raw_spans, list):
                triggered_spans = []
                for s in raw_spans:
                    span_text = s.get('text', '')
                    # Find position of span text in original input
                    idx = text.find(span_text) if span_text else -1
                    triggered_spans.append({
                        'start': idx if idx >= 0 else 0,
                        'end': (idx + len(span_text)) if idx >= 0 else 0,
                        'text': span_text,
                        'reason': s.get('reason', ''),
                        'confidence': s.get('confidence', 0.8),
                    })
        except (json.JSONDecodeError, TypeError):
            # Try to extract action from free text
            lower = response.lower() if response else ''
            if enforcement_mode in lower or 'block' in lower or 'fail' in lower:
                action = enforcement_mode
                reasoning = response or 'LLM flagged content'
            else:
                action = 'pass'
                reasoning = response or 'LLM approved content'

        return GuardrailResult(
            guardrail_id=guardrail_id,
            guardrail_name=guardrail_name,
            action=action,
            reasoning=reasoning,
            triggered_spans=triggered_spans,
        )

    async def _eval_ml_classifier(
        self,
        guardrail_id: str,
        guardrail_name: str,
        config: dict,
        text: str,
        enforcement_mode: str,
    ) -> GuardrailResult:
        """Evaluate using external ML classifier endpoint."""
        import httpx

        endpoint_url = config.get('endpoint_url', '')
        threshold = config.get('threshold', 0.5)
        labels = config.get('labels', [])

        if not endpoint_url:
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action="pass",
                reasoning="ML classifier endpoint not configured",
            )

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                endpoint_url,
                json={'text': text, 'labels': labels},
            )
            resp.raise_for_status()
            data = resp.json()

        score = data.get('score', 0.0)
        label = data.get('label', '')

        if score >= threshold:
            return GuardrailResult(
                guardrail_id=guardrail_id,
                guardrail_name=guardrail_name,
                action=enforcement_mode,
                reasoning=f"Classified as '{label}' with score {score:.2f}",
            )

        return GuardrailResult(
            guardrail_id=guardrail_id,
            guardrail_name=guardrail_name,
            action="pass",
            reasoning=f"Below threshold ({score:.2f} < {threshold})",
        )
