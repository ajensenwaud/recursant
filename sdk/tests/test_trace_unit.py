"""Unit tests for the ReasoningTracer — span lifecycle, buffer, context managers, decorator."""

import time

from recursant.trace import ReasoningTracer, Span


class TestSpan:
    def test_constructor_sets_start_time(self):
        span = Span("tool_call", "api_call", "t1", "agent-a")
        assert span.start_time is not None
        assert span.end_time is None
        assert span.duration_ms is None
        assert span.span_type == "tool_call"
        assert span.span_name == "api_call"
        assert span.task_id == "t1"
        assert span.agent_name == "agent-a"

    def test_finish_sets_end_time_and_duration(self):
        span = Span("tool_call", "api", "t1", "agent")
        time.sleep(0.01)
        span._finish()
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms > 0

    def test_set_input_output_metadata(self):
        span = Span("tool_call", "api", "t1", "agent")
        span.set_input({"x": 1})
        span.set_output({"y": 2})
        span.set_metadata({"model": "gpt-4"})
        assert span.input_data == {"x": 1}
        assert span.output_data == {"y": 2}
        assert span.metadata == {"model": "gpt-4"}

    def test_to_dict_required_fields(self):
        span = Span("thought", "plan", "t1", "agent")
        d = span.to_dict()
        assert d["task_id"] == "t1"
        assert d["agent_name"] == "agent"
        assert d["span_type"] == "thought"
        assert d["span_name"] == "plan"
        assert "start_time" in d

    def test_to_dict_excludes_none_optional_fields(self):
        span = Span("tool_call", "api", "t1", "agent")
        d = span.to_dict()
        assert "input_data" not in d
        assert "output_data" not in d
        assert "metadata" not in d
        assert "parent_span_id" not in d
        assert "trace_id" not in d
        assert "end_time" not in d
        assert "duration_ms" not in d

    def test_to_dict_includes_present_optional_fields(self):
        span = Span("tool_call", "api", "t1", "agent",
                     parent_span_id="p1", trace_id="tr1")
        span.set_input({"x": 1})
        span.set_output({"y": 2})
        span.set_metadata({"k": "v"})
        span._finish()
        d = span.to_dict()
        assert "end_time" in d
        assert "duration_ms" in d
        assert d["input_data"] == {"x": 1}
        assert d["output_data"] == {"y": 2}
        assert d["metadata"] == {"k": "v"}
        assert d["parent_span_id"] == "p1"
        assert d["trace_id"] == "tr1"

    def test_to_dict_duration_rounded(self):
        span = Span("tool_call", "api", "t1", "agent")
        time.sleep(0.005)
        span._finish()
        d = span.to_dict()
        # duration_ms should be rounded to 2 decimal places
        assert d["duration_ms"] == round(d["duration_ms"], 2)


class TestReasoningTracerContextManagers:
    def test_tool_call(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("api_call", task_id="t1") as span:
            span.set_output({"r": 1})
        assert len(tracer._buffer) == 1
        assert tracer._buffer[0]["span_type"] == "tool_call"
        assert tracer._buffer[0]["span_name"] == "api_call"

    def test_decision(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.decision("approve", task_id="t1") as span:
            span.set_output({"approved": True})
        assert tracer._buffer[0]["span_type"] == "decision"

    def test_observation(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.observation("note", task_id="t1") as span:
            span.set_output({"note": "ok"})
        assert tracer._buffer[0]["span_type"] == "observation"

    def test_thought(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.thought("reasoning", task_id="t1") as span:
            span.set_output({"thought": "thinking"})
        assert tracer._buffer[0]["span_type"] == "thought"

    def test_retrieval(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.retrieval("fetch_docs", task_id="t1") as span:
            span.set_output({"docs": ["d1"]})
        assert tracer._buffer[0]["span_type"] == "retrieval"

    def test_context_manager_sets_timing(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("x", task_id="t1"):
            pass
        assert "end_time" in tracer._buffer[0]
        assert "duration_ms" in tracer._buffer[0]

    def test_context_manager_with_kwargs(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("x", task_id="t1",
                              parent_span_id="p1", trace_id="tr1"):
            pass
        assert tracer._buffer[0]["parent_span_id"] == "p1"
        assert tracer._buffer[0]["trace_id"] == "tr1"

    def test_input_output_captured(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("x", task_id="t1") as span:
            span.set_input({"query": "test"})
            span.set_output({"result": "ok"})
        assert tracer._buffer[0]["input_data"] == {"query": "test"}
        assert tracer._buffer[0]["output_data"] == {"result": "ok"}


class TestReasoningTracerDecorator:
    def test_decorator_preserves_return_value(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)

        @tracer.trace("retrieval", name="fetch")
        def fetch(task_id=""):
            return [1, 2, 3]

        result = fetch(task_id="t1")
        assert result == [1, 2, 3]

    def test_decorator_uses_function_name_as_default(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)

        @tracer.trace("tool_call")
        def my_function(task_id=""):
            return "ok"

        my_function(task_id="t1")
        assert tracer._buffer[0]["span_name"] == "my_function"

    def test_decorator_uses_explicit_name(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)

        @tracer.trace("tool_call", name="custom_name")
        def my_function(task_id=""):
            return "ok"

        my_function(task_id="t1")
        assert tracer._buffer[0]["span_name"] == "custom_name"

    def test_decorator_captures_input_output(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)

        @tracer.trace("tool_call")
        def fn(x, task_id=""):
            return x * 2

        fn(42, task_id="t1")
        assert "input_data" in tracer._buffer[0]
        assert "output_data" in tracer._buffer[0]

    def test_decorator_default_task_id(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)

        @tracer.trace("tool_call")
        def fn():
            return "ok"

        fn()
        assert tracer._buffer[0]["task_id"] == "unknown"


class TestReasoningTracerBuffer:
    def test_buffer_accumulates(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        for i in range(3):
            with tracer.tool_call(f"call-{i}", task_id="t1"):
                pass
        assert len(tracer._buffer) == 3

    def test_flush_clears_buffer_no_backend(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("x", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        tracer.flush()
        assert len(tracer._buffer) == 0

    def test_auto_flush_at_flush_size(self):
        # flush_size=2, no backend → spans get discarded on flush
        tracer = ReasoningTracer(agent_name="a", flush_size=2, auto_flush=False)
        with tracer.tool_call("x", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        with tracer.tool_call("y", task_id="t1"):
            pass
        # Buffer should have been flushed (cleared) when reaching flush_size
        assert len(tracer._buffer) == 0

    def test_close_flushes_buffer(self):
        tracer = ReasoningTracer(agent_name="a", auto_flush=False)
        with tracer.tool_call("x", task_id="t1"):
            pass
        assert len(tracer._buffer) == 1
        tracer.close()
        assert len(tracer._buffer) == 0
