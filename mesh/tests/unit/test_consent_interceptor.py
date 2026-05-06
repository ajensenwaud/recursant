"""Tests for GDPR consent enforcement in the compliance interceptor."""

import asyncio
from unittest.mock import MagicMock

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
)
from runtime.sidecar.config import ComplianceConfig
from runtime.sidecar.interceptors.compliance import ComplianceInterceptor


def _make_context(text: str = "hello", data_subject_id: str | None = None, **overrides) -> InterceptorContext:
    payload = {
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            },
        },
    }
    if data_subject_id:
        payload["params"]["_data_subject_id"] = data_subject_id

    defaults = dict(
        direction=Direction.OUTBOUND,
        a2a_method="message/send",
        payload=payload,
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestConsentDisabled:
    def test_consent_not_checked_when_disabled(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=False)
        registry = MagicMock()
        interceptor = ComplianceInterceptor(config, registry_client=registry)

        ctx = _make_context("test", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.PASS
        registry.fetch_consent.assert_not_called()


class TestConsentEnforced:
    def test_blocks_when_no_consent(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True, default_action="block")
        registry = MagicMock()
        registry.fetch_consent.return_value = {
            "has_active_consent": False,
            "consents": [],
        }
        interceptor = ComplianceInterceptor(config, registry_client=registry)

        ctx = _make_context("test with PII", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.BLOCK
        assert "no active consent" in decision.reason
        registry.fetch_consent.assert_called_once_with(
            data_subject_id="subject-1",
            consent_type="processing",
        )

    def test_passes_when_consent_granted(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True)
        registry = MagicMock()
        registry.fetch_consent.return_value = {
            "has_active_consent": True,
            "consents": [{"consent_type": "processing", "granted": True}],
        }
        interceptor = ComplianceInterceptor(config, registry_client=registry)

        ctx = _make_context("test with consent", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.PASS

    def test_warns_when_no_consent_warn_mode(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True, default_action="warn")
        registry = MagicMock()
        registry.fetch_consent.return_value = {
            "has_active_consent": False,
            "consents": [],
        }
        interceptor = ComplianceInterceptor(config, registry_client=registry)

        ctx = _make_context("test", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.PASS
        assert "warn mode" in decision.reason


class TestConsentNoSubject:
    def test_no_subject_id_skips_check(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True)
        registry = MagicMock()
        interceptor = ComplianceInterceptor(config, registry_client=registry)

        ctx = _make_context("no subject")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.PASS
        registry.fetch_consent.assert_not_called()


class TestConsentNoRegistry:
    def test_no_registry_client_skips(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True)
        interceptor = ComplianceInterceptor(config, registry_client=None)

        ctx = _make_context("test", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.PASS

    def test_set_registry_client(self):
        config = ComplianceConfig(enabled=True, consent_enforcement=True, default_action="block")
        interceptor = ComplianceInterceptor(config)

        registry = MagicMock()
        registry.fetch_consent.return_value = {"has_active_consent": False, "consents": []}
        interceptor.set_registry_client(registry)

        ctx = _make_context("test", data_subject_id="subject-1")
        decision = _run(interceptor.process(ctx))

        assert decision.action == InterceptorAction.BLOCK
