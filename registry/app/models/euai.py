import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app import db


# ── Enums ──────────────────────────────────────────────────────────────

class EUAIRiskCategory(enum.Enum):
    UNACCEPTABLE = 'unacceptable'
    HIGH = 'high'
    LIMITED = 'limited'
    MINIMAL = 'minimal'


class EUAIUseDomain(enum.Enum):
    BIOMETRICS = 'biometrics'
    CRITICAL_INFRASTRUCTURE = 'critical_infrastructure'
    EDUCATION = 'education'
    EMPLOYMENT = 'employment'
    ESSENTIAL_SERVICES = 'essential_services'
    LAW_ENFORCEMENT = 'law_enforcement'
    MIGRATION_BORDER = 'migration_border'
    JUSTICE_DEMOCRACY = 'justice_democracy'
    GENERAL = 'general'


class ComplianceStatusValue(enum.Enum):
    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    COMPLIANT = 'compliant'
    NON_COMPLIANT = 'non_compliant'
    NOT_APPLICABLE = 'not_applicable'
    WAIVED = 'waived'


class AnnexIVDocumentStatus(enum.Enum):
    DRAFT = 'draft'
    UNDER_REVIEW = 'under_review'
    APPROVED = 'approved'
    SUPERSEDED = 'superseded'


class ConformityAssessmentType(enum.Enum):
    SELF = 'self'
    THIRD_PARTY = 'third_party'


class ConformityAssessmentStatus(enum.Enum):
    IN_PROGRESS = 'in_progress'
    PASSED = 'passed'
    FAILED = 'failed'
    WITHDRAWN = 'withdrawn'


class MonitoringPlanStatus(enum.Enum):
    ACTIVE = 'active'
    PAUSED = 'paused'
    ARCHIVED = 'archived'


class EvidenceType(enum.Enum):
    AUTO = 'auto'
    MANUAL = 'manual'
    HYBRID = 'hybrid'


# ── Models ─────────────────────────────────────────────────────────────

class EUAIClassification(db.Model):
    """Per-agent EU AI Act risk classification."""
    __tablename__ = 'euai_classifications'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('agents.id'),
        nullable=False,
        unique=True,
    )
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    eu_risk_category = db.Column(db.Enum(EUAIRiskCategory), nullable=False)
    use_domain = db.Column(db.Enum(EUAIUseDomain), nullable=False, default=EUAIUseDomain.GENERAL)
    questionnaire_responses = db.Column(JSONB, nullable=False, default=dict)
    classification_rationale = db.Column(db.Text, nullable=True)
    is_confirmed = db.Column(db.Boolean, default=False)
    classified_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = db.relationship('Agent', backref=db.backref('euai_classification', uselist=False))

    __table_args__ = (
        db.Index('ix_euai_classifications_tenant', 'tenant_id'),
    )


class ComplianceRequirement(db.Model):
    """Reference table of EU AI Act requirements (~50 entries)."""
    __tablename__ = 'compliance_requirements'

    id = db.Column(db.String(50), primary_key=True)  # e.g. "EUAI-ART9-001"
    article_reference = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    applicable_risk_categories = db.Column(JSONB, nullable=False, default=list)
    evidence_type = db.Column(db.Enum(EvidenceType), nullable=False, default=EvidenceType.MANUAL)
    auto_source = db.Column(db.String(255), nullable=True)
    guidance = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ComplianceStatus(db.Model):
    """Per-agent, per-requirement compliance tracking."""
    __tablename__ = 'compliance_statuses'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    requirement_id = db.Column(db.String(50), db.ForeignKey('compliance_requirements.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    status = db.Column(
        db.Enum(ComplianceStatusValue),
        nullable=False,
        default=ComplianceStatusValue.NOT_STARTED,
    )
    evidence_data = db.Column(JSONB, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    last_assessed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    assessed_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = db.relationship('Agent', backref=db.backref('compliance_statuses', lazy='dynamic'))
    requirement = db.relationship('ComplianceRequirement', backref=db.backref('statuses', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'requirement_id', name='uq_agent_requirement'),
        db.Index('ix_compliance_statuses_tenant', 'tenant_id'),
        db.Index('ix_compliance_statuses_agent', 'agent_id'),
        db.Index('ix_compliance_statuses_status', 'status'),
    )


class AnnexIVDocument(db.Model):
    """Generated Annex IV technical documentation."""
    __tablename__ = 'annex_iv_documents'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(
        db.Enum(AnnexIVDocumentStatus),
        nullable=False,
        default=AnnexIVDocumentStatus.DRAFT,
    )
    document_data = db.Column(JSONB, nullable=False, default=dict)
    manual_sections = db.Column(JSONB, nullable=False, default=dict)
    signature = db.Column(db.String(512), nullable=True)
    signature_algorithm = db.Column(db.String(50), nullable=True, default='HMAC-SHA256')
    pdf_storage_path = db.Column(db.String(1024), nullable=True)
    approved_by = db.Column(db.String(255), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    generated_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = db.relationship('Agent', backref=db.backref('annex_iv_documents', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('agent_id', 'version', name='uq_annex_iv_agent_version'),
        db.Index('ix_annex_iv_documents_tenant', 'tenant_id'),
        db.Index('ix_annex_iv_documents_agent', 'agent_id'),
    )


class ConformityAssessment(db.Model):
    """Article 47 Declaration of Conformity."""
    __tablename__ = 'conformity_assessments'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    assessment_type = db.Column(
        db.Enum(ConformityAssessmentType),
        nullable=False,
        default=ConformityAssessmentType.SELF,
    )
    status = db.Column(
        db.Enum(ConformityAssessmentStatus),
        nullable=False,
        default=ConformityAssessmentStatus.IN_PROGRESS,
    )
    compliance_snapshot = db.Column(JSONB, nullable=False, default=dict)
    findings = db.Column(JSONB, nullable=False, default=list)
    declaration_date = db.Column(db.DateTime(timezone=True), nullable=True)
    declared_by = db.Column(db.String(255), nullable=True)
    document_id = db.Column(UUID(as_uuid=True), db.ForeignKey('annex_iv_documents.id'), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = db.relationship('Agent', backref=db.backref('conformity_assessments', lazy='dynamic'))
    annex_iv_document = db.relationship('AnnexIVDocument', backref=db.backref('conformity_assessments', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_conformity_assessments_tenant', 'tenant_id'),
        db.Index('ix_conformity_assessments_agent', 'agent_id'),
    )


class PostMarketMonitoringPlan(db.Model):
    """Article 72 post-market monitoring configuration."""
    __tablename__ = 'post_market_monitoring_plans'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    monitoring_config = db.Column(JSONB, nullable=False, default=dict)
    status = db.Column(
        db.Enum(MonitoringPlanStatus),
        nullable=False,
        default=MonitoringPlanStatus.ACTIVE,
    )
    last_report_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = db.relationship('Agent', backref=db.backref('monitoring_plans', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_post_market_monitoring_tenant', 'tenant_id'),
        db.Index('ix_post_market_monitoring_agent', 'agent_id'),
    )
