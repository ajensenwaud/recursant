"""Tests for the PII redaction interceptor."""

import asyncio

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
)
from runtime.sidecar.config import RedactionConfig
from runtime.sidecar.interceptors.redaction import RedactionInterceptor


def _make_context(text: str = "hello", **overrides) -> InterceptorContext:
    defaults = dict(
        direction=Direction.OUTBOUND,
        a2a_method="message/send",
        payload={
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRedactionDisabled:
    def test_disabled_passes(self):
        config = RedactionConfig(enabled=False)
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("my email is user@example.com")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS
        assert "disabled" in decision.reason


class TestCleanPayloads:
    def test_no_pii_passes(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("this is a clean message")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS
        assert "no PII" in decision.reason


class TestEmailDetection:
    def test_email_redacted(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("contact user@example.com for details")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "email" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[EMAIL_REDACTED]" in text
        assert "user@example.com" not in text


class TestPhoneDetection:
    def test_phone_redacted(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("call me at +1 (555) 123-4567")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "phone" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[PHONE_REDACTED]" in text


class TestSSNDetection:
    def test_ssn_redacted(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("SSN: 123-45-6789")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "ssn" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[SSN_REDACTED]" in text
        assert "123-45-6789" not in text


class TestCreditCardDetection:
    def test_credit_card_redacted(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("card: 4111 1111 1111 1111")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "credit_card" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[CREDIT_CARD_REDACTED]" in text


class TestIPDetection:
    def test_ip_redacted(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("server at 192.168.1.100")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "ip_address" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[IP_REDACTED]" in text


class TestBlockMode:
    def test_block_on_pii(self):
        config = RedactionConfig(enabled=True, mode="block")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("email: user@example.com")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK
        assert "email" in decision.reason

    def test_block_no_pii_passes(self):
        config = RedactionConfig(enabled=True, mode="block")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("clean message")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS


class TestWarnMode:
    def test_warn_passes_with_pii(self):
        config = RedactionConfig(enabled=True, mode="warn")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("email: user@example.com")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS
        assert "warn" in decision.reason
        assert "email" in decision.reason


class TestCustomPatterns:
    def test_custom_pattern(self):
        config = RedactionConfig(
            enabled=True,
            mode="redact",
            custom_patterns={"employee_id": r"EMP-\d{6}"},
        )
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("employee EMP-123456 requested access")
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        assert "employee_id" in decision.reason
        text = decision.modified_payload["message"]["parts"][0]["text"]
        assert "[EMPLOYEE_ID_REDACTED]" in text
        assert "EMP-123456" not in text


class TestNestedPayload:
    def test_nested_scanning(self):
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context()
        # Override with nested payload
        ctx.payload = {
            "message": {
                "role": "user",
                "parts": [
                    {"kind": "text", "text": "first part"},
                    {"kind": "text", "text": "email: user@example.com"},
                ],
            },
            "metadata": {
                "notes": "contact admin@corp.org",
            },
        }
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.MODIFY
        # Check that both nested emails were redacted
        text1 = decision.modified_payload["message"]["parts"][1]["text"]
        assert "[EMAIL_REDACTED]" in text1
        notes = decision.modified_payload["metadata"]["notes"]
        assert "[EMAIL_REDACTED]" in notes

    def test_internal_fields_skipped(self):
        """Fields starting with _ should not be scanned."""
        config = RedactionConfig(enabled=True, mode="redact")
        interceptor = RedactionInterceptor(config)
        ctx = _make_context("clean message")
        ctx.payload["_api_key"] = "secret@example.com"  # looks like email but internal
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS
