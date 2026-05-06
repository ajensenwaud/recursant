"""Integration tests for the RecursantClient — real HTTP calls, no mocks.

Run inside the Kind cluster via kubectl exec against the running registry API.
"""

import os
import uuid

import httpx
import pytest

# Import from conftest helpers
from tests.conftest import get_password, get_registry_url, get_tenant_id, get_username

REGISTRY_URL = get_registry_url()
USERNAME = get_username()
PASSWORD = get_password()
TENANT = get_tenant_id()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestAuth:
    """Test JWT authentication flow."""

    def test_login_returns_token(self):
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 10

    def test_login_invalid_password(self):
        resp = httpx.post(
            f"{REGISTRY_URL}/v1/auth/login",
            json={"username": USERNAME, "password": "wrong-password"},
            timeout=10,
        )
        assert resp.status_code == 401


class TestSDKClient:
    """Test RecursantClient against the live registry API."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Set up a RecursantClient for each test."""
        # Import inside test to avoid module-level import failures
        from recursant.client import RecursantClient

        self.client = RecursantClient(
            REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        yield
        self.client.close()

    def _create_agent(self, name: str | None = None):
        """Helper to create a test agent."""
        agent_name = name or _unique("sdk-test-agent")
        return self.client.agents.create(
            name=agent_name,
            version="1.0.0",
            description="SDK integration test agent",
            owner_id="sdk-test",
            team_id="sdk-team",
            contact_email="sdk@test.example.com",
            classification="internal",
            data_sensitivity="none",
            risk_tier="low",
            endpoint={
                "type": "custom",
                "url": "http://test-agent:8001",
                "auth_method": "api_key",
                "timeout_ms": 30000,
                "agent_protocol": "A2A",
            },
            capabilities=[{"name": "test-cap", "description": "A test capability"}],
        )

    def test_create_agent(self):
        agent = self._create_agent()
        assert agent.id is not None
        assert agent.status == "draft"
        assert agent.classification == "internal"

    def test_get_agent(self):
        created = self._create_agent()
        fetched = self.client.agents.get(str(created.id))
        assert str(fetched.id) == str(created.id)
        assert fetched.name == created.name

    def test_list_agents(self):
        name = _unique("sdk-list-test")
        self._create_agent(name)
        result = self.client.agents.list(name=name)
        assert any(a.name == name for a in result.agents)

    def test_update_agent(self):
        created = self._create_agent()
        updated = self.client.agents.update(
            str(created.id),
            description="Updated description",
            version="1.0.1",
        )
        assert updated.description == "Updated description"

    def test_delete_agent(self):
        from recursant.exceptions import NotFoundError

        created = self._create_agent()
        self.client.agents.delete(str(created.id))
        # Soft-deleted agents return 404 on GET
        with pytest.raises(NotFoundError):
            self.client.agents.get(str(created.id))

    def test_submit_agent(self):
        created = self._create_agent()
        submitted = self.client.agents.submit(str(created.id))
        # Agent moves through governance pipeline; status may have progressed
        # past 'submitted' by the time we get the response
        assert submitted.status != "draft"


class TestSDKDeploy:
    """Test the deploy() workflow."""

    def test_deploy_creates_agent(self):
        from recursant.agent import Agent
        from recursant.deploy import deploy

        agent = Agent(
            name=_unique("sdk-deploy-test"),
            version="1.0.0",
            endpoint_url="http://test-agent:8001",
            endpoint_type="custom",
            description="Deploy workflow test",
        )
        result = deploy(
            agent,
            REGISTRY_URL,
            submit=False,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        assert result.created is True
        assert result.agent.id is not None

    def test_deploy_idempotent(self):
        from recursant.agent import Agent
        from recursant.deploy import deploy

        name = _unique("sdk-idempotent")
        agent = Agent(
            name=name,
            version="1.0.0",
            endpoint_url="http://test-agent:8001",
            endpoint_type="custom",
            description="Idempotency test",
        )
        auth = dict(username=USERNAME, password=PASSWORD, tenant_id=TENANT)

        r1 = deploy(agent, REGISTRY_URL, submit=False, **auth)
        assert r1.created is True

        r2 = deploy(agent, REGISTRY_URL, submit=False, **auth)
        assert r2.updated is True
        assert str(r2.agent.id) == str(r1.agent.id)


class TestConfigLoader:
    """Test config loading and validation."""

    def test_load_valid_agent_config(self, tmp_path):
        from recursant.config import load_config, AgentConfig

        cfg_file = tmp_path / "recursant.yaml"
        cfg_file.write_text("""
apiVersion: recursant/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
spec:
  classification: internal
  data_sensitivity: none
  risk_tier: low
  description: A test agent
  endpoint:
    url: http://localhost:8001
    type: custom
    auth_method: api_key
  capabilities:
    - name: default
      description: Default capability
""")
        cfg = load_config(str(cfg_file))
        assert isinstance(cfg, AgentConfig)
        assert cfg.metadata.name == "test-agent"

    def test_load_valid_registry_config(self, tmp_path):
        from recursant.config import load_config, RegistryConfig

        cfg_file = tmp_path / "registry-config.yaml"
        cfg_file.write_text("""
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
guardrails:
  - name: pii-detector
    type: pre_processing
    mechanism: regex
    enforcement: block
mesh_policies:
  - source: agent-a
    destination: agent-b
    action: allow
""")
        cfg = load_config(str(cfg_file))
        assert isinstance(cfg, RegistryConfig)
        assert len(cfg.guardrails) == 1
        assert len(cfg.mesh_policies) == 1

    def test_validate_invalid_config(self, tmp_path):
        from recursant.config import validate_config

        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("kind: Unknown\n")
        errors = validate_config(str(cfg_file))
        assert len(errors) > 0

    def test_validate_missing_file(self):
        from recursant.config import validate_config

        errors = validate_config("/nonexistent/file.yaml")
        assert len(errors) > 0


class TestClientErrorHandling:
    """Test SDK exception mapping for error responses."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from recursant.client import RecursantClient

        self.client = RecursantClient(
            REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        yield
        self.client.close()

    def test_get_nonexistent_agent_raises_not_found(self):
        from recursant.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            self.client.agents.get("00000000-0000-0000-0000-000000000000")

    def test_create_duplicate_name_raises_conflict(self):
        from recursant.exceptions import ConflictError

        name = _unique("dup-test")
        # Create first agent
        self.client.agents.create(
            name=name,
            version="1.0.0",
            description="First",
            owner_id="test",
            team_id="test",
            contact_email="t@t.com",
            classification="internal",
            data_sensitivity="none",
            risk_tier="low",
            endpoint={
                "type": "custom",
                "url": "http://test:8001",
                "auth_method": "api_key",
                "timeout_ms": 30000,
                "agent_protocol": "A2A",
            },
            capabilities=[{"name": "default", "description": "d"}],
        )
        # Creating same name again should raise ConflictError
        with pytest.raises(ConflictError):
            self.client.agents.create(
                name=name,
                version="1.0.0",
                description="Duplicate",
                owner_id="test",
                team_id="test",
                contact_email="t@t.com",
                classification="internal",
                data_sensitivity="none",
                risk_tier="low",
                endpoint={
                    "type": "custom",
                    "url": "http://test:8001",
                    "auth_method": "api_key",
                    "timeout_ms": 30000,
                    "agent_protocol": "A2A",
                },
                capabilities=[{"name": "default", "description": "d"}],
            )

    def test_wrong_password_raises_auth_error(self):
        from recursant.client import RecursantClient
        from recursant.exceptions import AuthError

        bad_client = RecursantClient(
            REGISTRY_URL,
            username=USERNAME,
            password="definitely-wrong-password",
            tenant_id=TENANT,
        )
        with pytest.raises(AuthError):
            bad_client.agents.list()
        bad_client.close()

    def test_auto_login_on_first_request(self):
        """Client should automatically log in on first API call (lazy auth)."""
        from recursant.client import RecursantClient

        c = RecursantClient(
            REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        # No explicit login — first request triggers it
        result = c.agents.list()
        assert result is not None
        c.close()


class TestDeployWithSubmit:
    """Test the deploy() workflow with submit flag variations."""

    def test_deploy_with_submit_true(self):
        from recursant.agent import Agent
        from recursant.deploy import deploy

        agent = Agent(
            name=_unique("deploy-submit"),
            version="1.0.0",
            endpoint_url="http://test-agent:8001",
            endpoint_type="custom",
            description="Deploy with submit test",
        )
        result = deploy(
            agent,
            REGISTRY_URL,
            submit=True,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        assert result.created is True
        assert result.submitted is True
        assert result.agent.status != "draft"

    def test_deploy_with_submit_false(self):
        from recursant.agent import Agent
        from recursant.deploy import deploy

        agent = Agent(
            name=_unique("deploy-nosubmit"),
            version="1.0.0",
            endpoint_url="http://test-agent:8001",
            endpoint_type="custom",
            description="Deploy without submit test",
        )
        result = deploy(
            agent,
            REGISTRY_URL,
            submit=False,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        assert result.created is True
        assert result.submitted is False
        assert result.agent.status == "draft"


class TestReasoningSpans:
    """Test reasoning span submission and retrieval."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from recursant.client import RecursantClient

        self.client = RecursantClient(
            REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
        )
        yield
        self.client.close()

    def test_submit_and_retrieve_spans(self):
        task_id = f"trace-test-{uuid.uuid4().hex[:8]}"
        spans = [
            {
                "task_id": task_id,
                "agent_name": "test-agent",
                "span_type": "tool_call",
                "span_name": "credit_check_api",
                "start_time": "2026-02-28T10:00:00Z",
                "end_time": "2026-02-28T10:00:01.2Z",
                "duration_ms": 1200,
                "input_data": {"applicant_id": "123"},
                "output_data": {"score": 720},
            },
            {
                "task_id": task_id,
                "agent_name": "test-agent",
                "span_type": "decision",
                "span_name": "approve_loan",
                "start_time": "2026-02-28T10:00:01.5Z",
                "end_time": "2026-02-28T10:00:01.7Z",
                "duration_ms": 200,
                "input_data": {"score": 720, "threshold": 650},
                "output_data": {"approved": True},
            },
        ]

        result = self.client.observability.submit_spans(spans)
        assert result.get("created") == 2

        # Retrieve spans
        retrieved = self.client.observability.get_trace_spans(task_id)
        assert len(retrieved) == 2
        assert retrieved[0].span_type == "tool_call"
        assert retrieved[1].span_type == "decision"


class TestTraceSDK:
    """Test the ReasoningTracer SDK."""

    def test_tracer_context_managers(self):
        """Test that the tracer captures spans correctly (local buffer, no backend)."""
        from recursant.trace import ReasoningTracer

        tracer = ReasoningTracer(agent_name="test-agent", auto_flush=False)

        with tracer.tool_call("api_call", task_id="t1") as span:
            span.set_input({"query": "test"})
            span.set_output({"result": "ok"})

        with tracer.decision("decide", task_id="t1") as span:
            span.set_input({"score": 100})
            span.set_output({"approved": True})

        assert len(tracer._buffer) == 2
        assert tracer._buffer[0]["span_type"] == "tool_call"
        assert tracer._buffer[1]["span_type"] == "decision"
        assert tracer._buffer[0]["input_data"] == {"query": "test"}

    def test_tracer_decorator(self):
        """Test the @tracer.trace decorator."""
        from recursant.trace import ReasoningTracer

        tracer = ReasoningTracer(agent_name="test-agent", auto_flush=False)

        @tracer.trace("retrieval", name="fetch_docs")
        def fetch_docs(query: str, task_id: str = ""):
            return ["doc1", "doc2"]

        result = fetch_docs("test query", task_id="t2")
        assert result == ["doc1", "doc2"]
        assert len(tracer._buffer) == 1
        assert tracer._buffer[0]["span_name"] == "fetch_docs"

    def test_tracer_flush_to_registry(self):
        """Test that the tracer can flush spans to the real registry API."""
        from recursant.trace import ReasoningTracer

        task_id = f"tracer-flush-{uuid.uuid4().hex[:8]}"
        tracer = ReasoningTracer(
            agent_name="tracer-test-agent",
            registry_url=REGISTRY_URL,
            username=USERNAME,
            password=PASSWORD,
            tenant_id=TENANT,
            auto_flush=False,
        )

        with tracer.tool_call("api_call", task_id=task_id) as span:
            span.set_input({"x": 1})
            span.set_output({"y": 2})

        tracer.flush()

        # Verify via SDK client
        from recursant.client import RecursantClient

        client = RecursantClient(
            REGISTRY_URL, username=USERNAME, password=PASSWORD, tenant_id=TENANT
        )
        spans = client.observability.get_trace_spans(task_id)
        client.close()
        assert len(spans) >= 1
        assert spans[0].span_name == "api_call"
