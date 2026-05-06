"""Marshmallow schemas for observability API endpoints."""

from marshmallow import Schema, fields, validate


# ---------------------------------------------------------------------------
# Trace schemas
# ---------------------------------------------------------------------------

class TraceHopSchema(Schema):
    """Schema for a single hop in a trace."""
    id = fields.String()
    timestamp = fields.String()
    source_agent_name = fields.String(allow_none=True)
    dest_agent_name = fields.String(allow_none=True)
    a2a_method = fields.String(allow_none=True)
    direction = fields.String(allow_none=True)
    decision = fields.String(allow_none=True)
    outcome = fields.String(allow_none=True)
    sidecar_id = fields.String(allow_none=True)
    details = fields.Raw(allow_none=True)
    cot_analysis = fields.Raw(allow_none=True)
    cot_risk_level = fields.String(allow_none=True)
    latency_ms = fields.Float()


class TraceSchema(Schema):
    """Schema for a complete trace response."""
    task_id = fields.String()
    hops = fields.List(fields.Nested(TraceHopSchema))
    total_duration_ms = fields.Float()
    agent_count = fields.Integer()
    start_time = fields.String(allow_none=True)
    end_time = fields.String(allow_none=True)
    status = fields.String(allow_none=True)


class TraceSummarySchema(Schema):
    """Schema for a trace in the list view."""
    task_id = fields.String()
    hop_count = fields.Integer()
    start_time = fields.String(allow_none=True)
    end_time = fields.String(allow_none=True)
    duration_ms = fields.Float()


class TraceListSchema(Schema):
    """Schema for paginated trace list response."""
    traces = fields.List(fields.Nested(TraceSummarySchema))
    total = fields.Integer()
    page = fields.Integer()
    per_page = fields.Integer()


class TraceListQuerySchema(Schema):
    """Schema for trace list query parameters."""
    date_from = fields.DateTime(load_default=None)
    date_to = fields.DateTime(load_default=None)
    agent_name = fields.String(load_default=None, validate=validate.Length(max=255))
    page = fields.Integer(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Integer(load_default=50, validate=validate.Range(min=1, max=200))


# ---------------------------------------------------------------------------
# Golden signals schemas
# ---------------------------------------------------------------------------

class GoldenSignalsSchema(Schema):
    """Schema for golden signals per agent."""
    request_rate = fields.Float()
    error_rate = fields.Float()
    p50_latency_ms = fields.Float()
    p95_latency_ms = fields.Float()
    p99_latency_ms = fields.Float()
    total_requests = fields.Integer()
    total_errors = fields.Integer()


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------

class AlertSchema(Schema):
    """Schema for an anomaly alert."""
    id = fields.String()
    anomaly_type = fields.String()
    severity = fields.String()
    agent_name = fields.String(allow_none=True)
    description = fields.String(allow_none=True)
    details = fields.Raw(allow_none=True)
    detected_at = fields.String(allow_none=True)
    resolved_at = fields.String(allow_none=True)
    is_acknowledged = fields.Boolean()


class AlertListQuerySchema(Schema):
    """Schema for alert list query parameters."""
    include_resolved = fields.Boolean(load_default=False)
    limit = fields.Integer(load_default=100, validate=validate.Range(min=1, max=500))


# ---------------------------------------------------------------------------
# Security posture schemas
# ---------------------------------------------------------------------------

class SecurityPostureComponentsSchema(Schema):
    """Schema for individual security posture components."""
    mtls_coverage = fields.Float()
    guardrail_coverage = fields.Float()
    guardrail_effectiveness = fields.Float()
    anomaly_score = fields.Float()
    policy_compliance = fields.Float()


class SecurityPostureSchema(Schema):
    """Schema for composite security posture response."""
    composite_score = fields.Float()
    components = fields.Nested(SecurityPostureComponentsSchema)
    open_anomalies = fields.Integer()
    total_registrations = fields.Integer()
    active_agents = fields.Integer()


# ---------------------------------------------------------------------------
# Cost schemas
# ---------------------------------------------------------------------------

class CostEntrySchema(Schema):
    """Schema for a cost entry per agent/model."""
    agent_name = fields.String()
    model_name = fields.String()
    input_tokens = fields.Integer()
    output_tokens = fields.Integer()
    cost_usd = fields.Float()
    request_count = fields.Integer()
    updated_at = fields.String(allow_none=True)


class CostSummarySchema(Schema):
    """Schema for the cost summary response."""
    entries = fields.List(fields.Nested(CostEntrySchema))
    total_cost_usd = fields.Float()
    total_input_tokens = fields.Integer()
    total_output_tokens = fields.Integer()
    total_requests = fields.Integer()


# ---------------------------------------------------------------------------
# Tool metrics schemas
# ---------------------------------------------------------------------------

class ToolMetricSchema(Schema):
    """Schema for per-tool metrics."""
    tool_name = fields.String()
    call_count = fields.Integer()
    error_count = fields.Integer()
    error_rate = fields.Float()
    agents_using = fields.List(fields.String())
