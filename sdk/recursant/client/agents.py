"""Agents API client."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import (
    AgentCreateRequest,
    AgentResponse,
    AgentUpdateRequest,
    PaginatedAgents,
)


class AgentsClient:
    """CRUD and lifecycle operations for agents."""

    def __init__(self, http: HttpClient):
        self._http = http

    def create(self, **kwargs: Any) -> AgentResponse:
        """Create a new agent (POST /v1/agents)."""
        payload = AgentCreateRequest(**kwargs).model_dump(exclude_none=True)
        data = self._http.post("/v1/agents", json=payload)
        return AgentResponse.model_validate(data)

    def get(self, agent_id: str) -> AgentResponse:
        """Retrieve agent details (GET /v1/agents/{id})."""
        data = self._http.get(f"/v1/agents/{agent_id}")
        return AgentResponse.model_validate(data)

    def list(self, **params: Any) -> PaginatedAgents:
        """List agents with optional filters (GET /v1/agents)."""
        data = self._http.get("/v1/agents", params=params)
        return PaginatedAgents.model_validate(data)

    def update(self, agent_id: str, **kwargs: Any) -> AgentResponse:
        """Update an existing agent (PUT /v1/agents/{id})."""
        payload = AgentUpdateRequest(**kwargs).model_dump(exclude_none=True)
        data = self._http.put(f"/v1/agents/{agent_id}", json=payload)
        return AgentResponse.model_validate(data)

    def delete(self, agent_id: str) -> None:
        """Soft-delete an agent (DELETE /v1/agents/{id})."""
        self._http.delete(f"/v1/agents/{agent_id}")

    def submit(self, agent_id: str) -> AgentResponse:
        """Submit agent for governance review (POST /v1/agents/{id}/submit)."""
        data = self._http.post(f"/v1/agents/{agent_id}/submit")
        return AgentResponse.model_validate(data)

    def versions(self, agent_id: str) -> list[dict[str, Any]]:
        """List all versions of an agent (GET /v1/agents/{id}/versions)."""
        data = self._http.get(f"/v1/agents/{agent_id}/versions")
        if isinstance(data, list):
            return data
        return data.get("versions", [])
