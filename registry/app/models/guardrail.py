"""Guardrail models for defining, assigning, and testing guardrails."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, text
from sqlalchemy.dialects.postgresql import UUID

from app import db


class GuardrailType(enum.Enum):
    PRE_PROCESSING = 'pre_processing'
    POST_PROCESSING = 'post_processing'
    STRUCTURAL = 'structural'


class GuardrailStatus(enum.Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    DISABLED = 'disabled'


class EnforcementMode(enum.Enum):
    BLOCK = 'block'
    WARN = 'warn'
    REDACT = 'redact'


class GuardrailMechanism(enum.Enum):
    LLM_JUDGE = 'llm_judge'
    REGEX = 'regex'
    VECTOR_LOOKUP = 'vector_lookup'
    ML_CLASSIFIER = 'ml_classifier'


class GuardrailScope(enum.Enum):
    ALL_AGENTS = 'all_agents'
    SPECIFIC_AGENTS = 'specific_agents'


class TestRunStatus(enum.Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class Guardrail(db.Model):
    """A guardrail rule definition."""
    __tablename__ = 'guardrails'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    type = db.Column(db.Enum(GuardrailType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = db.Column(db.Enum(GuardrailStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=GuardrailStatus.DRAFT)
    enforcement_mode = db.Column(db.Enum(EnforcementMode, values_callable=lambda x: [e.value for e in x]), nullable=False, default=EnforcementMode.BLOCK)
    mechanism = db.Column(db.Enum(GuardrailMechanism, values_callable=lambda x: [e.value for e in x]), nullable=False)
    config = db.Column(JSON, nullable=False, default=dict)
    scope = db.Column(db.Enum(GuardrailScope, values_callable=lambda x: [e.value for e in x]), nullable=False, default=GuardrailScope.ALL_AGENTS)
    priority = db.Column(db.Integer, nullable=False, default=100)
    version = db.Column(db.String(50), nullable=True)
    metric_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrail_metrics.id'), nullable=True)

    created_by = db.Column(db.String(255), nullable=True)
    approved_by = db.Column(db.String(255), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    assignments = db.relationship(
        'GuardrailAssignment',
        backref='guardrail',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    test_runs = db.relationship(
        'GuardrailTestRun',
        backref='guardrail',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.Index(
            'uq_tenant_guardrail_name_active',
            'tenant_id', 'name',
            unique=True,
            postgresql_where=db.text('deleted_at IS NULL'),
        ),
    )

    def __repr__(self):
        return f'<Guardrail {self.name} ({self.type.value})>'

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)
        self.status = GuardrailStatus.DISABLED


class GuardrailAssignment(db.Model):
    """Maps guardrails to specific agents."""
    __tablename__ = 'guardrail_assignments'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guardrail_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrails.id'), nullable=False)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=True)
    agent_name = db.Column(db.String(255), nullable=True)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('guardrail_id', 'agent_id', name='uq_guardrail_agent'),
    )

    def __repr__(self):
        return f'<GuardrailAssignment guardrail={self.guardrail_id} agent={self.agent_name}>'


class GuardrailTestRun(db.Model):
    """Records testing of guardrails against live agents."""
    __tablename__ = 'guardrail_test_runs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guardrail_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrails.id'), nullable=False)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=True)
    status = db.Column(db.Enum(TestRunStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TestRunStatus.PENDING)
    test_inputs = db.Column(JSON, nullable=True)
    test_results = db.Column(JSON, nullable=True)
    passed_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    initiated_by = db.Column(db.String(255), nullable=True)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f'<GuardrailTestRun {self.id} status={self.status.value}>'


class GuardrailEvent(db.Model):
    """High-volume guardrail evaluation events shipped from sidecars.

    One row per guardrail evaluation — used for observability dashboard
    (trigger rates, latency breakdown, drift detection).
    """
    __tablename__ = 'guardrail_events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    guardrail_id = db.Column(UUID(as_uuid=True), nullable=True)
    guardrail_name = db.Column(db.String(255), nullable=True)
    guardrail_type = db.Column(db.String(50), nullable=True)
    mechanism = db.Column(db.String(50), nullable=True)
    agent_name = db.Column(db.String(255), nullable=True)
    sidecar_id = db.Column(db.String(255), nullable=True)
    action = db.Column(db.String(20), nullable=False)  # pass/block/warn/redact
    reasoning = db.Column(db.Text, nullable=True)
    latency_ms = db.Column(db.Float, nullable=True)
    matched_pattern = db.Column(db.String(500), nullable=True)
    input_hash = db.Column(db.String(64), nullable=True)
    is_error = db.Column(db.Boolean, nullable=False, default=False)
    error_message = db.Column(db.Text, nullable=True)
    is_false_positive = db.Column(db.Boolean, nullable=True)
    metric_id = db.Column(UUID(as_uuid=True), nullable=True)
    triggered_spans = db.Column(JSON, nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_guardrail_events_tenant_ts', 'tenant_id', 'timestamp'),
        db.Index('ix_guardrail_events_guardrail_ts', 'guardrail_id', 'timestamp'),
        db.Index('ix_guardrail_events_agent_ts', 'agent_name', 'timestamp'),
        db.Index('ix_guardrail_events_action', 'action'),
    )

    def __repr__(self):
        return f'<GuardrailEvent {self.guardrail_name} {self.action} at {self.timestamp}>'
