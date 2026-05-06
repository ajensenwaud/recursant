import logging

from flask import jsonify, request, g, send_file
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.euai import (
    EUAIClassificationSchema,
    EUAIClassificationCreateSchema,
    EUAIClassificationUpdateSchema,
    ComplianceRequirementSchema,
    ComplianceStatusSchema,
    ComplianceStatusUpdateSchema,
    AnnexIVDocumentSchema,
    AnnexIVDocumentListSchema,
    AnnexIVManualSectionsUpdateSchema,
    ConformityAssessmentSchema,
    ConformityAssessmentCreateSchema,
    ConformityFindingSchema,
    PostMarketMonitoringPlanSchema,
    PostMarketMonitoringPlanCreateSchema,
    GapAnalysisSchema,
    ComplianceDashboardSchema,
)
from app.services.euai_compliance_service import (
    EUAIComplianceService,
    EUAIComplianceServiceError,
    ClassificationNotFoundError,
    ClassificationAlreadyExistsError,
    RequirementNotFoundError,
)
from app.services.annex_iv_service import (
    AnnexIVService,
    AnnexIVServiceError,
    AnnexIVNotFoundError,
)
from app.services.conformity_service import (
    ConformityService,
    ConformityServiceError,
    ConformityNotFoundError,
)
from app.services.post_market_service import (
    PostMarketService,
    PostMarketServiceError,
    MonitoringPlanNotFoundError,
)

logger = logging.getLogger(__name__)

classification_schema = EUAIClassificationSchema()
classification_create_schema = EUAIClassificationCreateSchema()
classification_update_schema = EUAIClassificationUpdateSchema()
requirement_schema = ComplianceRequirementSchema()
compliance_status_schema = ComplianceStatusSchema()
compliance_status_update_schema = ComplianceStatusUpdateSchema()
annex_iv_schema = AnnexIVDocumentSchema()
annex_iv_list_schema = AnnexIVDocumentListSchema()
manual_sections_schema = AnnexIVManualSectionsUpdateSchema()
conformity_schema = ConformityAssessmentSchema()
conformity_create_schema = ConformityAssessmentCreateSchema()
finding_schema = ConformityFindingSchema()
monitoring_plan_schema = PostMarketMonitoringPlanSchema()
monitoring_plan_create_schema = PostMarketMonitoringPlanCreateSchema()
gap_analysis_schema = GapAnalysisSchema()
dashboard_schema = ComplianceDashboardSchema()


def get_current_user():
    user_info = getattr(g, 'current_user', None)
    if user_info:
        return user_info['username']
    return request.headers.get('X-User-ID', 'anonymous')


def get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


# ── Classification ─────────────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/euai-classification', methods=['GET'])
@jwt_required
def get_euai_classification(agent_id):
    try:
        classification = EUAIComplianceService.get_classification(agent_id)
        return jsonify(classification_schema.dump(classification)), 200
    except ClassificationNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404


@api_bp.route('/agents/<uuid:agent_id>/euai-classification', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def create_euai_classification(agent_id):
    try:
        data = classification_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        classification = EUAIComplianceService.classify_agent(
            agent_id, data, tenant_id=get_tenant_id(), classified_by=get_current_user()
        )
        return jsonify(classification_schema.dump(classification)), 201
    except ClassificationAlreadyExistsError as e:
        return jsonify({'error': 'Already exists', 'message': str(e)}), 409
    except EUAIComplianceServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/euai-classification', methods=['PUT'])
@jwt_required
@role_required(GroupType.APPROVER)
def update_euai_classification(agent_id):
    try:
        data = classification_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        classification = EUAIComplianceService.update_classification(
            agent_id, data, classified_by=get_current_user()
        )
        return jsonify(classification_schema.dump(classification)), 200
    except ClassificationNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except EUAIComplianceServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


# ── Compliance Status ──────────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/compliance', methods=['GET'])
@jwt_required
def get_compliance_statuses(agent_id):
    statuses = EUAIComplianceService.get_compliance_statuses(agent_id)
    return jsonify({
        'statuses': compliance_status_schema.dump(statuses, many=True),
        'total': len(statuses),
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/compliance/<string:requirement_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.APPROVER)
def update_compliance_status(agent_id, requirement_id):
    try:
        data = compliance_status_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        status = EUAIComplianceService.update_compliance_status(
            agent_id, requirement_id, data, assessed_by=get_current_user()
        )
        return jsonify(compliance_status_schema.dump(status)), 200
    except RequirementNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except EUAIComplianceServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/compliance/auto-assess', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def auto_assess_compliance(agent_id):
    try:
        updated_count = EUAIComplianceService.auto_assess_all(agent_id)
        return jsonify({
            'message': f'Auto-assessed {updated_count} requirements',
            'updated_count': updated_count,
        }), 200
    except (ClassificationNotFoundError, EUAIComplianceServiceError) as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


# ── Gap Analysis ───────────────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/compliance/gap-analysis', methods=['GET'])
@jwt_required
def get_gap_analysis(agent_id):
    try:
        analysis = EUAIComplianceService.get_gap_analysis(agent_id)
        return jsonify(analysis), 200
    except ClassificationNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404


# ── Annex IV Documents ─────────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/annex-iv', methods=['GET'])
@jwt_required
def list_annex_iv_documents(agent_id):
    docs = AnnexIVService.get_documents(agent_id)
    return jsonify({
        'documents': annex_iv_list_schema.dump(docs, many=True),
        'total': len(docs),
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/generate', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def generate_annex_iv(agent_id):
    try:
        doc = AnnexIVService.generate_document(
            agent_id, tenant_id=get_tenant_id(), generated_by=get_current_user()
        )
        return jsonify(annex_iv_schema.dump(doc)), 201
    except AnnexIVServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/<uuid:doc_id>', methods=['GET'])
@jwt_required
def get_annex_iv_document(agent_id, doc_id):
    try:
        doc = AnnexIVService.get_document(doc_id)
        return jsonify(annex_iv_schema.dump(doc)), 200
    except AnnexIVNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/<uuid:doc_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.APPROVER)
def update_annex_iv_document(agent_id, doc_id):
    try:
        data = manual_sections_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        doc = AnnexIVService.update_manual_sections(doc_id, data['manual_sections'])
        return jsonify(annex_iv_schema.dump(doc)), 200
    except AnnexIVNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except AnnexIVServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/<uuid:doc_id>/regenerate', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def regenerate_annex_iv(agent_id, doc_id):
    try:
        doc = AnnexIVService.regenerate_auto_sections(doc_id)
        return jsonify(annex_iv_schema.dump(doc)), 200
    except AnnexIVNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except AnnexIVServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/<uuid:doc_id>/pdf', methods=['POST'])
@jwt_required
def generate_annex_iv_pdf(agent_id, doc_id):
    try:
        pdf_path = AnnexIVService.generate_pdf(doc_id)
        return send_file(pdf_path, as_attachment=True)
    except AnnexIVNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except Exception as e:
        return jsonify({'error': 'PDF generation failed', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/annex-iv/<uuid:doc_id>/approve', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def approve_annex_iv(agent_id, doc_id):
    try:
        doc = AnnexIVService.approve_document(doc_id, approved_by=get_current_user())
        return jsonify(annex_iv_schema.dump(doc)), 200
    except AnnexIVNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except AnnexIVServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


# ── Conformity Assessment ──────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/conformity', methods=['GET'])
@jwt_required
def list_conformity_assessments(agent_id):
    assessments = ConformityService.get_assessments(agent_id)
    return jsonify({
        'assessments': conformity_schema.dump(assessments, many=True),
        'total': len(assessments),
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/conformity', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def create_conformity_assessment(agent_id):
    try:
        data = conformity_create_schema.load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        assessment = ConformityService.create_assessment(
            agent_id, data, tenant_id=get_tenant_id()
        )
        return jsonify(conformity_schema.dump(assessment)), 201
    except ConformityServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/conformity/<uuid:assessment_id>/findings', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def add_conformity_finding(agent_id, assessment_id):
    try:
        data = finding_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        assessment = ConformityService.add_finding(assessment_id, data)
        return jsonify(conformity_schema.dump(assessment)), 200
    except ConformityNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except ConformityServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


@api_bp.route('/agents/<uuid:agent_id>/conformity/<uuid:assessment_id>/declare', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def declare_conformity(agent_id, assessment_id):
    try:
        assessment = ConformityService.declare(assessment_id, declared_by=get_current_user())
        return jsonify(conformity_schema.dump(assessment)), 200
    except ConformityNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404
    except ConformityServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 400


# ── Post-Market Monitoring ─────────────────────────────────────────────

@api_bp.route('/agents/<uuid:agent_id>/monitoring', methods=['GET'])
@jwt_required
def get_monitoring_plan(agent_id):
    try:
        plan = PostMarketService.get_plan(agent_id)
        return jsonify(monitoring_plan_schema.dump(plan)), 200
    except MonitoringPlanNotFoundError as e:
        return jsonify({'error': 'Not found', 'message': str(e)}), 404


@api_bp.route('/agents/<uuid:agent_id>/monitoring', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def create_monitoring_plan(agent_id):
    try:
        data = monitoring_plan_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        plan = PostMarketService.create_plan(
            agent_id, data, tenant_id=get_tenant_id(), created_by=get_current_user()
        )
        return jsonify(monitoring_plan_schema.dump(plan)), 201
    except PostMarketServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/monitoring/report', methods=['POST'])
@jwt_required
def generate_monitoring_report(agent_id):
    days = request.json.get('days', 30) if request.json else 30

    try:
        report = PostMarketService.generate_report(agent_id, days=days)
        return jsonify(report), 200
    except PostMarketServiceError as e:
        return jsonify({'error': 'Service error', 'message': str(e)}), 500


# ── Dashboard & Requirements ──────────────────────────────────────────

@api_bp.route('/compliance/dashboard', methods=['GET'])
@jwt_required
def compliance_dashboard():
    tenant_id = get_tenant_id()
    dashboard = EUAIComplianceService.get_dashboard(tenant_id)
    return jsonify(dashboard), 200


@api_bp.route('/compliance/requirements', methods=['GET'])
@jwt_required
def list_compliance_requirements():
    requirements = EUAIComplianceService.get_requirements()
    return jsonify({
        'requirements': requirement_schema.dump(requirements, many=True),
        'total': len(requirements),
    }), 200
