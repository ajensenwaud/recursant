"""Unit tests for Pydantic models in client/_models.py."""

import uuid

import pytest
from pydantic import ValidationError

from recursant.client._models import (
    AgentCreateRequest,
    AgentListItem,
    AgentResponse,
    AgentStatus,
    AgentUpdateRequest,
    AuthMethod,
    CapabilityRequest,
    Classification,
    ComplianceRuleCreateRequest,
    CostSummaryResponse,
    DataSensitivity,
    EndpointRequest,
    EndpointType,
    GuardrailCreateRequest,
    PaginatedAgents,
    PolicyCreateRequest,
    ReasoningSpanRequest,
    ReasoningSpanResponse,
    RiskTier,
)


class TestEnums:
    def test_agent_status_members(self):
        expected = {
            "draft", "submitted", "testing", "evaluating",
            "security_failed", "evaluation_failed", "pending_approval",
            "approved", "rejected", "active", "suspended", "decommissioned",
        }
        assert {s.value for s in AgentStatus} == expected

    def test_classification_members(self):
        expected = {"internal", "confidential", "restricted", "public"}
        assert {c.value for c in Classification} == expected

    def test_data_sensitivity_members(self):
        expected = {"none", "pii", "phi", "financial", "secret"}
        assert {d.value for d in DataSensitivity} == expected

    def test_risk_tier_members(self):
        expected = {"low", "medium", "high", "critical"}
        assert {r.value for r in RiskTier} == expected

    def test_endpoint_type_members(self):
        expected = {"langchain", "crewai", "langgraph", "agentforce", "databricks", "openai", "custom"}
        assert {e.value for e in EndpointType} == expected

    def test_auth_method_members(self):
        expected = {"mtls", "oauth2", "api_key", "iam"}
        assert {a.value for a in AuthMethod} == expected


class TestAgentCreateRequest:
    def test_valid_construction(self):
        req = AgentCreateRequest(
            name="test-agent",
            version="1.0.0",
            description="A test agent",
            owner_id="test-owner",
            team_id="test-team",
            contact_email="test@example.com",
            classification="internal",
            data_sensitivity="none",
            risk_tier="low",
            capabilities=[CapabilityRequest(name="cap", description="desc")],
            endpoint=EndpointRequest(type="custom", url="http://localhost:8001", auth_method="api_key"),
        )
        assert req.name == "test-agent"
        assert req.tenant_id == "default"

    def test_missing_required_name(self):
        with pytest.raises(ValidationError):
            AgentCreateRequest(
                version="1.0.0",
                description="d",
                owner_id="o",
                team_id="t",
                contact_email="e@e.com",
                classification="internal",
                data_sensitivity="none",
                risk_tier="low",
                capabilities=[],
                endpoint=EndpointRequest(type="custom", url="http://x", auth_method="api_key"),
            )

    def test_missing_required_endpoint(self):
        with pytest.raises(ValidationError):
            AgentCreateRequest(
                name="x",
                version="1.0.0",
                description="d",
                owner_id="o",
                team_id="t",
                contact_email="e@e.com",
                classification="internal",
                data_sensitivity="none",
                risk_tier="low",
                capabilities=[],
            )

    def test_optional_fields_default(self):
        req = AgentCreateRequest(
            name="x",
            version="1.0.0",
            description="d",
            owner_id="o",
            team_id="t",
            contact_email="e@e.com",
            classification="internal",
            data_sensitivity="none",
            risk_tier="low",
            capabilities=[],
            endpoint=EndpointRequest(type="custom", url="http://x", auth_method="api_key"),
        )
        assert req.tools == []
        assert req.upstream_agents == []
        assert req.downstream_agents == []
        assert req.guardrail_profile_id is None
        assert req.execution_graph_id is None
        assert req.resource_quota is None
        assert req.tenant_id == "default"


class TestAgentUpdateRequest:
    def test_empty_construction(self):
        req = AgentUpdateRequest()
        assert req.name is None
        assert req.version is None
        assert req.description is None

    def test_partial_update(self):
        req = AgentUpdateRequest(description="new desc", version="2.0.0")
        assert req.description == "new desc"
        assert req.version == "2.0.0"
        assert req.name is None


class TestAgentResponse:
    def test_extra_fields_allowed(self):
        resp = AgentResponse(
            id=uuid.uuid4(),
            name="a",
            version="1.0",
            description="d",
            status="draft",
            classification="internal",
            custom_field="custom_value",
        )
        assert resp.custom_field == "custom_value"

    def test_required_fields(self):
        uid = uuid.uuid4()
        resp = AgentResponse(
            id=uid,
            name="test",
            version="1.0.0",
            description="desc",
            status="draft",
            classification="internal",
        )
        assert resp.id == uid
        assert resp.status == "draft"


class TestPaginatedAgents:
    def test_empty_defaults(self):
        p = PaginatedAgents()
        assert p.agents == []
        assert p.pagination == {}

    def test_with_agents(self):
        uid = uuid.uuid4()
        p = PaginatedAgents(
            agents=[AgentListItem(
                id=uid,
                name="a",
                version="1",
                description="d",
                status="draft",
                classification="internal",
            )],
            pagination={"page": 1, "total": 1},
        )
        assert len(p.agents) == 1
        assert p.pagination["total"] == 1


class TestReasoningSpanRequest:
    def test_valid_construction(self):
        req = ReasoningSpanRequest(
            task_id="t1",
            agent_name="agent-a",
            span_type="tool_call",
            span_name="credit_check",
            start_time="2026-02-28T10:00:00Z",
        )
        assert req.task_id == "t1"
        assert req.span_type == "tool_call"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ReasoningSpanRequest(
                agent_name="a",
                span_type="tool_call",
                span_name="s",
                start_time="2026-02-28T10:00:00Z",
            )

    def test_optional_fields_default_to_none(self):
        req = ReasoningSpanRequest(
            task_id="t1",
            agent_name="a",
            span_type="tool_call",
            span_name="s",
            start_time="2026-02-28T10:00:00Z",
        )
        assert req.input_data is None
        assert req.output_data is None
        assert req.end_time is None
        assert req.duration_ms is None
        assert req.parent_span_id is None
        assert req.trace_id is None
        assert req.metadata is None


class TestOtherModels:
    def test_guardrail_create_request(self):
        req = GuardrailCreateRequest(
            name="test-gr",
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="block",
        )
        assert req.name == "test-gr"
        assert req.enforcement_mode == "block"
        assert req.scope is None
        assert req.priority is None

    def test_policy_create_request(self):
        req = PolicyCreateRequest(
            source_agent_name="src",
            dest_agent_name="dst",
            action="allow",
        )
        assert req.priority == 0

    def test_compliance_rule_create_request(self):
        req = ComplianceRuleCreateRequest(
            rule_type="sovereignty",
            source_value="eu",
            dest_value="us",
            action="block",
        )
        assert req.priority == 0

    def test_cost_summary_defaults(self):
        cs = CostSummaryResponse()
        assert cs.entries == []
        assert cs.total_cost_usd is None
