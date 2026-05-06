from marshmallow import Schema, fields, validate

from app.models.euai import (
    EUAIRiskCategory,
    EUAIUseDomain,
    ComplianceStatusValue,
    AnnexIVDocumentStatus,
    ConformityAssessmentType,
    ConformityAssessmentStatus,
    MonitoringPlanStatus,
    EvidenceType,
)


# ── Classification ─────────────────────────────────────────────────────

class EUAIClassificationSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    eu_risk_category = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EUAIRiskCategory]),
    )
    use_domain = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EUAIUseDomain]),
    )
    questionnaire_responses = fields.Dict(required=True)
    classification_rationale = fields.String(allow_none=True)
    is_confirmed = fields.Boolean(load_default=False)
    classified_by = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class EUAIClassificationCreateSchema(Schema):
    eu_risk_category = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EUAIRiskCategory]),
    )
    use_domain = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EUAIUseDomain]),
    )
    questionnaire_responses = fields.Dict(required=True)
    classification_rationale = fields.String(allow_none=True)
    is_confirmed = fields.Boolean(load_default=False)


class EUAIClassificationUpdateSchema(Schema):
    eu_risk_category = fields.String(
        validate=validate.OneOf([e.value for e in EUAIRiskCategory]),
    )
    use_domain = fields.String(
        validate=validate.OneOf([e.value for e in EUAIUseDomain]),
    )
    questionnaire_responses = fields.Dict()
    classification_rationale = fields.String(allow_none=True)
    is_confirmed = fields.Boolean()


# ── Compliance Requirement ─────────────────────────────────────────────

class ComplianceRequirementSchema(Schema):
    id = fields.String(dump_only=True)
    article_reference = fields.String()
    title = fields.String()
    description = fields.String()
    applicable_risk_categories = fields.List(fields.String())
    evidence_type = fields.String()
    auto_source = fields.String(allow_none=True)
    guidance = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)


# ── Compliance Status ──────────────────────────────────────────────────

class ComplianceStatusSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    requirement_id = fields.String(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    status = fields.String()
    evidence_data = fields.Dict(allow_none=True)
    notes = fields.String(allow_none=True)
    last_assessed_at = fields.DateTime(dump_only=True)
    assessed_by = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    requirement = fields.Nested(ComplianceRequirementSchema, dump_only=True)


class ComplianceStatusUpdateSchema(Schema):
    status = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in ComplianceStatusValue]),
    )
    evidence_data = fields.Dict(allow_none=True)
    notes = fields.String(allow_none=True)


# ── Annex IV Document ──────────────────────────────────────────────────

class AnnexIVDocumentSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    version = fields.Integer(dump_only=True)
    status = fields.String()
    document_data = fields.Dict()
    manual_sections = fields.Dict()
    signature = fields.String(dump_only=True)
    pdf_storage_path = fields.String(dump_only=True)
    approved_by = fields.String(dump_only=True)
    approved_at = fields.DateTime(dump_only=True)
    generated_by = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class AnnexIVDocumentListSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    version = fields.Integer(dump_only=True)
    status = fields.String()
    signature = fields.String(dump_only=True)
    approved_by = fields.String(dump_only=True)
    approved_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class AnnexIVManualSectionsUpdateSchema(Schema):
    manual_sections = fields.Dict(required=True)


# ── Conformity Assessment ──────────────────────────────────────────────

class ConformityAssessmentSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    assessment_type = fields.String()
    status = fields.String()
    compliance_snapshot = fields.Dict()
    findings = fields.List(fields.Dict())
    declaration_date = fields.DateTime(dump_only=True)
    declared_by = fields.String(dump_only=True)
    document_id = fields.UUID(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ConformityAssessmentCreateSchema(Schema):
    assessment_type = fields.String(
        load_default='self',
        validate=validate.OneOf([e.value for e in ConformityAssessmentType]),
    )
    document_id = fields.UUID(allow_none=True)


class ConformityFindingSchema(Schema):
    finding = fields.String(required=True)
    severity = fields.String(
        required=True,
        validate=validate.OneOf(['critical', 'major', 'minor', 'observation']),
    )
    requirement_id = fields.String(allow_none=True)


# ── Post-Market Monitoring ─────────────────────────────────────────────

class PostMarketMonitoringPlanSchema(Schema):
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    tenant_id = fields.String(dump_only=True)
    monitoring_config = fields.Dict()
    status = fields.String()
    last_report_at = fields.DateTime(dump_only=True)
    created_by = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PostMarketMonitoringPlanCreateSchema(Schema):
    monitoring_config = fields.Dict(required=True)


class PostMarketMonitoringReportSchema(Schema):
    agent_id = fields.UUID(dump_only=True)
    period_start = fields.DateTime(dump_only=True)
    period_end = fields.DateTime(dump_only=True)
    guardrail_events = fields.Dict(dump_only=True)
    adversarial_results = fields.Dict(dump_only=True)
    security_scans = fields.Dict(dump_only=True)
    drift_analysis = fields.Dict(dump_only=True)
    generated_at = fields.DateTime(dump_only=True)


# ── Gap Analysis ───────────────────────────────────────────────────────

class GapAnalysisItemSchema(Schema):
    requirement_id = fields.String()
    title = fields.String()
    article_reference = fields.String()
    status = fields.String()
    evidence_type = fields.String()
    auto_source = fields.String(allow_none=True)
    guidance = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)


class GapAnalysisSchema(Schema):
    agent_id = fields.UUID()
    compliance_score = fields.Float()
    total_requirements = fields.Integer()
    compliant_count = fields.Integer()
    non_compliant_count = fields.Integer()
    not_started_count = fields.Integer()
    in_progress_count = fields.Integer()
    gaps = fields.List(fields.Nested(GapAnalysisItemSchema))


# ── Dashboard ──────────────────────────────────────────────────────────

class ComplianceDashboardAgentSchema(Schema):
    agent_id = fields.UUID()
    agent_name = fields.String()
    eu_risk_category = fields.String()
    compliance_score = fields.Float()
    compliant_count = fields.Integer()
    total_applicable = fields.Integer()
    gap_count = fields.Integer()
    has_annex_iv = fields.Boolean()
    has_conformity = fields.Boolean()


class ComplianceDashboardSchema(Schema):
    agents = fields.List(fields.Nested(ComplianceDashboardAgentSchema))
    total_agents = fields.Integer()
    by_risk_category = fields.Dict()
    overall_compliance_pct = fields.Float()
