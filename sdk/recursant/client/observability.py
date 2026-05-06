"""Observability API client — traces, golden signals, cost, alerts."""

from __future__ import annotations

from typing import Any

from recursant.client._http import HttpClient
from recursant.client._models import (
    AlertResponse,
    CostSummaryResponse,
    GoldenSignalsResponse,
    ReasoningSpanRequest,
    ReasoningSpanResponse,
    TraceResponse,
    TraceSummary,
)


class ObservabilityClient:
    """Observability queries: traces, golden signals, cost, alerts, spans."""

    def __init__(self, http: HttpClient):
        self._http = http

    # ── Traces ───────────────────────────────────────────────────────

    def get_trace(self, task_id: str, *, include_spans: bool = False) -> TraceResponse:
        """Get a complete trace (GET /v1/mesh/observability/traces/{task_id})."""
        params: dict[str, Any] = {}
        if include_spans:
            params["include_spans"] = "true"
        data = self._http.get(
            f"/v1/mesh/observability/traces/{task_id}", params=params or None
        )
        return TraceResponse.model_validate(data)

    def list_traces(self, **params: Any) -> dict[str, Any]:
        """List traces with pagination (GET /v1/mesh/observability/traces)."""
        data = self._http.get("/v1/mesh/observability/traces", params=params)
        return data

    # ── Reasoning Spans ──────────────────────────────────────────────

    def submit_spans(self, spans: list[dict[str, Any]]) -> dict[str, Any]:
        """Submit reasoning spans (POST /v1/mesh/traces/spans)."""
        validated = [
            ReasoningSpanRequest(**s).model_dump(exclude_none=True) for s in spans
        ]
        data = self._http.post("/v1/mesh/traces/spans", json={"spans": validated})
        return data or {}

    def get_trace_spans(self, task_id: str) -> list[ReasoningSpanResponse]:
        """Get reasoning spans for a trace (GET /v1/mesh/observability/traces/{task_id}/spans)."""
        data = self._http.get(
            f"/v1/mesh/observability/traces/{task_id}/spans"
        )
        items = data if isinstance(data, list) else data.get("spans", [])
        return [ReasoningSpanResponse.model_validate(s) for s in items]

    # ── Golden Signals ───────────────────────────────────────────────

    def get_golden_signals(
        self, agent_name: str | None = None
    ) -> GoldenSignalsResponse:
        """Get golden signals for one or all agents."""
        if agent_name:
            data = self._http.get(
                f"/v1/mesh/observability/golden-signals/{agent_name}"
            )
        else:
            data = self._http.get("/v1/mesh/observability/golden-signals")
        return GoldenSignalsResponse.model_validate(data)

    # ── Cost ─────────────────────────────────────────────────────────

    def get_cost_summary(
        self, agent_name: str | None = None
    ) -> CostSummaryResponse:
        """Get cost summary for one or all agents."""
        if agent_name:
            data = self._http.get(
                f"/v1/mesh/observability/cost/{agent_name}"
            )
        else:
            data = self._http.get("/v1/mesh/observability/cost")
        return CostSummaryResponse.model_validate(data)

    # ── Alerts ───────────────────────────────────────────────────────

    def list_alerts(self, **params: Any) -> list[AlertResponse]:
        """List anomaly alerts (GET /v1/mesh/observability/alerts)."""
        data = self._http.get("/v1/mesh/observability/alerts", params=params)
        items = data if isinstance(data, list) else data.get("alerts", [])
        return [AlertResponse.model_validate(a) for a in items]

    def get_alert(self, anomaly_id: str) -> AlertResponse:
        """Get a single alert (GET /v1/mesh/observability/alerts/{id})."""
        data = self._http.get(f"/v1/mesh/observability/alerts/{anomaly_id}")
        return AlertResponse.model_validate(data)

    def acknowledge_alert(self, anomaly_id: str) -> dict[str, Any]:
        """Acknowledge an alert (POST /v1/mesh/observability/alerts/{id}/acknowledge)."""
        data = self._http.post(
            f"/v1/mesh/observability/alerts/{anomaly_id}/acknowledge"
        )
        return data or {}

    def resolve_alert(self, anomaly_id: str) -> dict[str, Any]:
        """Resolve an alert (POST /v1/mesh/observability/alerts/{id}/resolve)."""
        data = self._http.post(
            f"/v1/mesh/observability/alerts/{anomaly_id}/resolve"
        )
        return data or {}
