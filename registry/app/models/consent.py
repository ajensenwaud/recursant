"""GDPR consent tracking model — tracks data subject consent for personal data processing."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Index
from sqlalchemy.dialects.postgresql import UUID

from app import db


class DataSubjectConsent(db.Model):
    """Tracks per-subject, per-type consent (processing, sharing, marketing, etc.)."""

    __tablename__ = 'data_subject_consents'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(100), nullable=False, default='default')
    data_subject_id = db.Column(db.String(255), nullable=False)
    consent_type = db.Column(
        db.String(50), nullable=False,
    )  # processing, sharing, marketing
    granted = db.Column(db.Boolean, nullable=False, default=True)
    granted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    withdrawn_at = db.Column(db.DateTime(timezone=True), nullable=True)
    legal_basis = db.Column(db.String(100), nullable=True)  # consent, contract, legitimate_interest, etc.
    source = db.Column(db.String(255), nullable=True)  # where consent was obtained
    metadata_json = db.Column(JSON, nullable=True)

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
        Index('ix_consent_tenant_subject', 'tenant_id', 'data_subject_id'),
        Index('ix_consent_type', 'tenant_id', 'data_subject_id', 'consent_type'),
    )

    def __repr__(self):
        status = 'granted' if self.granted else 'withdrawn'
        return f'<DataSubjectConsent {self.data_subject_id} {self.consent_type}: {status}>'
