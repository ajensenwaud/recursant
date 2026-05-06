"""Mesh runtime models — tracks sidecar registrations, policies, and audit logs.

These models support the mesh control plane functionality:
- MeshRegistration: runtime sidecar registrations (which agents are online)
- MeshPolicy: authorisation policies for agent-to-agent communication
- MeshAuditLog: audit records received from sidecars
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class MeshRegistration(db.Model):
    """Runtime sidecar registration — tracks which approved agents are currently online."""

    __tablename__ = 'mesh_registrations'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('agents.id'),
        nullable=False,
        unique=True,
    )
    sidecar_url = db.Column(db.String(2048), nullable=False)
    agent_card = db.Column(JSON, nullable=False)
    sovereignty_zone = db.Column(db.String(50), nullable=True)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')

    registered_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_heartbeat = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status = db.Column(db.String(20), nullable=False, default='healthy')
    traffic_weight = db.Column(db.Integer, nullable=False, default=100)

    # Multi-cluster fields
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to Agent model
    agent = db.relationship('Agent', backref=db.backref('mesh_registration', uselist=False))

    __table_args__ = (
        Index('ix_mesh_registrations_tenant', 'tenant_id'),
        Index('ix_mesh_registrations_status', 'status'),
        Index('ix_mesh_registrations_cluster', 'cluster_id'),
    )

    def __repr__(self):
        return f'<MeshRegistration agent_id={self.agent_id} status={self.status}>'


class MeshPolicy(db.Model):
    """Authorisation policies for agent-to-agent communication."""

    __tablename__ = 'mesh_policies'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    source_agent_name = db.Column(db.String(255), nullable=False)
    dest_agent_name = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(10), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=0)

    # Multi-cluster provenance
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_mesh_policies_tenant', 'tenant_id'),
        Index('ix_mesh_policies_priority', 'tenant_id', 'priority'),
    )

    def __repr__(self):
        return f'<MeshPolicy {self.source_agent_name} -> {self.dest_agent_name}: {self.action}>'


class MeshAuditLog(db.Model):
    """Audit records received from sidecars."""

    __tablename__ = 'mesh_audit_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    source_agent_id = db.Column(db.String(255), nullable=True)
    source_agent_name = db.Column(db.String(255), nullable=True)
    dest_agent_id = db.Column(db.String(255), nullable=True)
    dest_agent_name = db.Column(db.String(255), nullable=True)
    task_id = db.Column(db.String(255), nullable=True)
    a2a_method = db.Column(db.String(100), nullable=False)
    message_hash = db.Column(db.String(64), nullable=False)
    direction = db.Column(db.String(20), nullable=False)
    decision = db.Column(db.String(20), nullable=False)
    outcome = db.Column(db.String(20), nullable=False)
    details = db.Column(JSON, nullable=True)
    sidecar_id = db.Column(db.String(255), nullable=True)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    # Multi-cluster provenance
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')
    # Hash-chain fields for tamper-evident audit
    record_hash = db.Column(db.String(64), nullable=True)
    previous_record_hash = db.Column(db.String(64), nullable=True)
    sequence_number = db.Column(db.Integer, nullable=True)

    # Chain-of-thought auditing (Phase 2)
    cot_analysis = db.Column(JSON, nullable=True)
    cot_risk_level = db.Column(db.String(20), nullable=True)
    cot_flags = db.Column(JSON, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_mesh_audit_logs_tenant_timestamp', 'tenant_id', 'timestamp'),
        Index('ix_mesh_audit_logs_task_id', 'task_id'),
        Index('ix_mesh_audit_logs_source', 'source_agent_name'),
        Index('ix_mesh_audit_logs_chain', 'sidecar_id', 'sequence_number'),
    )

    def __repr__(self):
        return f'<MeshAuditLog {self.a2a_method} {self.outcome} at {self.timestamp}>'


class MeshComplianceRule(db.Model):
    """Compliance rules for sovereignty zones and data classification enforcement."""

    __tablename__ = 'mesh_compliance_rules'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    rule_type = db.Column(db.String(50), nullable=False)  # "sovereignty" | "classification"
    source_value = db.Column(db.String(100), nullable=False)  # e.g. "eu" or "confidential"
    dest_value = db.Column(db.String(100), nullable=False)  # e.g. "us" or "public"
    action = db.Column(db.String(10), nullable=False)  # "allow" | "block"
    priority = db.Column(db.Integer, nullable=False, default=0)

    # Multi-cluster provenance
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_mesh_compliance_rules_tenant', 'tenant_id'),
        Index('ix_mesh_compliance_rules_type', 'tenant_id', 'rule_type'),
    )

    def __repr__(self):
        return f'<MeshComplianceRule {self.rule_type}: {self.source_value} -> {self.dest_value}: {self.action}>'


class MeshTool(db.Model):
    """Registered tool that agents can call through the sidecar gateway."""

    __tablename__ = 'mesh_tools'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    tool_type = db.Column(db.String(20), nullable=False, default='http')
    endpoint_url = db.Column(db.String(2048), nullable=False)
    http_method = db.Column(db.String(10), nullable=False, default='POST')
    parameters_schema = db.Column(JSON, nullable=True)
    mcp_server_url = db.Column(db.String(512), nullable=True)
    mcp_server_name = db.Column(db.String(255), nullable=True)
    mcp_server_description = db.Column(db.Text, nullable=True)
    backend_services = db.Column(JSON, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='submitted')
    approved_by = db.Column(db.String(255), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_by = db.Column(db.String(255), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    assignments = db.relationship('MeshToolAssignment', backref='tool', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_mesh_tools_tenant_name'),
        Index('ix_mesh_tools_tenant', 'tenant_id'),
        Index('ix_mesh_tools_status', 'status'),
    )

    def __repr__(self):
        return f'<MeshTool {self.name} [{self.status}]>'


class MeshToolAssignment(db.Model):
    """Maps an approved tool to an agent that is allowed to use it."""

    __tablename__ = 'mesh_tool_assignments'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    tool_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('mesh_tools.id', ondelete='CASCADE'),
        nullable=False,
    )
    agent_name = db.Column(db.String(255), nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'tool_id', 'agent_name', name='uq_mesh_tool_assignments_tenant_tool_agent'),
        Index('ix_mesh_tool_assignments_tenant', 'tenant_id'),
        Index('ix_mesh_tool_assignments_agent', 'agent_name'),
    )

    def __repr__(self):
        return f'<MeshToolAssignment tool={self.tool_id} agent={self.agent_name}>'


class MeshAnomaly(db.Model):
    """Anomalies detected by the observability pipeline."""

    __tablename__ = 'mesh_anomalies'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    anomaly_type = db.Column(db.String(50), nullable=False)  # traffic_spike, error_burst, policy_violation_surge, cost_spike
    severity = db.Column(db.String(20), nullable=False, default='medium')  # low, medium, high, critical
    agent_name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=False)
    details = db.Column(JSON, nullable=True)
    detected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    is_acknowledged = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        Index('ix_mesh_anomalies_tenant_detected', 'tenant_id', 'detected_at'),
        Index('ix_mesh_anomalies_agent', 'agent_name'),
        Index('ix_mesh_anomalies_severity', 'severity'),
    )

    def __repr__(self):
        return f'<MeshAnomaly {self.anomaly_type} [{self.severity}] at {self.detected_at}>'


class MeshEgressRule(db.Model):
    """Egress control rule — URL allowlist/denylist for non-tool HTTP calls."""

    __tablename__ = 'mesh_egress_rules'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    agent_name = db.Column(db.String(255), nullable=False, default='*')
    url_pattern = db.Column(db.String(2048), nullable=False)
    action = db.Column(db.String(10), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=0)
    cluster_id = db.Column(db.String(50), nullable=False, server_default='default')

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_mesh_egress_rules_tenant', 'tenant_id'),
        Index('ix_mesh_egress_rules_priority', 'tenant_id', 'priority'),
    )

    def __repr__(self):
        return f'<MeshEgressRule {self.agent_name} {self.url_pattern}: {self.action}>'


class MeshReasoningSpan(db.Model):
    """Per-agent reasoning span — captures tool calls, decisions, observations within a trace."""

    __tablename__ = 'mesh_reasoning_spans'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, server_default='default')
    task_id = db.Column(db.String(255), nullable=False)
    trace_id = db.Column(db.String(64), nullable=True)
    agent_name = db.Column(db.String(255), nullable=False)

    span_type = db.Column(db.String(50), nullable=False)   # tool_call | decision | observation | thought | retrieval
    span_name = db.Column(db.String(255), nullable=False)

    input_data = db.Column(JSON, nullable=True)
    output_data = db.Column(JSON, nullable=True)

    start_time = db.Column(db.DateTime(timezone=True), nullable=False)
    end_time = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_ms = db.Column(db.Float, nullable=True)

    parent_span_id = db.Column(UUID(as_uuid=True), nullable=True)
    metadata_ = db.Column('metadata', JSON, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index('ix_mesh_reasoning_spans_tenant_task', 'tenant_id', 'task_id'),
        Index('ix_mesh_reasoning_spans_agent', 'agent_name'),
        Index('ix_mesh_reasoning_spans_type', 'span_type'),
    )
