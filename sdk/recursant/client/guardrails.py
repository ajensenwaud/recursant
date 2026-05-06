"""Guardrails API client."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import GuardrailCreateRequest, GuardrailResponse


class GuardrailsClient:
    """Guardrail CRUD and management."""

    def __init__(self, http: HttpClient):
        self._http = http

    def create(self, **kwargs: Any) -> GuardrailResponse:
        """Create a guardrail (POST /v1/guardrails)."""
        payload = GuardrailCreateRequest(**kwargs).model_dump(exclude_none=True)
        data = self._http.post("/v1/guardrails", json=payload)
        return GuardrailResponse.model_validate(data)

    def list(self, **params: Any) -> list[GuardrailResponse]:
        """List guardrails (GET /v1/guardrails)."""
        data = self._http.get("/v1/guardrails", params=params)
        items = data if isinstance(data, list) else data.get("guardrails", [])
        return [GuardrailResponse.model_validate(g) for g in items]

    def get(self, guardrail_id: str) -> GuardrailResponse:
        """Get guardrail details (GET /v1/guardrails/{id})."""
        data = self._http.get(f"/v1/guardrails/{guardrail_id}")
        return GuardrailResponse.model_validate(data)

    def update(self, guardrail_id: str, **kwargs: Any) -> GuardrailResponse:
        """Update a guardrail (PUT /v1/guardrails/{id})."""
        data = self._http.put(
            f"/v1/guardrails/{guardrail_id}",
            json={k: v for k, v in kwargs.items() if v is not None},
        )
        return GuardrailResponse.model_validate(data)

    def delete(self, guardrail_id: str) -> None:
        """Soft-delete a guardrail (DELETE /v1/guardrails/{id})."""
        self._http.delete(f"/v1/guardrails/{guardrail_id}")
