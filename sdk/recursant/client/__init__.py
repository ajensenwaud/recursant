"""RecursantClient — single entry point for all registry API operations."""

from __future__ import annotations

from recursant.client._http import HttpClient
from recursant.client.agents import AgentsClient
from recursant.client.evaluation import EvaluationClient
from recursant.client.guardrails import GuardrailsClient
from recursant.client.mesh import MeshClient
from recursant.client.observability import ObservabilityClient
from recursant.client.security import SecurityClient


class RecursantClient:
    """Facade client for the Recursant Agent Registry API.

    Usage::

        client = RecursantClient(
            registry_url="http://localhost:5000",
            username="admin",
            password="secret",
        )
        agents = client.agents.list()
    """

    def __init__(
        self,
        registry_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        tenant_id: str = "default",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._http = HttpClient(
            registry_url,
            username=username,
            password=password,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.agents = AgentsClient(self._http)
        self.security = SecurityClient(self._http)
        self.evaluation = EvaluationClient(self._http)
        self.guardrails = GuardrailsClient(self._http)
        self.mesh = MeshClient(self._http)
        self.observability = ObservabilityClient(self._http)

    def close(self) -> None:
        """Close underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> RecursantClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
