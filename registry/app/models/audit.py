"""Audit log model for immutable compliance-grade logging."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class AuditLog(db.Model):
    """Immutable audit log entry. No update or delete operations allowed."""

    __tablename__ = 'audit_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(150), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(UUID(as_uuid=True), nullable=True)
    resource_name = db.Column(db.String(255), nullable=True)
    detail = db.Column(JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)

    __table_args__ = (
        Index('ix_audit_logs_tenant_timestamp', 'tenant_id', 'timestamp'),
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('ix_audit_logs_user_id', 'user_id'),
    )

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.username} at {self.timestamp}>'
