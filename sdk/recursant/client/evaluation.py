"""Evaluation API client."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import EvaluationResponse


class EvaluationClient:
    """Evaluation trigger and result retrieval."""

    def __init__(self, http: HttpClient):
        self._http = http

    def trigger(self, agent_id: str, **kwargs: Any) -> EvaluationResponse:
        """Trigger evaluation (POST /v1/agents/{id}/evaluations)."""
        payload = kwargs if kwargs else None
        data = self._http.post(
            f"/v1/agents/{agent_id}/evaluations", json=payload
        )
        return EvaluationResponse.model_validate(data)

    def list_evaluations(
        self, agent_id: str, **params: Any
    ) -> list[EvaluationResponse]:
        """List evaluations (GET /v1/agents/{id}/evaluations)."""
        data = self._http.get(
            f"/v1/agents/{agent_id}/evaluations", params=params
        )
        items = data if isinstance(data, list) else data.get("evaluations", [])
        return [EvaluationResponse.model_validate(e) for e in items]

    def get_evaluation(
        self, agent_id: str, eval_id: str
    ) -> EvaluationResponse:
        """Get evaluation results (GET /v1/agents/{id}/evaluations/{eval_id})."""
        data = self._http.get(
            f"/v1/agents/{agent_id}/evaluations/{eval_id}"
        )
        return EvaluationResponse.model_validate(data)
