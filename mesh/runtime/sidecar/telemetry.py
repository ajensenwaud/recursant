"""OpenTelemetry tracing and metrics for the Recursant sidecar.

Provides:
- Trace spans for A2A requests and interceptor pipeline
- Metrics counters and histograms for requests and interceptor decisions
- Trace context propagation via W3C Trace Context headers
- Flask and httpx auto-instrumentation
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Optional

import structlog

from runtime.sidecar.config import TelemetryConfig

logger = structlog.get_logger()

# Module-level state
_tracer = None
_meter = None
_initialized = False

# Metrics instruments (set during init)
_request_counter = None
_request_duration = None
_interceptor_counter = None
_discovery_cache_hits = None
_discovery_cache_misses = None
_cb_active_connections = None
_cb_rejected_pool = None
_rate_limit_rejected = None


def init_telemetry(config: TelemetryConfig) -> None:
    """Initialize OpenTelemetry tracing and metrics.

    Safe to call multiple times — only initializes once.
    """
    global _tracer, _meter, _initialized
    global _request_counter, _request_duration, _interceptor_counter
    global _discovery_cache_hits, _discovery_cache_misses

    global _cb_active_connections, _cb_rejected_pool, _rate_limit_rejected

    if _initialized or not config.enabled:
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": config.service_name})

        # Traces
        tracer_provider = TracerProvider(resource=resource)

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint)
            tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        except Exception:
            logger.info("otlp_exporter_unavailable", msg="spans will not be exported")

        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer(config.service_name)

        # Metrics
        meter_provider = MeterProvider(resource=resource)
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(config.service_name)

        _request_counter = _meter.create_counter(
            "sidecar.requests.total",
            description="Total A2A requests processed",
        )
        _request_duration = _meter.create_histogram(
            "sidecar.request.duration",
            description="Request processing duration in seconds",
            unit="s",
        )
        _interceptor_counter = _meter.create_counter(
            "sidecar.interceptor.decisions",
            description="Interceptor decision counts",
        )
        _discovery_cache_hits = _meter.create_counter(
            "sidecar.discovery.cache_hits",
            description="Discovery cache hits",
        )
        _discovery_cache_misses = _meter.create_counter(
            "sidecar.discovery.cache_misses",
            description="Discovery cache misses",
        )
        _cb_active_connections = _meter.create_up_down_counter(
            "sidecar.circuit_breaker.active_connections",
            description="Active connections per destination",
        )
        _cb_rejected_pool = _meter.create_counter(
            "sidecar.circuit_breaker.rejected_pool_exhausted",
            description="Requests rejected due to connection pool exhaustion",
        )
        _rate_limit_rejected = _meter.create_counter(
            "sidecar.rate_limit.rejected",
            description="Requests rejected by rate limiting",
        )

        _initialized = True
        logger.info("telemetry_initialized", service=config.service_name)

    except ImportError as e:
        logger.warning("telemetry_init_failed", error=str(e))
    except Exception as e:
        logger.warning("telemetry_init_error", error=str(e))


def instrument_flask(app: Any) -> None:
    """Instrument a Flask app with OpenTelemetry."""
    if not _initialized:
        return
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        FlaskInstrumentor().instrument_app(app)
    except Exception as e:
        logger.warning("flask_instrumentation_failed", error=str(e))


def instrument_httpx() -> None:
    """Instrument httpx with OpenTelemetry."""
    if not _initialized:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        logger.warning("httpx_instrumentation_failed", error=str(e))


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None):
    """Create a trace span as a context manager.

    If telemetry is disabled, yields a no-op context.
    """
    if not _initialized or not _tracer:
        yield None
        return

    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
        yield span


def record_request(direction: str, method: str, outcome: str) -> None:
    """Record a request metric."""
    if _request_counter:
        _request_counter.add(1, {
            "direction": direction,
            "method": method,
            "outcome": outcome,
        })


def record_request_duration(direction: str, method: str, duration: float) -> None:
    """Record request processing duration."""
    if _request_duration:
        _request_duration.record(duration, {
            "direction": direction,
            "method": method,
        })


def record_interceptor_decision(interceptor_name: str, action: str) -> None:
    """Record an interceptor decision."""
    if _interceptor_counter:
        _interceptor_counter.add(1, {
            "interceptor": interceptor_name,
            "action": action,
        })


def record_discovery_cache(hit: bool) -> None:
    """Record a discovery cache hit or miss."""
    if hit and _discovery_cache_hits:
        _discovery_cache_hits.add(1)
    elif not hit and _discovery_cache_misses:
        _discovery_cache_misses.add(1)


def record_pool_exhausted(destination: str) -> None:
    """Record a connection pool exhaustion rejection."""
    if _cb_rejected_pool:
        _cb_rejected_pool.add(1, {"destination": destination})


def record_active_connections(destination: str, delta: int) -> None:
    """Record a change in active connections (delta: +1 or -1)."""
    if _cb_active_connections:
        _cb_active_connections.add(delta, {"destination": destination})


def record_rate_limit_rejected(source_agent: str) -> None:
    """Record a rate limit rejection."""
    if _rate_limit_rejected:
        _rate_limit_rejected.add(1, {"source_agent": source_agent})


def generate_metrics_response() -> tuple[bytes, str]:
    """Generate Prometheus metrics output.

    Returns:
        Tuple of (body_bytes, content_type).
    """
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return generate_latest(), CONTENT_TYPE_LATEST
    except ImportError:
        return b"# prometheus_client not installed\n", "text/plain"


def get_trace_context_headers() -> dict[str, str]:
    """Get W3C Trace Context headers for outbound propagation."""
    if not _initialized:
        return {}
    try:
        from opentelemetry import context
        from opentelemetry.propagators import textmap
        from opentelemetry.propagate import inject

        headers: dict[str, str] = {}
        inject(headers)
        return headers
    except Exception:
        return {}


def extract_trace_context(headers: dict[str, str]) -> Any:
    """Extract trace context from inbound request headers."""
    if not _initialized:
        return None
    try:
        from opentelemetry.propagate import extract
        return extract(headers)
    except Exception:
        return None


def reset_telemetry() -> None:
    """Reset telemetry state. For testing only."""
    global _tracer, _meter, _initialized
    global _request_counter, _request_duration, _interceptor_counter
    global _discovery_cache_hits, _discovery_cache_misses

    global _cb_active_connections, _cb_rejected_pool, _rate_limit_rejected

    _tracer = None
    _meter = None
    _initialized = False
    _request_counter = None
    _request_duration = None
    _interceptor_counter = None
    _discovery_cache_hits = None
    _discovery_cache_misses = None
    _cb_active_connections = None
    _cb_rejected_pool = None
    _rate_limit_rejected = None
