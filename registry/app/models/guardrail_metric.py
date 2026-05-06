"""Unified guardrail metric store — shared definitions for evaluation, monitoring, and enforcement."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, text
from sqlalchemy.dialects.postgresql import UUID

from app import db


class MetricCategory(enum.Enum):
    SAFETY = 'safety'
    POLICY = 'policy'
    HALLUCINATION = 'hallucination'
    BOUNDARY = 'boundary'
    QUALITY = 'quality'
    TONE = 'tone'
    CUSTOM = 'custom'


class GuardrailMetric(db.Model):
    """A reusable metric definition that can power guardrails, evaluations, and monitoring."""
    __tablename__ = 'guardrail_metrics'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(
        db.Enum(MetricCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MetricCategory.CUSTOM,
    )
    mechanism = db.Column(db.String(50), nullable=False)  # reuses GuardrailMechanism values
    config = db.Column(JSON, nullable=False, default=dict)
    version = db.Column(db.String(50), nullable=True)
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)
    scoring_rubric = db.Column(JSON, nullable=True)

    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_by = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    scores = db.relationship(
        'GuardrailMetricScore',
        backref='metric',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.Index(
            'uq_tenant_metric_name_active',
            'tenant_id', 'name',
            unique=True,
            postgresql_where=db.text('deleted_at IS NULL'),
        ),
    )

    def __repr__(self):
        return f'<GuardrailMetric {self.name} ({self.category.value})>'

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)


class GuardrailMetricScore(db.Model):
    """A score recorded against a metric for a specific agent."""
    __tablename__ = 'guardrail_metric_scores'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrail_metrics.id'), nullable=False)
    agent_name = db.Column(db.String(255), nullable=True)
    score = db.Column(db.Float, nullable=True)
    details = db.Column(JSON, nullable=True)
    source = db.Column(db.String(50), nullable=False, default='evaluation')  # evaluation/sidecar/adversarial
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_metric_scores_metric_ts', 'metric_id', 'timestamp'),
        db.Index('ix_metric_scores_agent', 'agent_name', 'timestamp'),
    )

    def __repr__(self):
        return f'<GuardrailMetricScore metric={self.metric_id} score={self.score}>'
