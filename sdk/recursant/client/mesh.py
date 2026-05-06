"""Mesh API client — policies, compliance rules, registrations."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import (
    ComplianceRuleCreateRequest,
    ComplianceRuleResponse,
    PolicyCreateRequest,
    PolicyResponse,
    RegistrationResponse,
)


class MeshClient:
    """Mesh policy, compliance, and registration operations."""

    def __init__(self, http: HttpClient):
        self._http = http

    # ── Policies ─────────────────────────────────────────────────────

    def list_policies(self, **params: Any) -> list[PolicyResponse]:
        """List mesh authorization policies (GET /v1/mesh/policies)."""
        data = self._http.get("/v1/mesh/policies", params=params)
        items = data if isinstance(data, list) else data.get("policies", [])
        return [PolicyResponse.model_validate(p) for p in items]

    def create_policy(self, **kwargs: Any) -> PolicyResponse:
        """Create a mesh policy (POST /v1/mesh/policies)."""
        payload = PolicyCreateRequest(**kwargs).model_dump()
        data = self._http.post("/v1/mesh/policies", json=payload)
        return PolicyResponse.model_validate(data)

    def delete_policy(self, policy_id: str) -> None:
        """Delete a mesh policy (DELETE /v1/mesh/policies/{id})."""
        self._http.delete(f"/v1/mesh/policies/{policy_id}")

    # ── Compliance Rules ─────────────────────────────────────────────

    def list_compliance_rules(self, **params: Any) -> list[ComplianceRuleResponse]:
        """List compliance rules (GET /v1/mesh/compliance-rules)."""
        data = self._http.get("/v1/mesh/compliance-rules", params=params)
        items = data if isinstance(data, list) else data.get("rules", [])
        return [ComplianceRuleResponse.model_validate(r) for r in items]

    def create_compliance_rule(self, **kwargs: Any) -> ComplianceRuleResponse:
        """Create a compliance rule (POST /v1/mesh/compliance-rules)."""
        payload = ComplianceRuleCreateRequest(**kwargs).model_dump()
        data = self._http.post("/v1/mesh/compliance-rules", json=payload)
        return ComplianceRuleResponse.model_validate(data)

    def delete_compliance_rule(self, rule_id: str) -> None:
        """Delete a compliance rule (DELETE /v1/mesh/compliance-rules/{id})."""
        self._http.delete(f"/v1/mesh/compliance-rules/{rule_id}")

    # ── Registrations ────────────────────────────────────────────────

    def list_registrations(self, **params: Any) -> list[RegistrationResponse]:
        """List sidecar registrations (GET /v1/mesh/registrations)."""
        data = self._http.get("/v1/mesh/registrations", params=params)
        items = data if isinstance(data, list) else data.get("registrations", [])
        return [RegistrationResponse.model_validate(r) for r in items]
