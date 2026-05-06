"""Unit tests for ReasoningTracer flush pipeline — buffer, timer, error handling, close.

No live services required — tests buffer mechanics and error paths.
"""

import logging
import time

import pytest

from recursant.trace import ReasoningTracer, Span


class TestSpanLifecycle:
    """Test the Span class directly."""

    def test_span_constructor_sets_start_time(self):
        span = Span("tool_call", "test", "t1", "agent-a")
        assert span.start_time is not None
        assert span.end_time is None
        assert span.duration_ms is None

    def test_span_finish_sets_end_and_duration(self):
        span = Span("tool_call", "test", "t1", "agent-a")
        span._finish()
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_span_to_dict_required_fields(self):
        span = Span("decision", "approve", "t1", "agent-a")
        span._finish()
        d = span.to_dict()
        assert d["task_id"] == "t1"
        assert d["agent_name"] == "agent-a"
        assert d["span_type"] == "decision"
        assert d["span_name"] == "approve"
        assert "start_time" in d
        assert "end_time" in d

    def test_span_to_dict_excludes_none_optionals(self):
        span = Span("tool_call", "test", "t1", "agent-a")
        span._finish()
        d = span.to_dict()
        assert "input_data" not in d
        assert "output_data" not in d
        assert "parent_span_id" not in d
        assert "trace_id" not in d
        assert "metadata" not in d

    def test_span_to_dict_includes_set_fields(self):
        span = Span("tool_call", "test", "t1", "agent-a",
                     parent_span_id="parent-1", trace_id="trace-1")
        span.set_input({"x": 1})
        span.set_output({"y": 2})
        span.set_metadata({"env": "test"})
        span._finish()
        d = span.to_dict()
        assert d["input_data"] == {"x": 1}
        assert d["output_data"] == {"y": 2}
        assert d["metadata"] == {"env": "test"}
        assert d["parent_span_id"] == "parent-1"
        assert d["trace_id"] == "trace-1"


class TestAddSpan:
    """Test buffer append and threshold flush."""

    def test_add_span_appends_to_buffer(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        with tracer.tool_call("api_call", task_id="t1") as span:
            span.set_input({"q": "test"})
        assert len(tracer._buffer) == 1
        assert tracer._buffer[0]["span_type"] == "tool_call"

    def test_buffer_flush_at_threshold(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False, flush_size=2)
        with tracer.tool_call("call1", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        with tracer.tool_call("call2", task_id="t1"):
            pass
        # No backend → discarded on flush
        assert len(tracer._buffer) == 0

    def test_buffer_below_threshold_not_flushed(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False, flush_size=5)
        with tracer.tool_call("call1", task_id="t1"):
            pass
        with tracer.decision("dec1", task_id="t1"):
            pass
        assert len(tracer._buffer) == 2


class TestFlushNoBackend:
    """Test flush behavior with no backend configured."""

    def test_flush_discards_without_backend(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        with tracer.tool_call("call", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        tracer.flush()
        assert len(tracer._buffer) == 0

    def test_flush_empty_buffer_noop(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        tracer.flush()  # Should not raise
        assert len(tracer._buffer) == 0

    def test_flush_logs_discard_message(self, caplog):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        with tracer.tool_call("call", task_id="t1"):
            pass
        with caplog.at_level(logging.DEBUG, logger="recursant.trace"):
            tracer.flush()
        assert any("discarding" in r.message.lower() for r in caplog.records)


class TestFlushErrorHandling:
    """Test that flush errors are caught and logged, not propagated."""

    def test_flush_catches_connection_error(self):
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=False,
        )
        with tracer.tool_call("call", task_id="t1"):
            pass
        # Should not raise — error is caught in _do_flush
        tracer.flush()
        assert len(tracer._buffer) == 0

    def test_flush_logs_warning_on_error(self, caplog):
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=False,
        )
        with tracer.tool_call("call", task_id="t1"):
            pass
        with caplog.at_level(logging.WARNING, logger="recursant.trace"):
            tracer.flush()
        assert any("failed to flush" in r.message.lower() for r in caplog.records)

    def test_flush_clears_buffer_before_send(self):
        """Buffer is cleared before sending, even if send fails."""
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=False,
        )
        with tracer.tool_call("call", task_id="t1"):
            pass
        tracer.flush()
        assert len(tracer._buffer) == 0

    def test_multiple_flushes_independent(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        with tracer.tool_call("call1", task_id="t1"):
            pass
        tracer.flush()
        assert len(tracer._buffer) == 0

        with tracer.tool_call("call2", task_id="t2"):
            pass
        assert len(tracer._buffer) == 1
        tracer.flush()
        assert len(tracer._buffer) == 0


class TestTimer:
    """Test the periodic flush timer."""

    def test_timer_not_started_without_backend(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=True)
        assert tracer._timer is None

    def test_timer_started_with_backend(self):
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=True,
        )
        try:
            assert tracer._timer is not None
        finally:
            tracer.close()

    def test_timer_is_daemon(self):
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=True,
        )
        try:
            assert tracer._timer.daemon is True
        finally:
            tracer.close()

    def test_close_cancels_timer(self):
        tracer = ReasoningTracer(
            agent_name="test",
            sidecar_url="http://127.0.0.1:1",
            auto_flush=True,
        )
        timer = tracer._timer
        tracer.close()
        assert timer.finished.is_set()


class TestClose:
    """Test close() behavior."""

    def test_close_flushes_remaining(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        with tracer.tool_call("call", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        tracer.close()
        assert len(tracer._buffer) == 0

    def test_close_idempotent(self):
        tracer = ReasoningTracer(agent_name="test", auto_flush=False)
        tracer.close()
        tracer.close()  # Should not raise


class TestLogin:
    """Test _login() method directly."""

    def test_login_skips_without_credentials(self):
        tracer = ReasoningTracer(
            agent_name="test",
            registry_url="http://127.0.0.1:1",
            auto_flush=False,
        )
        tracer._login()
        assert tracer._token is None

    def test_login_skips_without_password(self):
        tracer = ReasoningTracer(
            agent_name="test",
            registry_url="http://127.0.0.1:1",
            username="admin",
            auto_flush=False,
        )
        tracer._login()
        assert tracer._token is None

    def test_login_bad_password_raises(self):
        """Login with wrong password raises — only works with a reachable host."""
        import httpx

        tracer = ReasoningTracer(
            agent_name="test",
            registry_url="http://127.0.0.1:1",
            username="admin",
            password="wrong",
            auto_flush=False,
        )
        with pytest.raises(httpx.ConnectError):
            tracer._login()
