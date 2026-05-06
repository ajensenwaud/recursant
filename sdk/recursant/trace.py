"""Reasoning trace SDK — context managers and decorator for capturing agent reasoning spans."""

from __future__ import annotations

import functools
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)


class Span:
    """A single reasoning span being recorded."""

    def __init__(
        self,
        span_type: str,
        span_name: str,
        task_id: str,
        agent_name: str,
        parent_span_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.span_type = span_type
        self.span_name = span_name
        self.task_id = task_id
        self.agent_name = agent_name
        self.parent_span_id = parent_span_id
        self.trace_id = trace_id
        self.input_data: dict[str, Any] | None = None
        self.output_data: dict[str, Any] | None = None
        self.metadata: dict[str, Any] | None = None
        self.start_time: datetime = datetime.now(timezone.utc)
        self.end_time: datetime | None = None
        self.duration_ms: float | None = None

    def set_input(self, data: dict[str, Any]) -> None:
        self.input_data = data

    def set_output(self, data: dict[str, Any]) -> None:
        self.output_data = data

    def set_metadata(self, data: dict[str, Any]) -> None:
        self.metadata = data

    def _finish(self) -> None:
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "span_type": self.span_type,
            "span_name": self.span_name,
            "start_time": self.start_time.isoformat(),
        }
        if self.end_time:
            d["end_time"] = self.end_time.isoformat()
        if self.duration_ms is not None:
            d["duration_ms"] = round(self.duration_ms, 2)
        if self.input_data is not None:
            d["input_data"] = self.input_data
        if self.output_data is not None:
            d["output_data"] = self.output_data
        if self.parent_span_id:
            d["parent_span_id"] = self.parent_span_id
        if self.trace_id:
            d["trace_id"] = self.trace_id
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class ReasoningTracer:
    """Captures reasoning spans and flushes them to a sidecar or registry.

    Usage::

        tracer = ReasoningTracer(
            agent_name="loan-analyzer",
            sidecar_url="http://localhost:9901",
        )

        with tracer.tool_call("credit_check_api", task_id="task-123") as span:
            result = call_credit_api(applicant_id)
            span.set_output(result)

        # Decorator form
        @tracer.trace("retrieval", name="fetch_documents")
        def fetch_documents(query: str, task_id: str = "") -> list:
            ...
    """

    def __init__(
        self,
        agent_name: str = "",
        *,
        sidecar_url: str | None = None,
        registry_url: str | None = None,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        tenant_id: str = "default",
        flush_interval: float = 1.0,
        flush_size: int = 10,
        auto_flush: bool = True,
    ):
        self.agent_name = agent_name
        self._sidecar_url = sidecar_url
        self._registry_url = registry_url
        self._api_key = api_key
        self._username = username
        self._password = password
        self._tenant_id = tenant_id
        self._flush_interval = flush_interval
        self._flush_size = flush_size

        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._token: str | None = None
        self._timer: threading.Timer | None = None

        if auto_flush and (sidecar_url or registry_url):
            self._schedule_flush()

    def _schedule_flush(self) -> None:
        self._timer = threading.Timer(self._flush_interval, self._periodic_flush)
        self._timer.daemon = True
        self._timer.start()

    def _periodic_flush(self) -> None:
        self.flush()
        if self._sidecar_url or self._registry_url:
            self._schedule_flush()

    # ── Context managers ─────────────────────────────────────────────

    @contextmanager
    def tool_call(self, name: str, task_id: str, **kwargs: Any):
        """Context manager for a tool_call span."""
        span = Span("tool_call", name, task_id, self.agent_name, **kwargs)
        try:
            yield span
        finally:
            span._finish()
            self._add_span(span)

    @contextmanager
    def decision(self, name: str, task_id: str, **kwargs: Any):
        """Context manager for a decision span."""
        span = Span("decision", name, task_id, self.agent_name, **kwargs)
        try:
            yield span
        finally:
            span._finish()
            self._add_span(span)

    @contextmanager
    def observation(self, name: str, task_id: str, **kwargs: Any):
        """Context manager for an observation span."""
        span = Span("observation", name, task_id, self.agent_name, **kwargs)
        try:
            yield span
        finally:
            span._finish()
            self._add_span(span)

    @contextmanager
    def thought(self, name: str, task_id: str, **kwargs: Any):
        """Context manager for a thought span."""
        span = Span("thought", name, task_id, self.agent_name, **kwargs)
        try:
            yield span
        finally:
            span._finish()
            self._add_span(span)

    @contextmanager
    def retrieval(self, name: str, task_id: str, **kwargs: Any):
        """Context manager for a retrieval span."""
        span = Span("retrieval", name, task_id, self.agent_name, **kwargs)
        try:
            yield span
        finally:
            span._finish()
            self._add_span(span)

    # ── Decorator ────────────────────────────────────────────────────

    def trace(
        self, span_type: str, *, name: str | None = None
    ) -> Callable:
        """Decorator that wraps a function in a reasoning span.

        The decorated function must accept a `task_id` keyword argument.
        """

        def decorator(fn: Callable) -> Callable:
            span_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                task_id = kwargs.get("task_id", "unknown")
                span = Span(span_type, span_name, task_id, self.agent_name)
                span.set_input({"args": str(args), "kwargs": {k: str(v) for k, v in kwargs.items()}})
                try:
                    result = fn(*args, **kwargs)
                    span.set_output({"result": str(result)})
                    return result
                finally:
                    span._finish()
                    self._add_span(span)

            return wrapper

        return decorator

    # ── Buffer management ────────────────────────────────────────────

    def _add_span(self, span: Span) -> None:
        with self._lock:
            self._buffer.append(span.to_dict())
            if len(self._buffer) >= self._flush_size:
                self._do_flush()

    def flush(self) -> None:
        """Flush buffered spans to the backend."""
        with self._lock:
            self._do_flush()

    def _do_flush(self) -> None:
        """Send buffered spans (must hold self._lock)."""
        if not self._buffer:
            return

        spans = self._buffer[:]
        self._buffer.clear()

        try:
            if self._sidecar_url:
                self._send_to_sidecar(spans)
            elif self._registry_url:
                self._send_to_registry(spans)
            else:
                logger.debug("No backend configured, discarding %d spans", len(spans))
        except Exception as exc:
            logger.warning("Failed to flush %d spans: %s", len(spans), exc)

    def _send_to_sidecar(self, spans: list[dict[str, Any]]) -> None:
        resp = httpx.post(
            f"{self._sidecar_url}/traces/spans",
            json={"spans": spans},
            timeout=5.0,
        )
        resp.raise_for_status()

    def _send_to_registry(self, spans: list[dict[str, Any]]) -> None:
        headers: dict[str, str] = {"X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["X-Mesh-API-Key"] = self._api_key
        else:
            if not self._token:
                self._login()
            headers["Authorization"] = f"Bearer {self._token}"

        resp = httpx.post(
            f"{self._registry_url}/v1/mesh/traces/spans",
            json={"spans": spans},
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 401 and self._username:
            self._login()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = httpx.post(
                f"{self._registry_url}/v1/mesh/traces/spans",
                json={"spans": spans},
                headers=headers,
                timeout=10.0,
            )
        resp.raise_for_status()

    def _login(self) -> None:
        if not self._username or not self._password:
            return
        resp = httpx.post(
            f"{self._registry_url}/v1/auth/login",
            json={"username": self._username, "password": self._password},
            timeout=10.0,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]

    def close(self) -> None:
        """Flush remaining spans and stop the timer."""
        if self._timer:
            self._timer.cancel()
        self.flush()
