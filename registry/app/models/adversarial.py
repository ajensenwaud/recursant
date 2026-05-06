"""Adversarial testing models for guardrail evasion testing."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app import db


class AdversarialTestSuite(db.Model):
    """Configuration for a set of adversarial attacks against guardrails."""
    __tablename__ = 'adversarial_test_suites'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    attack_types = db.Column(JSON, nullable=False, default=list)
    target_guardrail_ids = db.Column(JSON, nullable=False, default=list)
    target_agent_names = db.Column(JSON, nullable=False, default=list)
    schedule_enabled = db.Column(db.Boolean, nullable=False, default=False)
    schedule_interval_minutes = db.Column(db.Integer, nullable=True)
    last_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    evasion_rate_threshold = db.Column(db.Float, nullable=False, default=0.1)
    alert_on_threshold_breach = db.Column(db.Boolean, nullable=False, default=True)
    generation_config = db.Column(JSON, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='active')
    created_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    runs = db.relationship(
        'AdversarialTestRun',
        backref='suite',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.Index('ix_adversarial_suites_tenant', 'tenant_id'),
        db.Index('ix_adversarial_suites_schedule', 'schedule_enabled', 'next_run_at'),
    )

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)
        self.status = 'disabled'

    def __repr__(self):
        return f'<AdversarialTestSuite {self.name} [{self.status}]>'


class AdversarialTestRun(db.Model):
    """Execution record for an adversarial test run."""
    __tablename__ = 'adversarial_test_runs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suite_id = db.Column(UUID(as_uuid=True),
                         db.ForeignKey('adversarial_test_suites.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    status = db.Column(db.String(20), nullable=False, default='pending')
    triggered_by = db.Column(db.String(255), nullable=True)
    total_inputs = db.Column(db.Integer, default=0)
    blocked_count = db.Column(db.Integer, default=0)
    evaded_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    evasion_rate = db.Column(db.Float, nullable=True)
    generated_inputs = db.Column(JSON, nullable=True)
    results = db.Column(JSON, nullable=True)
    threshold_breached = db.Column(db.Boolean, nullable=False, default=False)
    alert_sent = db.Column(db.Boolean, nullable=False, default=False)
    result_signature = db.Column(db.String(128), nullable=True)
    signature_algorithm = db.Column(db.String(20), nullable=True)

    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_adversarial_runs_suite', 'suite_id'),
        db.Index('ix_adversarial_runs_status', 'status'),
        db.Index('ix_adversarial_runs_breached', 'threshold_breached'),
    )

    def __repr__(self):
        return f'<AdversarialTestRun {self.id} status={self.status}>'


class CustomAttack(db.Model):
    """User-defined adversarial attack entry stored in the database."""
    __tablename__ = 'custom_attacks'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    attack_type = db.Column(db.String(50), nullable=False)
    variant_name = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(20), nullable=False, default='medium')
    source = db.Column(db.String(255), nullable=True)
    tags = db.Column(JSON, nullable=False, default=list)
    created_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.Index('ix_custom_attacks_tenant', 'tenant_id'),
        db.Index('ix_custom_attacks_type', 'tenant_id', 'attack_type'),
        db.UniqueConstraint('tenant_id', 'attack_type', 'variant_name',
                            name='uq_custom_attack_variant'),
    )

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f'<CustomAttack {self.variant_name} [{self.attack_type}]>'
