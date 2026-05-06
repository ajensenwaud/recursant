"""Tests for the compliance interceptor."""

import asyncio

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
)
from runtime.sidecar.config import ComplianceConfig
from runtime.sidecar.interceptors.compliance import ComplianceInterceptor


def _make_context(**overrides) -> InterceptorContext:
    defaults = dict(
        direction=Direction.OUTBOUND,
        a2a_method="message/send",
        payload={"message": {"role": "user", "parts": [{"kind": "text", "text": "hello"}]}},
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestComplianceDisabled:
    def test_disabled_passes_everything(self):
        config = ComplianceConfig(enabled=False)
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="us",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS
        assert "disabled" in decision.reason


class TestSovereigntyRules:
    def test_eu_to_eu_allowed(self):
        config = ComplianceConfig(
            enabled=True,
            sovereignty_rules=[
                {"source_zone": "eu", "dest_zone": "eu", "action": "allow"},
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="eu",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS

    def test_eu_to_us_blocked(self):
        config = ComplianceConfig(
            enabled=True,
            sovereignty_rules=[
                {"source_zone": "eu", "dest_zone": "us", "action": "block"},
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="us",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK
        assert "sovereignty" in decision.reason

    def test_wildcard_source_blocks(self):
        config = ComplianceConfig(
            enabled=True,
            sovereignty_rules=[
                {"source_zone": "*", "dest_zone": "restricted", "action": "block"},
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="restricted",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK

    def test_wildcard_dest_allows(self):
        config = ComplianceConfig(
            enabled=True,
            sovereignty_rules=[
                {"source_zone": "eu", "dest_zone": "*", "action": "allow"},
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="anywhere",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS

    def test_no_zone_info_passes(self):
        config = ComplianceConfig(enabled=True)
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context()  # no zone fields set
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS

    def test_unknown_zones_default_block(self):
        config = ComplianceConfig(enabled=True, default_action="block")
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="unknown-zone",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK
        assert "default block" in decision.reason

    def test_same_zone_no_rules_passes(self):
        config = ComplianceConfig(enabled=True, default_action="block")
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="eu",
        )
        decision = _run(interceptor.process(ctx))
        # Same zone, no rules, default block only applies to cross-zone
        assert decision.action == InterceptorAction.PASS


class TestClassificationRules:
    def test_confidential_to_public_blocked(self):
        config = ComplianceConfig(
            enabled=True,
            classification_rules=[
                {
                    "min_classification": "confidential",
                    "max_dest_classification": "internal",
                    "action": "block",
                },
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_classification="confidential",
            dest_classification="public",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK
        assert "classification" in decision.reason

    def test_internal_to_internal_allowed(self):
        config = ComplianceConfig(
            enabled=True,
            classification_rules=[
                {
                    "min_classification": "confidential",
                    "max_dest_classification": "internal",
                    "action": "block",
                },
            ],
        )
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_classification="internal",
            dest_classification="internal",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS

    def test_no_classification_info_passes(self):
        config = ComplianceConfig(enabled=True)
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context()  # no classification set
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS

    def test_higher_to_lower_default_block(self):
        config = ComplianceConfig(enabled=True, default_action="block")
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_classification="restricted",
            dest_classification="public",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK

    def test_lower_to_higher_passes(self):
        config = ComplianceConfig(enabled=True, default_action="block")
        interceptor = ComplianceInterceptor(config)
        ctx = _make_context(
            source_classification="public",
            dest_classification="confidential",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.PASS


class TestRegistryRuleSync:
    def test_update_rules_overrides_config(self):
        config = ComplianceConfig(
            enabled=True,
            sovereignty_rules=[
                {"source_zone": "eu", "dest_zone": "us", "action": "allow"},
            ],
        )
        interceptor = ComplianceInterceptor(config)

        # Override with registry rules
        interceptor.update_rules(
            sovereignty_rules=[
                {"source_zone": "eu", "dest_zone": "us", "action": "block"},
            ],
        )

        ctx = _make_context(
            source_sovereignty_zone="eu",
            dest_sovereignty_zone="us",
        )
        decision = _run(interceptor.process(ctx))
        assert decision.action == InterceptorAction.BLOCK
