"""PII redaction interceptor — detects and redacts PII in message payloads.

Supports three modes:
- redact: replaces PII with tokens like [EMAIL_REDACTED]
- block: rejects the message if any PII is found
- warn: passes the message but logs a warning

PII detection is delegated to a pluggable PiiDetector backend:
- regex (default): fast regex patterns
- presidio: ML-based NER via Microsoft Presidio
"""

from __future__ import annotations

import copy
import re
from typing import Any

import structlog

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import RedactionConfig
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.interceptors.pii_detector import PiiDetector, PiiMatch, create_detector

logger = structlog.get_logger()

# Map entity types to redaction tokens
REDACTION_TOKENS: dict[str, str] = {
    "email": "[EMAIL_REDACTED]",
    "email_address": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "phone_number": "[PHONE_REDACTED]",
    "ssn": "[SSN_REDACTED]",
    "us_ssn": "[SSN_REDACTED]",
    "credit_card": "[CREDIT_CARD_REDACTED]",
    "ip_address": "[IP_REDACTED]",
    "uk_postcode": "[POSTCODE_REDACTED]",
    "person": "[NAME_REDACTED]",
    "location": "[LOCATION_REDACTED]",
    "iban_code": "[IBAN_REDACTED]",
    "us_bank_number": "[BANK_REDACTED]",
    "us_driver_license": "[DL_REDACTED]",
    "us_passport": "[PASSPORT_REDACTED]",
    "medical_license": "[MEDICAL_REDACTED]",
    "crypto": "[CRYPTO_REDACTED]",
    "nrp": "[NRP_REDACTED]",
}


class RedactionInterceptor(Interceptor):
    """Scans outbound message payloads for PII and applies redaction policy."""

    def __init__(self, config: RedactionConfig):
        self._config = config
        self._detector: PiiDetector = create_detector(
            backend=config.backend,
            custom_patterns=config.custom_patterns if config.custom_patterns else None,
            presidio_score_threshold=config.presidio_score_threshold,
            presidio_entities=config.presidio_entities if config.presidio_entities else None,
        )
        # Register custom pattern tokens
        for name in (config.custom_patterns or {}):
            token_name = name.upper().replace(" ", "_")
            REDACTION_TOKENS.setdefault(name, f"[{token_name}_REDACTED]")

    @property
    def name(self) -> str:
        return "redaction"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="redaction disabled",
            )

        # Scan payload for PII
        detected: dict[str, list[str]] = {}
        self._scan_value(context.payload, detected)

        if not detected:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="no PII detected",
            )

        detected_types = list(detected.keys())
        reason = f"PII detected: {', '.join(detected_types)}"

        if self._config.mode == "block":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=reason,
            )

        if self._config.mode == "warn":
            logger.warning("pii_detected", types=detected_types, mode="warn")
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason=f"{reason} (warn mode)",
            )

        # Mode: redact
        redacted_payload = copy.deepcopy(context.payload)
        self._redact_value(redacted_payload)

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.MODIFY,
            reason=f"{reason} — redacted",
            modified_payload=redacted_payload,
        )

    def _scan_value(self, value: Any, detected: dict[str, list[str]]) -> None:
        """Recursively scan a value for PII using the configured detector."""
        if isinstance(value, str):
            matches = self._detector.detect(value)
            for m in matches:
                detected.setdefault(m.entity_type, []).append(m.text)
        elif isinstance(value, dict):
            for k, v in value.items():
                if not k.startswith("_"):
                    self._scan_value(v, detected)
        elif isinstance(value, list):
            for item in value:
                self._scan_value(item, detected)

    def _redact_value(self, value: Any, parent: Any = None, key: Any = None) -> None:
        """Recursively redact PII in a value, mutating in place."""
        if isinstance(value, str):
            redacted = self._redact_string(value)
            if parent is not None and redacted != value:
                parent[key] = redacted
        elif isinstance(value, dict):
            for k, v in value.items():
                if not k.startswith("_"):
                    self._redact_value(v, value, k)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                self._redact_value(item, value, i)

    def _redact_string(self, text: str) -> str:
        """Redact all PII matches in a string, replacing with tokens."""
        matches = self._detector.detect(text)
        if not matches:
            return text

        # Sort by start position descending so replacements don't shift offsets
        matches.sort(key=lambda m: m.start, reverse=True)

        result = text
        for m in matches:
            token = REDACTION_TOKENS.get(
                m.entity_type,
                f"[{m.entity_type.upper()}_REDACTED]",
            )
            result = result[:m.start] + token + result[m.end:]

        return result
