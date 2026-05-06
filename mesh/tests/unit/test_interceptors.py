"""Tests for the interceptor pipeline and individual interceptors."""

import asyncio
import hashlib
import json
from unittest.mock import MagicMock

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
    PolicyAction,
    PolicyRule,
)
from runtime.sidecar.config import (
    AuditConfig,
    AuthenticationConfig,
    AuthorisationConfig,
    FallbackRule,
)
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.authentication import AuthenticationInterceptor
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.interceptors.pipeline import PipelineResult, run_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(**overrides) -> InterceptorContext:
    """Build a default InterceptorContext with optional overrides."""
    defaults = dict(
        direction=Direction.INBOUND,
        a2a_method="message/send",
        payload={"message": {"role": "user", "parts": [{"kind": "text", "text": "hello"}]}},
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
        task_id="task-001",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


class _PassInterceptor(Interceptor):
    """Test interceptor that always passes."""

    @property
    def name(self) -> str:
        return "pass-interceptor"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="always pass",
        )


class _BlockInterceptor(Interceptor):
    """Test interceptor that always blocks."""

    @property
    def name(self) -> str:
        return "block-interceptor"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.BLOCK,
            reason="always block",
        )


class _ModifyInterceptor(Interceptor):
    """Test interceptor that modifies the payload."""

    @property
    def name(self) -> str:
        return "modify-interceptor"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        new_payload = dict(context.payload)
        new_payload["_modified"] = True
        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.MODIFY,
            reason="payload modified",
            modified_payload=new_payload,
        )


class _RecordingInterceptor(Interceptor):
    """Test interceptor that records what payload it saw."""

    def __init__(self):
        self.seen_payloads: list[dict] = []

    @property
    def name(self) -> str:
        return "recording-interceptor"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        self.seen_payloads.append(dict(context.payload))
        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="recorded",
        )


# ===========================================================================
# Pipeline Tests
# ===========================================================================

class TestPipeline:
    def test_empty_pipeline_allows(self):
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(run_pipeline([], ctx))

        assert result.allowed is True
        assert result.decisions == []

    def test_all_pass(self):
        ctx = _make_context()
        interceptors = [_PassInterceptor(), _PassInterceptor()]
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline(interceptors, ctx)
        )

        assert result.allowed is True
        assert len(result.decisions) == 2
        assert all(d.action == InterceptorAction.PASS for d in result.decisions)

    def test_blocks_on_first_rejection(self):
        ctx = _make_context()
        p1 = _PassInterceptor()
        blocker = _BlockInterceptor()
        p2 = _PassInterceptor()  # should never run
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([p1, blocker, p2], ctx)
        )

        assert result.allowed is False
        # Only 2 decisions: pass then block. The third never ran.
        assert len(result.decisions) == 2
        assert result.decisions[0].action == InterceptorAction.PASS
        assert result.decisions[1].action == InterceptorAction.BLOCK

    def test_blocking_decision_property(self):
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([_BlockInterceptor()], ctx)
        )

        assert result.blocking_decision is not None
        assert result.blocking_decision.interceptor == "block-interceptor"

    def test_no_blocking_decision_when_allowed(self):
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([_PassInterceptor()], ctx)
        )

        assert result.blocking_decision is None

    def test_modify_updates_payload_for_subsequent_interceptors(self):
        ctx = _make_context()
        recorder = _RecordingInterceptor()
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([_ModifyInterceptor(), recorder], ctx)
        )

        assert result.allowed is True
        # The recorder should have seen the modified payload
        assert len(recorder.seen_payloads) == 1
        assert recorder.seen_payloads[0]["_modified"] is True

    def test_modify_updates_context_payload(self):
        ctx = _make_context()
        asyncio.get_event_loop().run_until_complete(
            run_pipeline([_ModifyInterceptor()], ctx)
        )

        assert ctx.payload.get("_modified") is True

    def test_decisions_ordered(self):
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline(
                [_PassInterceptor(), _ModifyInterceptor(), _PassInterceptor()], ctx
            )
        )

        assert len(result.decisions) == 3
        assert result.decisions[0].interceptor == "pass-interceptor"
        assert result.decisions[1].interceptor == "modify-interceptor"
        assert result.decisions[2].interceptor == "pass-interceptor"


# ===========================================================================
# Authentication Interceptor Tests
# ===========================================================================

class TestAuthenticationInterceptor:
    def test_disabled_always_passes(self):
        config = AuthenticationConfig(enabled=False)
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "disabled" in decision.reason

    def test_mtls_passes_with_valid_cert_cn(self):
        config = AuthenticationConfig(enabled=True, schemes=["mtls"])
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn="sidecar-a")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "sidecar-a" in decision.reason

    def test_mtls_sets_source_agent_name_from_cn(self):
        config = AuthenticationConfig(enabled=True, schemes=["mtls"])
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn="sidecar-a", source_agent_name=None)

        asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert ctx.source_agent_name == "sidecar-a"

    def test_mtls_does_not_overwrite_existing_source_name(self):
        config = AuthenticationConfig(enabled=True, schemes=["mtls"])
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn="sidecar-a", source_agent_name="already-set")

        asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert ctx.source_agent_name == "already-set"

    def test_mtls_blocks_without_cert(self):
        config = AuthenticationConfig(enabled=True, schemes=["mtls"])
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn=None)

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK

    def test_api_key_passes_with_correct_key(self):
        config = AuthenticationConfig(
            enabled=True, schemes=["api_key"], api_key="secret-123"
        )
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(
            client_cert_cn=None, payload={"_api_key": "secret-123", "data": "x"}
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    def test_api_key_blocks_with_wrong_key(self):
        config = AuthenticationConfig(
            enabled=True, schemes=["api_key"], api_key="secret-123"
        )
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(
            client_cert_cn=None, payload={"_api_key": "wrong-key"}
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "invalid" in decision.reason

    def test_api_key_blocks_when_missing(self):
        config = AuthenticationConfig(
            enabled=True, schemes=["api_key"], api_key="secret-123"
        )
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn=None, payload={"data": "x"})

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK

    def test_mtls_preferred_over_api_key(self):
        """When both schemes are available and cert is present, use mTLS."""
        config = AuthenticationConfig(
            enabled=True, schemes=["mtls", "api_key"], api_key="secret-123"
        )
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn="sidecar-a")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "mTLS" in decision.reason

    def test_falls_back_to_api_key_when_no_cert(self):
        """When mTLS scheme is listed but no cert, fall back to API key."""
        config = AuthenticationConfig(
            enabled=True, schemes=["mtls", "api_key"], api_key="secret-123"
        )
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(
            client_cert_cn=None, payload={"_api_key": "secret-123"}
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "API key" in decision.reason

    def test_blocks_when_no_schemes_match(self):
        config = AuthenticationConfig(enabled=True, schemes=["mtls"])
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn=None)

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "no valid authentication" in decision.reason


# ===========================================================================
# JWT Authentication Tests
# ===========================================================================

class TestJWTAuthentication:
    """Test JWT authentication scheme."""

    def _make_jwt_config(self, **overrides):
        defaults = dict(
            enabled=True,
            schemes=["jwt"],
            jwt_secret="test-secret-key-for-unit-tests-32b+",
            jwt_algorithms=["HS256"],
        )
        defaults.update(overrides)
        return AuthenticationConfig(**defaults)

    def _make_token(self, payload, secret="test-secret-key-for-unit-tests-32b+", algorithm="HS256"):
        import jwt as pyjwt
        return pyjwt.encode(payload, secret, algorithm=algorithm)

    def test_valid_jwt_passes(self):
        config = self._make_jwt_config()
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token({"sub": "agent-jwt", "exp": 9999999999})
        ctx = _make_context(
            client_cert_cn=None,
            source_agent_name="",
            payload={"_jwt_token": token, "data": "x"},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "JWT" in decision.reason
        assert ctx.source_agent_name == "agent-jwt"

    def test_expired_jwt_blocks(self):
        config = self._make_jwt_config()
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token({"sub": "agent-jwt", "exp": 1})  # expired
        ctx = _make_context(
            client_cert_cn=None,
            payload={"_jwt_token": token},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "expired" in decision.reason

    def test_wrong_issuer_blocks(self):
        config = self._make_jwt_config(jwt_issuer="expected-issuer")
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token({"sub": "agent-jwt", "iss": "wrong-issuer", "exp": 9999999999})
        ctx = _make_context(
            client_cert_cn=None,
            payload={"_jwt_token": token},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "issuer" in decision.reason

    def test_missing_token_blocks(self):
        config = self._make_jwt_config()
        interceptor = AuthenticationInterceptor(config)
        ctx = _make_context(client_cert_cn=None, payload={"data": "x"})

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK

    def test_scheme_fallthrough_mtls_to_jwt(self):
        """When mTLS has no cert, should fall through to JWT."""
        config = self._make_jwt_config(schemes=["mtls", "jwt"])
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token({"sub": "jwt-agent", "exp": 9999999999})
        ctx = _make_context(
            client_cert_cn=None,
            payload={"_jwt_token": token},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "JWT" in decision.reason

    def test_custom_agent_claim(self):
        config = self._make_jwt_config(jwt_agent_claim="agent_name")
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token({"agent_name": "custom-agent", "exp": 9999999999})
        ctx = _make_context(
            client_cert_cn=None,
            source_agent_name=None,
            payload={"_jwt_token": token},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert ctx.source_agent_name == "custom-agent"

    def test_wrong_secret_blocks(self):
        config = self._make_jwt_config()
        interceptor = AuthenticationInterceptor(config)
        token = self._make_token(
            {"sub": "agent-jwt", "exp": 9999999999},
            secret="wrong-secret-that-is-at-least-32bytes",
        )
        ctx = _make_context(
            client_cert_cn=None,
            payload={"_jwt_token": token},
        )

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "validation failed" in decision.reason


# ===========================================================================
# Authorisation Interceptor Tests
# ===========================================================================

class TestAuthorisationInterceptor:
    def _make_config(self, **overrides) -> AuthorisationConfig:
        defaults = dict(
            enabled=True,
            default_action="deny",
            fallback_rules=[
                FallbackRule(source="agent-a", destination="agent-b", action="allow"),
                FallbackRule(source="*", destination="*", action="deny"),
            ],
        )
        defaults.update(overrides)
        return AuthorisationConfig(**defaults)

    def test_disabled_always_passes(self):
        config = self._make_config(enabled=False)
        interceptor = AuthorisationInterceptor(config)
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    def test_allowed_by_fallback_rule(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "allows" in decision.reason

    def test_denied_by_wildcard_rule(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        ctx = _make_context(source_agent_name="agent-x", dest_agent_name="agent-y")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "denies" in decision.reason

    def test_default_deny_when_no_rules_match(self):
        config = self._make_config(fallback_rules=[])
        interceptor = AuthorisationInterceptor(config)
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "default deny" in decision.reason

    def test_default_allow_when_configured(self):
        config = self._make_config(default_action="allow", fallback_rules=[])
        interceptor = AuthorisationInterceptor(config)
        ctx = _make_context(source_agent_name="agent-x", dest_agent_name="agent-y")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        assert "default allow" in decision.reason

    def test_blocks_when_source_unknown(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        ctx = _make_context(source_agent_name=None, dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "source" in decision.reason

    def test_blocks_when_destination_unknown(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name=None)

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "destination" in decision.reason

    def test_registry_policies_take_precedence(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        # Registry says agent-a -> agent-b is DENIED (overrides fallback allow)
        interceptor.update_policies([
            PolicyRule(source="agent-a", destination="agent-b", action=PolicyAction.DENY, priority=0),
        ])
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK

    def test_clear_policies_reverts_to_fallback(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        interceptor.update_policies([
            PolicyRule(source="*", destination="*", action=PolicyAction.DENY, priority=0),
        ])
        interceptor.clear_policies()
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        # Fallback rules allow agent-a -> agent-b
        assert decision.action == InterceptorAction.PASS

    def test_policies_sorted_by_priority(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        interceptor.update_policies([
            PolicyRule(source="*", destination="*", action=PolicyAction.DENY, priority=10),
            PolicyRule(source="agent-a", destination="agent-b", action=PolicyAction.ALLOW, priority=0),
        ])
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    def test_active_policies_returns_registry_when_set(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        registry_policies = [
            PolicyRule(source="x", destination="y", action=PolicyAction.ALLOW, priority=0),
        ]
        interceptor.update_policies(registry_policies)

        assert len(interceptor.active_policies) == 1
        assert interceptor.active_policies[0].source == "x"

    def test_active_policies_returns_fallback_when_empty(self):
        interceptor = AuthorisationInterceptor(self._make_config())

        assert len(interceptor.active_policies) == 2
        assert interceptor.active_policies[0].source == "agent-a"

    def test_first_match_wins(self):
        """With two matching rules, the first by priority wins."""
        config = self._make_config(fallback_rules=[
            FallbackRule(source="agent-a", destination="agent-b", action="deny"),
            FallbackRule(source="agent-a", destination="agent-b", action="allow"),
        ])
        interceptor = AuthorisationInterceptor(config)
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK

    # --- Governance status enforcement ---

    def test_blocks_when_source_agent_not_active(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = lambda name: (
            "draft" if name == "agent-a" else "active"
        )
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "not approved" in decision.reason
        assert "agent-a" in decision.reason
        assert "draft" in decision.reason

    def test_blocks_when_dest_agent_not_active(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = lambda name: (
            "active" if name == "agent-a" else "pending_approval"
        )
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "not approved" in decision.reason
        assert "agent-b" in decision.reason

    def test_blocks_when_agent_not_found_in_registry(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.return_value = None
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="unknown-agent", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "not found" in decision.reason

    def test_passes_when_both_agents_active(self):
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.return_value = "active"
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        # Should pass governance check and then pass on policy too
        assert decision.action == InterceptorAction.PASS

    def test_governance_skipped_without_registry_client(self):
        """Without a registry client, governance check is a no-op (backward compat)."""
        interceptor = AuthorisationInterceptor(self._make_config())
        # No set_registry_client call
        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        # Falls through to policy check which allows agent-a -> agent-b
        assert decision.action == InterceptorAction.PASS

    def test_governance_case_insensitive(self):
        """Registry may return 'ACTIVE' in any case."""
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.return_value = "ACTIVE"
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    # --- A1: All non-ACTIVE statuses are blocked ---

    @pytest.mark.parametrize("status", [
        "draft", "submitted", "testing", "evaluating", "pending_approval",
        "suspended", "decommissioned", "rejected", "security_failed",
        "evaluation_failed",
    ])
    def test_blocks_each_non_active_status(self, status):
        """Every non-ACTIVE governance status must be blocked."""
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = lambda name: (
            status if name == "agent-a" else "active"
        )
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert status in decision.reason

    # --- A2: Both agents non-ACTIVE — source checked first ---

    def test_both_non_active_reports_source_first(self):
        """When both agents are non-ACTIVE, error should reference source (fail fast)."""
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.return_value = "draft"
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "source" in decision.reason
        assert "agent-a" in decision.reason
        # Should NOT mention destination (don't leak info about other agents)
        assert "agent-b" not in decision.reason

    # --- A3: Governance enforced on inbound direction ---

    def test_governance_enforced_inbound(self):
        """Governance blocks inbound requests from non-ACTIVE agents."""
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = lambda name: (
            "active" if name == "agent-a" else "draft"
        )
        interceptor.set_registry_client(registry)

        ctx = _make_context(
            direction=Direction.INBOUND,
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
        )
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.BLOCK
        assert "agent-b" in decision.reason
        assert "draft" in decision.reason

    # --- A4: Registry client exception handling ---

    def test_governance_blocks_on_registry_exception(self):
        """If fetch_agent_status raises an unexpected exception, fail closed (block)."""
        interceptor = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = RuntimeError("connection pool exhausted")
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        # Should fail closed — block, not crash or pass
        assert decision.action == InterceptorAction.BLOCK

    # --- A5: Full pipeline integration — blocked agent produces no audit ---

    def test_pipeline_governance_block_no_audit(self):
        """Blocked by governance — audit interceptor never runs, no record created."""
        auth = AuthenticationInterceptor(
            AuthenticationConfig(enabled=True, schemes=["mtls"])
        )
        authz = AuthorisationInterceptor(self._make_config())
        registry = MagicMock()
        registry.fetch_agent_status.side_effect = lambda name: (
            "active" if name == "sidecar-a" else "draft"
        )
        authz.set_registry_client(registry)
        audit = AuditInterceptor(AuditConfig(enabled=True))

        ctx = _make_context(
            client_cert_cn="sidecar-a",
            source_agent_name=None,
            dest_agent_name="agent-b",
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        assert result.allowed is False
        assert result.blocking_decision.interceptor == "authorisation"
        assert "governance" in result.blocking_decision.reason or "not approved" in result.blocking_decision.reason
        # Audit interceptor never ran — no records
        assert len(audit.all_records) == 0

    # --- A6: Governance check skipped when authorisation disabled ---

    def test_governance_skipped_when_disabled(self):
        """If authz is disabled, governance check should also be skipped."""
        config = self._make_config(enabled=False)
        interceptor = AuthorisationInterceptor(config)
        registry = MagicMock()
        interceptor.set_registry_client(registry)

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS
        # No registry call should be made when disabled
        registry.fetch_agent_status.assert_not_called()


# ===========================================================================
# Audit Interceptor Tests
# ===========================================================================

class TestAuditInterceptor:
    def test_always_passes(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context()

        decision = asyncio.get_event_loop().run_until_complete(
            interceptor.process(ctx)
        )
        assert decision.action == InterceptorAction.PASS

    def test_disabled_passes_without_recording(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=False))
        ctx = _make_context()

        asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))
        assert len(interceptor.all_records) == 0

    def test_process_does_not_create_records(self):
        """process() observes only — records are created by create_record_from_result()."""
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context(
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
            task_id="task-42",
            a2a_method="message/send",
        )

        asyncio.get_event_loop().run_until_complete(interceptor.process(ctx))

        assert len(interceptor.all_records) == 0
        assert len(interceptor.pending_records) == 0

    def test_create_record_has_correct_fields(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context(
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
            task_id="task-42",
            a2a_method="message/send",
        )
        decisions = [
            InterceptorDecision(
                interceptor="auth", action=InterceptorAction.PASS, reason="ok"
            ),
        ]

        record = interceptor.create_record_from_result(ctx, decisions, "success")

        assert record.source_agent_name == "agent-a"
        assert record.dest_agent_name == "agent-b"
        assert record.task_id == "task-42"
        assert record.a2a_method == "message/send"
        assert record.direction == Direction.INBOUND
        assert record.timestamp is not None

    def test_message_hash_is_sha256(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        payload = {"message": "hello world"}
        ctx = _make_context(payload=payload)
        decisions = []

        record = interceptor.create_record_from_result(ctx, decisions, "success")

        expected_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        assert record.message_hash == expected_hash
        assert len(record.message_hash) == 64  # SHA-256 hex

    def test_hash_excludes_internal_fields(self):
        """Fields prefixed with _ should not affect the hash."""
        interceptor = AuditInterceptor(AuditConfig(enabled=True))

        payload_with = {"message": "hello", "_api_key": "secret"}
        payload_without = {"message": "hello"}

        ctx1 = _make_context(payload=payload_with)
        ctx2 = _make_context(payload=payload_without)

        r1 = interceptor.create_record_from_result(ctx1, [], "success")
        r2 = interceptor.create_record_from_result(ctx2, [], "success")

        assert r1.message_hash == r2.message_hash

    def test_records_buffered_for_shipping(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context()

        interceptor.create_record_from_result(ctx, [], "success")

        assert len(interceptor.pending_records) == 1

    def test_drain_buffer_clears(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context()

        interceptor.create_record_from_result(ctx, [], "success")
        drained = interceptor.drain_buffer()

        assert len(drained) == 1
        assert len(interceptor.pending_records) == 0
        # all_records is not affected by drain
        assert len(interceptor.all_records) == 1

    def test_multiple_records(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))

        for i in range(5):
            ctx = _make_context(task_id=f"task-{i}")
            interceptor.create_record_from_result(ctx, [], "success")

        assert len(interceptor.all_records) == 5
        assert len(interceptor.pending_records) == 5

    def test_create_record_from_result(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context()
        decisions = [
            InterceptorDecision(
                interceptor="auth", action=InterceptorAction.PASS, reason="ok"
            ),
        ]

        record = interceptor.create_record_from_result(ctx, decisions, "success")

        assert record.decision == "pass"
        assert record.outcome == "success"
        assert len(record.interceptor_decisions) == 1
        assert record.interceptor_decisions[0].interceptor == "auth"

    def test_create_record_from_result_blocked(self):
        interceptor = AuditInterceptor(AuditConfig(enabled=True))
        ctx = _make_context()
        decisions = [
            InterceptorDecision(
                interceptor="authz", action=InterceptorAction.BLOCK, reason="denied"
            ),
        ]

        record = interceptor.create_record_from_result(ctx, decisions, "blocked")

        assert record.decision == "block"
        assert record.outcome == "blocked"


# ===========================================================================
# Full Pipeline Integration (unit-level)
# ===========================================================================

class TestPipelineWithRealInterceptors:
    """Test the pipeline with actual interceptor implementations."""

    def _build_pipeline(self) -> tuple[
        AuthenticationInterceptor,
        AuthorisationInterceptor,
        AuditInterceptor,
    ]:
        auth = AuthenticationInterceptor(
            AuthenticationConfig(enabled=True, schemes=["mtls", "api_key"], api_key="test-key")
        )
        authz = AuthorisationInterceptor(
            AuthorisationConfig(
                enabled=True,
                default_action="deny",
                fallback_rules=[
                    FallbackRule(source="sidecar-a", destination="agent-b", action="allow"),
                ],
            )
        )
        audit = AuditInterceptor(AuditConfig(enabled=True))
        return auth, authz, audit

    def test_authenticated_and_authorised_passes(self):
        auth, authz, audit = self._build_pipeline()
        ctx = _make_context(
            client_cert_cn="sidecar-a",
            source_agent_name=None,  # will be set by auth from CN
            dest_agent_name="agent-b",
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        assert result.allowed is True
        assert len(result.decisions) == 3
        assert ctx.source_agent_name == "sidecar-a"

    def test_unauthenticated_blocked_at_auth(self):
        auth, authz, audit = self._build_pipeline()
        ctx = _make_context(client_cert_cn=None)

        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        assert result.allowed is False
        assert len(result.decisions) == 1  # blocked at first interceptor
        assert result.blocking_decision.interceptor == "authentication"

    def test_authenticated_but_unauthorised_blocked(self):
        auth, authz, audit = self._build_pipeline()
        ctx = _make_context(
            client_cert_cn="sidecar-x",  # not in allow rules
            source_agent_name=None,
            dest_agent_name="agent-b",
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        assert result.allowed is False
        assert len(result.decisions) == 2
        assert result.decisions[0].action == InterceptorAction.PASS  # auth passed
        assert result.decisions[1].action == InterceptorAction.BLOCK  # authz blocked

    def test_api_key_auth_then_authorised(self):
        auth, authz, audit = self._build_pipeline()
        ctx = _make_context(
            client_cert_cn=None,
            source_agent_name="sidecar-a",
            dest_agent_name="agent-b",
            payload={"_api_key": "test-key", "message": "hi"},
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        assert result.allowed is True

    def test_audit_no_records_from_pipeline_alone(self):
        """Pipeline process() calls don't create records; create_record_from_result() does."""
        auth, authz, audit = self._build_pipeline()
        ctx = _make_context(
            client_cert_cn="sidecar-a",
            source_agent_name=None,
            dest_agent_name="agent-b",
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_pipeline([auth, authz, audit], ctx)
        )

        # Pipeline alone doesn't create records
        assert len(audit.all_records) == 0

        # Records are created explicitly after the pipeline
        audit.create_record_from_result(ctx, result.decisions, "success")
        assert len(audit.all_records) == 1


# ===========================================================================
# Lifecycle Wiring — Governance Integration (C1, C2)
# ===========================================================================

class TestLifecycleGovernanceWiring:
    """Verify that LifecycleManager wires registry client into authz."""

    def test_registry_client_wired_after_startup(self):
        """C1: After startup(), authz interceptor's _registry_client is set."""
        from runtime.sidecar.lifecycle import LifecycleManager

        config = MagicMock()
        config.agent_id = "agent-123"
        config.heartbeat_interval_seconds = 30
        config.policy_sync_interval_seconds = 60
        config.tool_sync_interval_seconds = 1
        config.tls = None
        config.port = 8080
        config.a2a_port = 8443

        registry = MagicMock()
        registry.register.return_value = {"status": "ok"}
        registry.cached_policies = None
        registry.fetch_registered_agents.return_value = set()
        registry.fetch_tools_for_agent.return_value = []
        registry.fetch_egress_rules_for_agent.return_value = []

        authz = AuthorisationInterceptor(
            AuthorisationConfig(enabled=True, default_action="deny", fallback_rules=[])
        )
        audit = AuditInterceptor(AuditConfig(enabled=True))

        manager = LifecycleManager(
            config=config,
            registry_client=registry,
            authz_interceptor=authz,
            audit_interceptor=audit,
            agent_card_json={"name": "test"},
        )

        assert authz._registry_client is None

        manager.startup()

        assert authz._registry_client is registry

        # Clean up background threads
        manager.shutdown()

    def test_governance_active_after_startup(self):
        """C2: After startup(), authz blocks non-ACTIVE agents via registry."""
        from runtime.sidecar.lifecycle import LifecycleManager

        config = MagicMock()
        config.agent_id = "agent-123"
        config.heartbeat_interval_seconds = 30
        config.policy_sync_interval_seconds = 60
        config.tool_sync_interval_seconds = 1
        config.tls = None
        config.port = 8080
        config.a2a_port = 8443

        registry = MagicMock()
        registry.register.return_value = {"status": "ok"}
        registry.cached_policies = None
        registry.fetch_registered_agents.return_value = set()
        registry.fetch_agent_status.return_value = "draft"
        registry.fetch_tools_for_agent.return_value = []
        registry.fetch_egress_rules_for_agent.return_value = []

        authz = AuthorisationInterceptor(
            AuthorisationConfig(
                enabled=True,
                default_action="allow",
                fallback_rules=[],
            )
        )
        audit = AuditInterceptor(AuditConfig(enabled=True))

        manager = LifecycleManager(
            config=config,
            registry_client=registry,
            authz_interceptor=authz,
            audit_interceptor=audit,
            agent_card_json={"name": "test"},
        )

        manager.startup()

        ctx = _make_context(source_agent_name="agent-a", dest_agent_name="agent-b")
        decision = asyncio.get_event_loop().run_until_complete(
            authz.process(ctx)
        )

        assert decision.action == InterceptorAction.BLOCK
        assert "draft" in decision.reason
        registry.fetch_agent_status.assert_called()

        manager.shutdown()
