"""Certificate tracking model — tracks certificates issued by the registry CA."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class IssuedCertificate(db.Model):
    """Tracks certificates signed by the registry CA for audit purposes."""

    __tablename__ = 'issued_certificates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(db.String(255), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False, unique=True)
    issued_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active, revoked
    tenant_id = db.Column(db.String(100), nullable=False, default='default')

    __table_args__ = (
        Index('ix_issued_certs_agent', 'agent_id'),
        Index('ix_issued_certs_status', 'status'),
    )

    def __repr__(self):
        return f'<IssuedCertificate agent={self.agent_id} serial={self.serial_number[:20]}...>'
