"""Stage-based guardrail configuration models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app import db


class GuardrailConfig(db.Model):
    """A named guardrail configuration (e.g. production, staging, canary)."""
    __tablename__ = 'guardrail_configs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)

    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_by = db.Column(db.String(255), nullable=True)
    activated_by = db.Column(db.String(255), nullable=True)
    activated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    entries = db.relationship(
        'GuardrailConfigEntry', backref='config', lazy='dynamic', cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.Index(
            'uq_tenant_config_name',
            'tenant_id', 'name',
            unique=True,
        ),
    )

    def __repr__(self):
        return f'<GuardrailConfig {self.name} active={self.is_active}>'


class GuardrailConfigEntry(db.Model):
    """An override entry within a guardrail configuration."""
    __tablename__ = 'guardrail_config_entries'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrail_configs.id'), nullable=False)
    guardrail_id = db.Column(UUID(as_uuid=True), db.ForeignKey('guardrails.id'), nullable=False)
    enforcement_mode_override = db.Column(db.String(20), nullable=True)  # block/warn/redact or null
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    priority_override = db.Column(db.Integer, nullable=True)
    config_override = db.Column(JSON, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('config_id', 'guardrail_id', name='uq_config_guardrail'),
    )

    def __repr__(self):
        return f'<GuardrailConfigEntry config={self.config_id} guardrail={self.guardrail_id}>'
