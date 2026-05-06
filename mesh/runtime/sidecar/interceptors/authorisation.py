"""Authorisation interceptor — enforces allow/deny policies.

Policies are fetched from the registry control plane and cached locally.
Falls back to static config rules if the registry is unreachable.

Also enforces governance status: only ACTIVE agents are allowed to
send or receive messages in the mesh.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Optional

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
    PolicyAction,
    PolicyRule,
)
from runtime.sidecar.config import AuthorisationConfig
from runtime.sidecar.interceptors.base import Interceptor

if TYPE_CHECKING:
    from runtime.sidecar.registry_client import RegistryClient


class AuthorisationInterceptor(Interceptor):
    """Enforces agent-to-agent access control policies and governance status."""

    def __init__(self, config: AuthorisationConfig):
        self._config = config
        self._registry_client: RegistryClient | None = None
        # Policies from registry (set externally via update_policies)
        self._registry_policies: list[PolicyRule] | None = None
        # Fallback policies from static config
        self._fallback_policies = [
            PolicyRule(
                source=r.source,
                destination=r.destination,
                action=PolicyAction(r.action),
                priority=i,
            )
            for i, r in enumerate(config.fallback_rules)
        ]

    @property
    def name(self) -> str:
        return "authorisation"

    def set_registry_client(self, client: RegistryClient) -> None:
        """Set the registry client for governance status checks."""
        self._registry_client = client

    def update_policies(self, policies: list[PolicyRule]) -> None:
        """Update cached policies from the registry control plane."""
        self._registry_policies = sorted(policies, key=lambda p: p.priority)

    def clear_policies(self) -> None:
        """Clear registry policies (forces fallback to static config)."""
        self._registry_policies = None

    @property
    def active_policies(self) -> list[PolicyRule]:
        """Return the currently active policy set."""
        if self._registry_policies is not None:
            return self._registry_policies
        return self._fallback_policies

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="authorisation disabled",
            )

        source = context.source_agent_name or ""
        destination = context.dest_agent_name or ""

        if not source:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="source agent identity unknown",
            )

        if not destination:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="destination agent identity unknown",
            )

        # Governance status check — only ACTIVE agents may participate
        governance_block = self._check_governance_status(source, destination)
        if governance_block:
            return governance_block

        match = self._find_matching_policy(source, destination)

        if match and match.action == PolicyAction.ALLOW:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason=f"policy allows {source} -> {destination}",
            )

        if match and match.action == PolicyAction.DENY:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=f"policy denies {source} -> {destination}",
            )

        # No matching rule — apply default action
        if self._config.default_action == "allow":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason=f"default allow for {source} -> {destination}",
            )

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.BLOCK,
            reason=f"no policy found for {source} -> {destination}; default deny",
        )

    def _find_matching_policy(
        self, source: str, destination: str
    ) -> Optional[PolicyRule]:
        """Find the first matching policy rule (by priority order)."""
        for policy in self.active_policies:
            if self._matches(policy.source, source) and self._matches(
                policy.destination, destination
            ):
                return policy
        return None

    @staticmethod
    def _matches(pattern: str, value: str) -> bool:
        """Check if a policy pattern matches a value. Supports '*' wildcard."""
        if pattern == "*":
            return True
        return fnmatch.fnmatch(value, pattern)

    def _check_governance_status(
        self, source: str, destination: str,
    ) -> InterceptorDecision | None:
        """Check that both source and destination agents are ACTIVE.

        Returns a BLOCK decision if either agent is not ACTIVE, or None
        if both are approved for mesh participation.
        """
        if not self._registry_client:
            return None

        for label, agent_name in [("source", source), ("destination", destination)]:
            try:
                status = self._registry_client.fetch_agent_status(agent_name)
            except Exception:
                # Fail closed — block if registry lookup raises
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=(
                        f"governance check failed for {label} agent "
                        f"'{agent_name}': registry lookup error"
                    ),
                )
            if status is None:
                # Agent not found in registry — block
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"{label} agent '{agent_name}' not found in registry",
                )
            if status.lower() != "active":
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=(
                        f"{label} agent '{agent_name}' is not approved "
                        f"(status: {status}); only ACTIVE agents may "
                        f"participate in the mesh"
                    ),
                )

        return None
