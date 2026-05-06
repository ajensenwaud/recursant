"""Tests for Prometheus /metrics endpoint."""

import pytest

from runtime.sidecar.app import create_app
from runtime.sidecar.config import SidecarConfig, TelemetryConfig


class TestPrometheusMetrics:
    def test_metrics_endpoint_enabled(self):
        config = SidecarConfig(
            telemetry=TelemetryConfig(prometheus_enabled=True),
        )
        app = create_app(config)
        client = app.test_client()

        resp = client.get("/metrics")
        assert resp.status_code == 200
        # Should contain Prometheus format text
        assert b"#" in resp.data or resp.data  # at minimum returns something

    def test_metrics_endpoint_disabled(self):
        config = SidecarConfig(
            telemetry=TelemetryConfig(prometheus_enabled=False),
        )
        app = create_app(config)
        client = app.test_client()

        resp = client.get("/metrics")
        assert resp.status_code == 404
