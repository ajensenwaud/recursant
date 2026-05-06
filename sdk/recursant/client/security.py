"""Security scan API client."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import SecurityScanResponse


class SecurityClient:
    """Security scan operations."""

    def __init__(self, http: HttpClient):
        self._http = http

    def trigger_scan(self, agent_id: str, **kwargs: Any) -> SecurityScanResponse:
        """Trigger a security scan (POST /v1/agents/{id}/security-scans)."""
        payload = kwargs if kwargs else None
        data = self._http.post(
            f"/v1/agents/{agent_id}/security-scans", json=payload
        )
        return SecurityScanResponse.model_validate(data)

    def list_scans(self, agent_id: str, **params: Any) -> list[SecurityScanResponse]:
        """List security scans (GET /v1/agents/{id}/security-scans)."""
        data = self._http.get(
            f"/v1/agents/{agent_id}/security-scans", params=params
        )
        items = data if isinstance(data, list) else data.get("scans", [])
        return [SecurityScanResponse.model_validate(s) for s in items]

    def get_scan(
        self, agent_id: str, scan_id: str
    ) -> SecurityScanResponse:
        """Get scan details (GET /v1/agents/{id}/security-scans/{scan_id})."""
        data = self._http.get(
            f"/v1/agents/{agent_id}/security-scans/{scan_id}"
        )
        return SecurityScanResponse.model_validate(data)
