"""OpenClaw instance and enrollment-token models.

An OpenClaw "instance" is a local-first OpenClaw process running on a user's
machine that has registered itself with the Recursant registry through the
openclaw-recursant plugin. Each instance is backed by an Agent row (with
endpoint.type == 'openclaw') so it can ride the existing governance pipeline.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app import db


class OpenClawInstanceStatus(enum.Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    REVOKED = 'revoked'


class OpenClawInstance(db.Model):
    __tablename__ = 'openclaw_instances'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default', index=True)

    machine_id = db.Column(db.String(64), nullable=False, index=True)
    instance_fingerprint = db.Column(JSON, nullable=False, default=dict)
    os = db.Column(db.String(64), nullable=True)
    openclaw_version = db.Column(db.String(64), nullable=True)
    plugin_version = db.Column(db.String(64), nullable=True)

    status = db.Column(
        db.Enum(OpenClawInstanceStatus, name='openclaw_instance_status'),
        nullable=False,
        default=OpenClawInstanceStatus.PENDING,
    )
    enrolled_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_heartbeat_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    agent = db.relationship('Agent', backref=db.backref('openclaw_instance', uselist=False))

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'machine_id', name='uq_openclaw_instance_tenant_machine'),
    )


class OpenClawEnrollmentToken(db.Model):
    __tablename__ = 'openclaw_enrollment_tokens'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, default='default', index=True)
    token_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    consumed_by_instance_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('openclaw_instances.id'),
        nullable=True,
    )

    def is_usable(self) -> bool:
        if self.consumed_at is not None:
            return False
        return self.expires_at > datetime.now(timezone.utc)
