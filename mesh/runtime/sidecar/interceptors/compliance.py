"""Compliance interceptor — enforces sovereignty and data classification rules.

Checks:
- Sovereignty: whether data can flow between sovereignty zones
- Classification: whether data at a given classification level can reach
  agents with a lower clearance
"""

from __future__ import annotations

import structlog

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import ComplianceConfig
from runtime.sidecar.interceptors.base import Interceptor

logger = structlog.get_logger()

# Ordered classification levels (lowest to highest)
CLASSIFICATION_LEVELS = ["public", "internal", "confidential", "restricted"]


class ComplianceInterceptor(Interceptor):
    """Enforces sovereignty and data classification compliance rules."""

    def __init__(self, config: ComplianceConfig, registry_client=None):
        self._config = config
        self._registry_client = registry_client
        # Rules synced from registry (set via update_rules)
        self._sovereignty_rules: list[dict] | None = None
        self._classification_rules: list[dict] | None = None

    @property
    def name(self) -> str:
        return "compliance"

    def update_rules(
        self,
        sovereignty_rules: list[dict] | None = None,
        classification_rules: list[dict] | None = None,
    ) -> None:
        """Update rules from the registry."""
        if sovereignty_rules is not None:
            self._sovereignty_rules = sovereignty_rules
        if classification_rules is not None:
            self._classification_rules = classification_rules

    @property
    def sovereignty_rules(self) -> list[dict]:
        """Active sovereignty rules — registry rules or config fallback."""
        if self._sovereignty_rules is not None:
            return self._sovereignty_rules
        return self._config.sovereignty_rules

    @property
    def classification_rules(self) -> list[dict]:
        """Active classification rules — registry rules or config fallback."""
        if self._classification_rules is not None:
            return self._classification_rules
        return self._config.classification_rules

    def set_registry_client(self, registry_client) -> None:
        """Set the registry client (for consent lookups)."""
        self._registry_client = registry_client

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="compliance disabled",
            )

        # Check sovereignty rules
        sov_decision = self._check_sovereignty(context)
        if sov_decision:
            return sov_decision

        # Check classification rules
        cls_decision = self._check_classification(context)
        if cls_decision:
            return cls_decision

        # Check GDPR consent
        consent_decision = self._check_consent(context)
        if consent_decision:
            return consent_decision

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="compliance checks passed",
        )

    def _check_sovereignty(self, context: InterceptorContext) -> InterceptorDecision | None:
        """Check sovereignty zone rules."""
        src_zone = context.source_sovereignty_zone
        dst_zone = context.dest_sovereignty_zone

        if not src_zone or not dst_zone:
            return None  # No zone info — nothing to check

        for rule in self.sovereignty_rules:
            rule_src = rule.get("source_zone", "*")
            rule_dst = rule.get("dest_zone", "*")
            rule_action = rule.get("action", "block")

            if self._zone_matches(rule_src, src_zone) and self._zone_matches(rule_dst, dst_zone):
                if rule_action == "block":
                    return InterceptorDecision(
                        interceptor=self.name,
                        action=InterceptorAction.BLOCK,
                        reason=f"sovereignty violation: {src_zone} -> {dst_zone} blocked",
                    )
                elif rule_action == "allow":
                    return InterceptorDecision(
                        interceptor=self.name,
                        action=InterceptorAction.PASS,
                        reason=f"sovereignty allowed: {src_zone} -> {dst_zone}",
                    )

        # No matching rule — apply default action
        if src_zone != dst_zone and self._config.default_action == "block":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=f"sovereignty: no rule for {src_zone} -> {dst_zone}; default block",
            )

        return None

    def _check_classification(self, context: InterceptorContext) -> InterceptorDecision | None:
        """Check data classification level rules."""
        src_cls = context.source_classification
        dst_cls = context.dest_classification

        if not src_cls or not dst_cls:
            return None  # No classification info — nothing to check

        for rule in self.classification_rules:
            rule_min = rule.get("min_classification")
            rule_max_dest = rule.get("max_dest_classification")
            rule_action = rule.get("action", "block")

            if not rule_min or not rule_max_dest:
                continue

            src_level = self._classification_level(src_cls)
            min_level = self._classification_level(rule_min)
            max_dest_level = self._classification_level(rule_max_dest)
            dst_level = self._classification_level(dst_cls)

            # Rule applies if source classification >= min_classification
            # and destination classification > max_dest_classification
            if src_level >= min_level and dst_level > max_dest_level:
                if rule_action == "block":
                    return InterceptorDecision(
                        interceptor=self.name,
                        action=InterceptorAction.BLOCK,
                        reason=(
                            f"classification violation: {src_cls} data "
                            f"cannot flow to {dst_cls}-classified agent"
                        ),
                    )

        # Default: if source is higher than destination, block
        src_level = self._classification_level(src_cls)
        dst_level = self._classification_level(dst_cls)
        if src_level > dst_level and self._config.default_action == "block":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=(
                    f"classification: {src_cls} data cannot flow to "
                    f"{dst_cls}-classified agent; default block"
                ),
            )

        return None

    @staticmethod
    def _zone_matches(pattern: str, value: str) -> bool:
        """Check if a zone pattern matches a value."""
        if pattern == "*":
            return True
        return pattern.lower() == value.lower()

    @staticmethod
    def _classification_level(classification: str) -> int:
        """Return the numeric level of a classification string."""
        try:
            return CLASSIFICATION_LEVELS.index(classification.lower())
        except ValueError:
            return -1

    def _check_consent(self, context: InterceptorContext) -> InterceptorDecision | None:
        """Check GDPR consent if enforcement is enabled.

        Extracts ``_data_subject_id`` from message params. If present and
        consent enforcement is enabled, queries the registry for active consent.
        """
        if not self._config.consent_enforcement:
            return None

        # Extract data subject ID from message payload
        params = context.payload.get("params", {})
        if isinstance(params, dict):
            data_subject_id = params.get("_data_subject_id")
        else:
            data_subject_id = None

        if not data_subject_id:
            return None  # No subject identified — nothing to check

        if not self._registry_client:
            logger.warning("consent_check_skipped", reason="no registry client")
            return None

        try:
            consent_data = self._registry_client.fetch_consent(
                data_subject_id=data_subject_id,
                consent_type="processing",
            )
        except Exception as e:
            logger.warning("consent_lookup_failed", error=str(e))
            return None  # Fail open on lookup errors

        if not consent_data.get("has_active_consent"):
            logger.warning(
                "consent_missing",
                data_subject_id=data_subject_id,
            )
            if self._config.default_action == "block":
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"no active consent for data subject {data_subject_id}",
                )
            else:
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.PASS,
                    reason=f"consent missing for {data_subject_id} (warn mode)",
                )

        return None
