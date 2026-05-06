"""Integration tests for ReasoningTracer flush to registry — real HTTP calls.

Run inside the Kind cluster via kubectl exec.
"""

import uuid

import pytest

from recursant.client import RecursantClient
from recursant.trace import ReasoningTracer
from tests.conftest import (
    get_mesh_api_key,
    get_password,
    get_registry_url,
    get_tenant_id,
    get_username,
)

REGISTRY_URL = get_registry_url()
USERNAME = get_username()
PASSWORD = get_password()
TENANT = get_tenant_id()
MESH_API_KEY = get_mesh_api_key()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_client():
    return RecursantClient(
        REGISTRY_URL, username=USERNAME, password=PASSWORD, tenant_id=TENANT
    )


@pytest.mark.integration
class TestTracerFlushToRegistry:
    """Test tracer flush to the real registry and verify via SDK client."""

    def test_flush_jwt_auth(self):
        task_id = _unique("flush-jwt")
        tracer = ReasoningTracer(
            agent_name="tracer-jwt-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("jwt_call", task_id=task_id) as span:
            span.set_input({"x": 1})
            span.set_output({"y": 2})
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        assert spans[0].span_name == "jwt_call"

    def test_flush_api_key_auth(self):
        task_id = _unique("flush-apikey")
        tracer = ReasoningTracer(
            agent_name="tracer-apikey-test",
            registry_url=REGISTRY_URL,
            api_key=MESH_API_KEY,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("apikey_call", task_id=task_id) as span:
            span.set_input({"q": "test"})
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        assert spans[0].span_name == "apikey_call"

    def test_flush_multiple_spans(self):
        task_id = _unique("flush-multi")
        tracer = ReasoningTracer(
            agent_name="tracer-multi-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        for i in range(3):
            with tracer.tool_call(f"call_{i}", task_id=task_id) as span:
                span.set_input({"i": i})
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) == 3

    def test_flush_different_span_types(self):
        task_id = _unique("flush-types")
        tracer = ReasoningTracer(
            agent_name="tracer-types-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("api_call", task_id=task_id):
            pass
        with tracer.decision("approve", task_id=task_id):
            pass
        with tracer.observation("observe", task_id=task_id):
            pass
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        types = {s.span_type for s in spans}
        assert "tool_call" in types
        assert "decision" in types
        assert "observation" in types

    def test_flush_with_metadata(self):
        task_id = _unique("flush-meta")
        tracer = ReasoningTracer(
            agent_name="tracer-meta-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("meta_call", task_id=task_id,
                              trace_id="trace-abc") as span:
            span.set_input({"nested": {"key": "value"}})
            span.set_output({"result": [1, 2, 3]})
            span.set_metadata({"env": "test", "version": "1.0"})
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        s = spans[0]
        assert s.input_data == {"nested": {"key": "value"}}
        assert s.output_data == {"result": [1, 2, 3]}

    def test_auto_flush_on_close(self):
        task_id = _unique("flush-close")
        tracer = ReasoningTracer(
            agent_name="tracer-close-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("close_call", task_id=task_id) as span:
            span.set_input({"action": "close"})
        # Don't call flush() — close() should flush
        tracer.close()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        assert spans[0].span_name == "close_call"


@pytest.mark.integration
class TestTracerPerAgentTraceability:
    """Test per-agent trace isolation and data integrity."""

    def test_spans_isolated_by_task_id(self):
        task_a = _unique("task-a")
        task_b = _unique("task-b")
        tracer = ReasoningTracer(
            agent_name="isolation-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("call_a", task_id=task_a):
            pass
        with tracer.tool_call("call_b", task_id=task_b):
            pass
        tracer.flush()

        client = _make_client()
        spans_a = client.observability.get_trace_spans(task_a)
        spans_b = client.observability.get_trace_spans(task_b)
        client.close()

        assert len(spans_a) == 1
        assert spans_a[0].span_name == "call_a"
        assert len(spans_b) == 1
        assert spans_b[0].span_name == "call_b"

    def test_spans_from_different_agents_same_task(self):
        task_id = _unique("shared-task")

        for agent_name in ["agent-alpha", "agent-beta"]:
            tracer = ReasoningTracer(
                agent_name=agent_name,
                registry_url=REGISTRY_URL,
                username=USERNAME,
                password=PASSWORD,
                tenant_id=TENANT,
                auto_flush=False,
            )
            with tracer.tool_call(f"{agent_name}_call", task_id=task_id):
                pass
            tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()

        agent_names = {s.agent_name for s in spans}
        assert "agent-alpha" in agent_names
        assert "agent-beta" in agent_names

    def test_reasoning_spans_retrievable_via_get_trace_spans(self):
        task_id = _unique("trace-spans")
        tracer = ReasoningTracer(
            agent_name="trace-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("check_credit", task_id=task_id) as span:
            span.set_input({"applicant": "123"})
            span.set_output({"score": 720})
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        assert spans[0].span_name == "check_credit"
        assert spans[0].input_data == {"applicant": "123"}
        assert spans[0].output_data == {"score": 720}

    def test_input_output_data_preserved(self):
        task_id = _unique("data-round")
        complex_input = {
            "applicant": {"name": "John", "age": 30},
            "amounts": [1000, 2000, 3000],
            "flags": {"verified": True, "score": None},
        }
        complex_output = {
            "decision": "approved",
            "details": {"rate": 3.5, "term_months": 360},
        }

        tracer = ReasoningTracer(
            agent_name="data-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.decision("loan_decision", task_id=task_id) as span:
            span.set_input(complex_input)
            span.set_output(complex_output)
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        s = spans[0]
        assert s.input_data == complex_input
        assert s.output_data == complex_output

    def test_duration_ms_preserved(self):
        task_id = _unique("duration")
        tracer = ReasoningTracer(
            agent_name="dur-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("slow_call", task_id=task_id):
            pass
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        # duration_ms should be set (auto-calculated from start/end)
        assert spans[0].duration_ms is not None
        assert spans[0].duration_ms >= 0

    def test_span_ordering(self):
        task_id = _unique("ordering")
        tracer = ReasoningTracer(
            agent_name="order-test",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )
        with tracer.tool_call("first", task_id=task_id):
            pass
        with tracer.decision("second", task_id=task_id):
            pass
        with tracer.observation("third", task_id=task_id):
            pass
        tracer.flush()

        client = _make_client()
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) == 3
        names = [s.span_name for s in spans]
        assert names == ["first", "second", "third"]
