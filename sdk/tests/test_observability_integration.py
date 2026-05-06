"""Integration tests for the ObservabilityClient — traces, golden signals, cost, alerts.

Run inside the Kind cluster via kubectl exec against the running registry API.
"""

import uuid

import pytest

from recursant.client._models import CostSummaryResponse, GoldenSignalsResponse


@pytest.mark.integration
class TestObservabilityTraces:
    """Test trace listing and retrieval."""

    def test_list_traces_returns_dict(self, client):
        result = client.observability.list_traces()
        assert isinstance(result, dict)

    def test_submit_and_get_trace_spans(self, client):
        task_id = f"obs-test-{uuid.uuid4().hex[:8]}"
        spans = [
            {
                "task_id": task_id,
                "agent_name": "obs-test-agent",
                "span_type": "tool_call",
                "span_name": "lookup",
                "start_time": "2026-02-28T12:00:00Z",
                "end_time": "2026-02-28T12:00:00.5Z",
                "duration_ms": 500,
            },
        ]
        result = client.observability.submit_spans(spans)
        assert result.get("created") == 1

        retrieved = client.observability.get_trace_spans(task_id)
        assert len(retrieved) >= 1
        assert retrieved[0].span_type == "tool_call"
        assert retrieved[0].span_name == "lookup"


@pytest.mark.integration
class TestGoldenSignals:
    """Test golden signals retrieval."""

    def test_get_golden_signals_all_agents(self, client):
        signals = client.observability.get_golden_signals()
        assert isinstance(signals, GoldenSignalsResponse)

    def test_get_golden_signals_specific_agent(self, client):
        """Querying golden signals for a nonexistent agent returns 404."""
        from recursant.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            client.observability.get_golden_signals(agent_name="nonexistent-agent")


@pytest.mark.integration
class TestCostSummary:
    """Test cost summary retrieval."""

    def test_get_cost_summary(self, client):
        cost = client.observability.get_cost_summary()
        assert isinstance(cost, CostSummaryResponse)


@pytest.mark.integration
class TestTraceRetrieval:
    """Test trace retrieval methods."""

    def test_get_trace_nonexistent_raises_not_found(self, client):
        """Querying a nonexistent task_id raises NotFoundError."""
        from recursant.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            client.observability.get_trace("nonexistent-task-xyz")

    def test_list_traces_returns_dict(self, client):
        result = client.observability.list_traces(limit=5)
        assert isinstance(result, dict)


@pytest.mark.integration
class TestAlerts:
    """Test alert listing and lifecycle."""

    def test_list_alerts_returns_list(self, client):
        alerts = client.observability.list_alerts()
        assert isinstance(alerts, list)

    def test_acknowledge_alert_if_exists(self, client):
        """If any alerts exist, acknowledge the first one."""
        alerts = client.observability.list_alerts()
        if not alerts:
            pytest.skip("No alerts to acknowledge")
        alert_id = str(alerts[0].id)
        result = client.observability.acknowledge_alert(alert_id)
        assert isinstance(result, dict)

    def test_resolve_alert_if_exists(self, client):
        """If any alerts exist, resolve the first one."""
        alerts = client.observability.list_alerts()
        if not alerts:
            pytest.skip("No alerts to resolve")
        alert_id = str(alerts[0].id)
        result = client.observability.resolve_alert(alert_id)
        assert isinstance(result, dict)
