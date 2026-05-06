"""Pydantic models matching the Recursant Registry API."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────

class AgentStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    TESTING = "testing"
    EVALUATING = "evaluating"
    SECURITY_FAILED = "security_failed"
    EVALUATION_FAILED = "evaluation_failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DECOMMISSIONED = "decommissioned"


class Classification(str, enum.Enum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PUBLIC = "public"


class DataSensitivity(str, enum.Enum):
    NONE = "none"
    PII = "pii"
    PHI = "phi"
    FINANCIAL = "financial"
    SECRET = "secret"


class RiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EndpointType(str, enum.Enum):
    LANGCHAIN = "langchain"
    CREWAI = "crewai"
    LANGGRAPH = "langgraph"
    AGENTFORCE = "agentforce"
    DATABRICKS = "databricks"
    OPENAI = "openai"
    CUSTOM = "custom"


class AuthMethod(str, enum.Enum):
    MTLS = "mtls"
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    IAM = "iam"


# ── Request / nested models ─────────────────────────────────────────────

class CapabilityRequest(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class ToolDependencyRequest(BaseModel):
    tool_id: str
    required: bool = True


class AgentRelationshipRequest(BaseModel):
    agent_id: str
    relationship_type: str | None = None  # upstream / downstream


class EndpointRequest(BaseModel):
    type: str
    url: str
    auth_method: str
    timeout_ms: int = 30000
    agent_protocol: str = "A2A"


class ResourceQuotaRequest(BaseModel):
    max_tokens_per_request: int | None = None
    max_requests_per_minute: int | None = None
    max_cost_per_day_usd: float | None = None


class AgentCreateRequest(BaseModel):
    name: str
    version: str
    description: str
    owner_id: str
    team_id: str
    contact_email: str
    classification: str
    data_sensitivity: str
    risk_tier: str
    capabilities: list[CapabilityRequest]
    endpoint: EndpointRequest
    tools: list[ToolDependencyRequest] = Field(default_factory=list)
    upstream_agents: list[AgentRelationshipRequest] = Field(default_factory=list)
    downstream_agents: list[AgentRelationshipRequest] = Field(default_factory=list)
    guardrail_profile_id: str | None = None
    execution_graph_id: str | None = None
    resource_quota: ResourceQuotaRequest | None = None
    tenant_id: str = "default"


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    owner_id: str | None = None
    team_id: str | None = None
    contact_email: str | None = None
    classification: str | None = None
    data_sensitivity: str | None = None
    risk_tier: str | None = None
    capabilities: list[CapabilityRequest] | None = None
    endpoint: EndpointRequest | None = None
    tools: list[ToolDependencyRequest] | None = None
    upstream_agents: list[AgentRelationshipRequest] | None = None
    downstream_agents: list[AgentRelationshipRequest] | None = None
    guardrail_profile_id: str | None = None
    execution_graph_id: str | None = None
    resource_quota: ResourceQuotaRequest | None = None


# ── Response models ──────────────────────────────────────────────────────

class CapabilityResponse(BaseModel):
    id: UUID | None = None
    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class AgentResponse(BaseModel):
    id: UUID
    name: str
    version: str
    description: str
    owner_id: str | None = None
    team_id: str | None = None
    contact_email: str | None = None
    tenant_id: str | None = None
    status: str
    classification: str
    data_sensitivity: str | None = None
    risk_tier: str | None = None
    endpoint: dict[str, Any] | None = None
    capabilities: list[CapabilityResponse] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    upstream_agents: list[dict[str, Any]] = Field(default_factory=list)
    downstream_agents: list[dict[str, Any]] = Field(default_factory=list)
    guardrail_profile_id: str | None = None
    execution_graph_id: str | None = None
    resource_quota: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"extra": "allow"}


class AgentListItem(BaseModel):
    id: UUID
    name: str
    version: str
    description: str
    status: str
    classification: str
    risk_tier: str | None = None
    team_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"extra": "allow"}


class PaginatedAgents(BaseModel):
    agents: list[AgentListItem] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)


# ── Security ─────────────────────────────────────────────────────────────

class SecurityScanResponse(BaseModel):
    id: UUID | None = None
    agent_id: UUID | None = None
    status: str | None = None
    scan_types: list[str] | None = None
    overall_result: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"extra": "allow"}


# ── Evaluation ───────────────────────────────────────────────────────────

class EvaluationResponse(BaseModel):
    id: UUID | None = None
    agent_id: UUID | None = None
    suite_id: UUID | None = None
    status: str | None = None
    overall_score: float | None = None
    passed: bool | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"extra": "allow"}


# ── Guardrails ───────────────────────────────────────────────────────────

class GuardrailCreateRequest(BaseModel):
    name: str
    description: str | None = None
    type: str  # pre_processing, post_processing, structural
    mechanism: str  # regex, vector, llm, ml_classifier
    enforcement_mode: str = "block"  # block, warn, redact
    scope: str | None = None
    priority: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class GuardrailResponse(BaseModel):
    id: UUID | None = None
    name: str
    description: str | None = None
    type: str | None = None
    mechanism: str | None = None
    enforcement: str | None = None
    scope: str | None = None
    priority: int | None = None
    config: dict[str, Any] | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"extra": "allow"}


# ── Mesh ─────────────────────────────────────────────────────────────────

class PolicyCreateRequest(BaseModel):
    source_agent_name: str
    dest_agent_name: str
    action: str  # allow | deny
    priority: int = 0


class PolicyResponse(BaseModel):
    id: UUID | None = None
    tenant_id: str | None = None
    source: str | None = None
    destination: str | None = None
    source_agent_name: str | None = None
    dest_agent_name: str | None = None
    action: str
    priority: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"extra": "allow"}


class RegistrationResponse(BaseModel):
    id: UUID | None = None
    agent_id: UUID | None = None
    sidecar_url: str | None = None
    agent_card: dict[str, Any] | None = None
    sovereignty_zone: str | None = None
    status: str | None = None
    last_heartbeat: datetime | None = None

    model_config = {"extra": "allow"}


class ComplianceRuleCreateRequest(BaseModel):
    rule_type: str  # sovereignty | classification
    source_value: str
    dest_value: str
    action: str  # allow | block
    priority: int = 0


class ComplianceRuleResponse(BaseModel):
    id: UUID | None = None
    rule_type: str | None = None
    source_value: str | None = None
    dest_value: str | None = None
    action: str | None = None
    priority: int = 0
    created_at: datetime | None = None

    model_config = {"extra": "allow"}


# ── Observability ────────────────────────────────────────────────────────

class TraceHop(BaseModel):
    id: str | None = None
    timestamp: str | None = None
    source_agent_name: str | None = None
    dest_agent_name: str | None = None
    a2a_method: str | None = None
    direction: str | None = None
    decision: str | None = None
    outcome: str | None = None
    sidecar_id: str | None = None
    details: dict[str, Any] | None = None
    cot_analysis: dict[str, Any] | None = None
    cot_risk_level: str | None = None
    latency_ms: float | None = None

    model_config = {"extra": "allow"}


class TraceResponse(BaseModel):
    task_id: str
    hops: list[TraceHop] = Field(default_factory=list)
    total_duration_ms: float | None = None
    agent_count: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
    reasoning_spans: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class TraceSummary(BaseModel):
    task_id: str
    hop_count: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: float | None = None

    model_config = {"extra": "allow"}


class GoldenSignalsResponse(BaseModel):
    agent_name: str | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, Any] | None = None  # for all-agents endpoint

    model_config = {"extra": "allow"}


class AlertResponse(BaseModel):
    id: UUID | None = None
    anomaly_type: str | None = None
    severity: str | None = None
    agent_name: str | None = None
    description: str | None = None
    details: dict[str, Any] | None = None
    detected_at: datetime | None = None
    resolved_at: datetime | None = None
    is_acknowledged: bool | None = None

    model_config = {"extra": "allow"}


class CostEntry(BaseModel):
    agent_name: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    request_count: int | None = None
    updated_at: str | None = None

    model_config = {"extra": "allow"}


class CostSummaryResponse(BaseModel):
    entries: list[CostEntry] = Field(default_factory=list)
    total_cost_usd: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_requests: int | None = None
    updated_at: str | None = None

    model_config = {"extra": "allow"}


# ── Reasoning Spans ──────────────────────────────────────────────────────

class ReasoningSpanRequest(BaseModel):
    task_id: str
    agent_name: str
    span_type: str  # tool_call | decision | observation | thought | retrieval
    span_name: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    start_time: str
    end_time: str | None = None
    duration_ms: float | None = None
    parent_span_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None


class ReasoningSpanResponse(BaseModel):
    id: UUID | None = None
    task_id: str
    agent_name: str
    span_type: str
    span_name: str
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: float | None = None
    parent_span_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"extra": "allow"}


# ── Auth ─────────────────────────────────────────────────────────────────

class LoginResponse(BaseModel):
    token: str
    username: str | None = None
    expires_in: int | None = None
