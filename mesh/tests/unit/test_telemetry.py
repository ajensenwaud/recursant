"""Tests for OpenTelemetry tracing and metrics."""

import pytest

from runtime.sidecar.config import TelemetryConfig
from runtime.sidecar.telemetry import (
    extract_trace_context,
    get_trace_context_headers,
    init_telemetry,
    record_discovery_cache,
    record_interceptor_decision,
    record_request,
    record_request_duration,
    reset_telemetry,
    trace_span,
)


@pytest.fixture(autouse=True)
def _clean_telemetry():
    """Reset telemetry state before and after each test."""
    reset_telemetry()
    yield
    reset_telemetry()


class TestTelemetryInit:
    def test_init_creates_tracer_and_meter(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        from runtime.sidecar.telemetry import _initialized, _tracer, _meter
        assert _initialized is True
        assert _tracer is not None
        assert _meter is not None

    def test_init_disabled_does_nothing(self):
        config = TelemetryConfig(enabled=False)
        init_telemetry(config)

        from runtime.sidecar.telemetry import _initialized
        assert _initialized is False

    def test_init_idempotent(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        init_telemetry(config)  # should not raise

        from runtime.sidecar.telemetry import _initialized
        assert _initialized is True

    def test_init_creates_metrics_instruments(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        from runtime.sidecar.telemetry import (
            _request_counter,
            _request_duration,
            _interceptor_counter,
            _discovery_cache_hits,
            _discovery_cache_misses,
        )
        assert _request_counter is not None
        assert _request_duration is not None
        assert _interceptor_counter is not None
        assert _discovery_cache_hits is not None
        assert _discovery_cache_misses is not None


class TestTraceSpan:
    def test_span_created_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        with trace_span("test-operation", {"key": "value"}) as span:
            assert span is not None

    def test_span_noop_when_disabled(self):
        # Telemetry not initialized
        with trace_span("test-operation") as span:
            assert span is None

    def test_span_with_attributes(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        with trace_span("test-op", {"agent": "research-assistant", "method": "message/send"}) as span:
            assert span is not None
            # Span should have the attributes set (OTel SDK stores them)


class TestMetricRecording:
    def test_record_request_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        # Should not raise
        record_request("inbound", "message/send", "success")

    def test_record_request_when_disabled(self):
        # Should not raise even when not initialized
        record_request("inbound", "message/send", "success")

    def test_record_request_duration_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        record_request_duration("outbound", "message/send", 0.123)

    def test_record_request_duration_when_disabled(self):
        record_request_duration("outbound", "message/send", 0.123)

    def test_record_interceptor_decision_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        record_interceptor_decision("authentication", "pass")

    def test_record_interceptor_decision_when_disabled(self):
        record_interceptor_decision("authentication", "pass")

    def test_record_discovery_cache_hit(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        record_discovery_cache(hit=True)

    def test_record_discovery_cache_miss(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)
        record_discovery_cache(hit=False)

    def test_record_discovery_cache_when_disabled(self):
        record_discovery_cache(hit=True)
        record_discovery_cache(hit=False)


class TestTraceContextPropagation:
    def test_get_headers_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        headers = get_trace_context_headers()
        assert isinstance(headers, dict)

    def test_get_headers_when_disabled(self):
        headers = get_trace_context_headers()
        assert headers == {}

    def test_extract_context_when_enabled(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        ctx = extract_trace_context({"traceparent": "00-abc123-def456-01"})
        # Should return a context object (even if traceparent is invalid format)
        assert ctx is not None

    def test_extract_context_when_disabled(self):
        ctx = extract_trace_context({"traceparent": "00-abc123-def456-01"})
        assert ctx is None

    def test_roundtrip_trace_context(self):
        """Inject trace context, then extract it — should round-trip."""
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        # Create a span to establish trace context
        with trace_span("test-roundtrip"):
            headers = get_trace_context_headers()
            # When there's an active span, we should get traceparent
            if "traceparent" in headers:
                ctx = extract_trace_context(headers)
                assert ctx is not None


class TestResetTelemetry:
    def test_reset_clears_state(self):
        config = TelemetryConfig(enabled=True, service_name="test-sidecar")
        init_telemetry(config)

        from runtime.sidecar.telemetry import _initialized
        assert _initialized is True

        reset_telemetry()

        from runtime.sidecar.telemetry import _initialized as _init_after
        assert _init_after is False
