"""REST endpoints for the unified guardrail metric store."""

from flask import g, request, jsonify
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.guardrail_metric import (
    GuardrailMetricCreateSchema,
    GuardrailMetricUpdateSchema,
    GuardrailMetricSchema,
    GuardrailMetricListSchema,
    GuardrailMetricScoreSchema,
    CreateGuardrailFromMetricSchema,
    RecordScoreSchema,
)
from app.schemas.guardrail import GuardrailSchema
from app.services.guardrail_metric_service import (
    GuardrailMetricService,
    GuardrailMetricNotFoundError,
    GuardrailMetricValidationError,
)


# --- CRUD ---

@api_bp.route('/guardrail-metrics', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_guardrail_metrics():
    """GET /v1/guardrail-metrics — list metrics with optional filters."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    category = request.args.get('category')
    mechanism = request.args.get('mechanism')
    builtin_only = request.args.get('builtin_only', 'false').lower() == 'true'

    result = GuardrailMetricService.list_metrics(
        tenant_id=tenant_id,
        category=category,
        mechanism=mechanism,
        builtin_only=builtin_only,
        page=page,
        per_page=per_page,
    )
    schema = GuardrailMetricListSchema(many=True)
    return jsonify({
        'metrics': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })


@api_bp.route('/guardrail-metrics', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_guardrail_metric():
    """POST /v1/guardrail-metrics — create a new metric."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')

    try:
        data = GuardrailMetricCreateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    metric = GuardrailMetricService.create_metric(
        data=data,
        created_by=identity,
        tenant_id=tenant_id,
    )
    return jsonify(GuardrailMetricSchema().dump(metric)), 201


@api_bp.route('/guardrail-metrics/<uuid:metric_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_guardrail_metric(metric_id):
    """GET /v1/guardrail-metrics/<id> — get metric details."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        metric = GuardrailMetricService.get_metric(metric_id, tenant_id)
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailMetricSchema().dump(metric))


@api_bp.route('/guardrail-metrics/<uuid:metric_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_guardrail_metric(metric_id):
    """PUT /v1/guardrail-metrics/<id> — update a metric."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')

    try:
        data = GuardrailMetricUpdateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        metric = GuardrailMetricService.update_metric(metric_id, data, tenant_id)
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except GuardrailMetricValidationError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify(GuardrailMetricSchema().dump(metric))


@api_bp.route('/guardrail-metrics/<uuid:metric_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_guardrail_metric(metric_id):
    """DELETE /v1/guardrail-metrics/<id> — soft-delete a metric."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        GuardrailMetricService.delete_metric(metric_id, tenant_id)
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except GuardrailMetricValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'status': 'deleted'}), 200


# --- Deploy as guardrail ---

@api_bp.route('/guardrail-metrics/<uuid:metric_id>/create-guardrail', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_guardrail_from_metric(metric_id):
    """POST /v1/guardrail-metrics/<id>/create-guardrail — deploy metric as a guardrail."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')

    try:
        data = CreateGuardrailFromMetricSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        guardrail = GuardrailMetricService.create_guardrail_from_metric(
            metric_id=metric_id,
            data=data,
            created_by=identity,
            tenant_id=tenant_id,
        )
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify(GuardrailSchema().dump(guardrail)), 201


# --- Generate test cases ---

@api_bp.route('/guardrail-metrics/<uuid:metric_id>/generate-test-cases', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def generate_metric_test_cases(metric_id):
    """POST /v1/guardrail-metrics/<id>/generate-test-cases — generate eval test cases."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        test_cases = GuardrailMetricService.generate_eval_test_cases(metric_id, tenant_id)
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify({'test_cases': test_cases, 'count': len(test_cases)})


# --- Scores ---

@api_bp.route('/guardrail-metrics/<uuid:metric_id>/scores', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_metric_scores(metric_id):
    """GET /v1/guardrail-metrics/<id>/scores — list scores for a metric."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    agent_name = request.args.get('agent_name')
    source = request.args.get('source')

    try:
        result = GuardrailMetricService.list_scores(
            metric_id=metric_id,
            tenant_id=tenant_id,
            agent_name=agent_name,
            source=source,
            page=page,
            per_page=per_page,
        )
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    schema = GuardrailMetricScoreSchema(many=True)
    return jsonify({
        'scores': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })


@api_bp.route('/guardrail-metrics/<uuid:metric_id>/scores', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def record_metric_score(metric_id):
    """POST /v1/guardrail-metrics/<id>/scores — record a score."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')

    try:
        data = RecordScoreSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        score = GuardrailMetricService.record_score(
            metric_id=metric_id,
            agent_name=data['agent_name'],
            score=data['score'],
            source=data.get('source', 'evaluation'),
            details=data.get('details'),
            tenant_id=tenant_id,
        )
    except GuardrailMetricNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    return jsonify(GuardrailMetricScoreSchema().dump(score)), 201
