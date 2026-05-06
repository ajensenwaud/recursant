"""Guardrail management API endpoints."""

import logging
from datetime import datetime, timezone

from flask import g, jsonify, request
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.guardrail import (
    GuardrailAssignmentCreateSchema,
    GuardrailAssignmentSchema,
    GuardrailCreateSchema,
    GuardrailListSchema,
    GuardrailSchema,
    GuardrailTestRunCreateSchema,
    GuardrailTestRunSchema,
    GuardrailUpdateSchema,
)
from app.services.guardrail_service import (
    GuardrailNotFoundError,
    GuardrailService,
    GuardrailServiceError,
    GuardrailValidationError,
)
from app.services.guardrail_observability_service import GuardrailObservabilityService

logger = logging.getLogger(__name__)

# Schema instances
create_schema = GuardrailCreateSchema()
update_schema = GuardrailUpdateSchema()
guardrail_schema = GuardrailSchema()
list_schema = GuardrailListSchema(many=True)
assignment_create_schema = GuardrailAssignmentCreateSchema()
assignment_schema = GuardrailAssignmentSchema(many=True)
test_run_create_schema = GuardrailTestRunCreateSchema()
test_run_schema = GuardrailTestRunSchema()
test_run_list_schema = GuardrailTestRunSchema(many=True)


def _get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


# --- CRUD ---

@api_bp.route('/guardrails', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_guardrails():
    """List guardrails with optional filtering."""
    tenant_id = _get_tenant_id()
    type_filter = request.args.get('type')
    status_filter = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    pagination = GuardrailService.list_guardrails(
        tenant_id=tenant_id,
        type_filter=type_filter,
        status_filter=status_filter,
        page=page,
        per_page=per_page,
    )
    return jsonify({
        'guardrails': list_schema.dump(pagination.items),
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    })


@api_bp.route('/guardrails', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_guardrail():
    """Create a new guardrail."""
    try:
        data = create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    created_by = g.current_user.get('username', 'unknown')

    try:
        guardrail = GuardrailService.create_guardrail(data, created_by, tenant_id)
        return jsonify(guardrail_schema.dump(guardrail)), 201
    except GuardrailValidationError as e:
        return jsonify({'error': str(e)}), 400
    except GuardrailServiceError as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/guardrails/<guardrail_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_guardrail(guardrail_id):
    """Get guardrail details."""
    tenant_id = _get_tenant_id()
    try:
        guardrail = GuardrailService.get_guardrail(guardrail_id, tenant_id)
        return jsonify(guardrail_schema.dump(guardrail))
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404


@api_bp.route('/guardrails/<guardrail_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_guardrail(guardrail_id):
    """Update a draft guardrail."""
    try:
        data = update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    try:
        guardrail = GuardrailService.update_guardrail(guardrail_id, data, tenant_id)
        return jsonify(guardrail_schema.dump(guardrail))
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404
    except GuardrailValidationError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/guardrails/<guardrail_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_guardrail(guardrail_id):
    """Soft-delete a guardrail."""
    tenant_id = _get_tenant_id()
    try:
        GuardrailService.delete_guardrail(guardrail_id, tenant_id)
        return jsonify({'message': 'Guardrail deleted'}), 200
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404


# --- Status transitions ---

@api_bp.route('/guardrails/<guardrail_id>/activate', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def activate_guardrail(guardrail_id):
    """Activate a draft guardrail."""
    tenant_id = _get_tenant_id()
    approved_by = g.current_user.get('username', 'unknown')
    try:
        guardrail = GuardrailService.activate_guardrail(guardrail_id, approved_by, tenant_id)
        return jsonify(guardrail_schema.dump(guardrail))
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404
    except GuardrailValidationError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/guardrails/<guardrail_id>/disable', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def disable_guardrail(guardrail_id):
    """Disable an active guardrail."""
    tenant_id = _get_tenant_id()
    try:
        guardrail = GuardrailService.disable_guardrail(guardrail_id, tenant_id)
        return jsonify(guardrail_schema.dump(guardrail))
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404
    except GuardrailValidationError as e:
        return jsonify({'error': str(e)}), 400


# --- Assignments ---

@api_bp.route('/guardrails/<guardrail_id>/assignments', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_assignments(guardrail_id):
    """List agent assignments for a guardrail."""
    tenant_id = _get_tenant_id()
    try:
        GuardrailService.get_guardrail(guardrail_id, tenant_id)
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404

    assignments = GuardrailService.list_assignments(guardrail_id, tenant_id)
    return jsonify({'assignments': assignment_schema.dump(assignments)})


@api_bp.route('/guardrails/<guardrail_id>/assignments', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_assignments(guardrail_id):
    """Assign guardrail to agent(s)."""
    try:
        data = assignment_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    try:
        assignments = GuardrailService.assign_to_agents(
            guardrail_id, data['agent_ids'], tenant_id,
        )
        return jsonify({'assignments': assignment_schema.dump(assignments)}), 201
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404
    except GuardrailValidationError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/guardrails/<guardrail_id>/assignments/<assignment_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_assignment(guardrail_id, assignment_id):
    """Remove an agent assignment."""
    tenant_id = _get_tenant_id()
    try:
        GuardrailService.remove_assignment(assignment_id, tenant_id)
        return jsonify({'message': 'Assignment removed'}), 200
    except GuardrailNotFoundError:
        return jsonify({'error': 'Assignment not found'}), 404


# --- Test runs ---

@api_bp.route('/guardrails/<guardrail_id>/test', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def run_guardrail_test(guardrail_id):
    """Execute a test run against a live agent."""
    try:
        data = test_run_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    initiated_by = g.current_user.get('username', 'unknown')

    try:
        test_run = GuardrailService.create_test_run(
            guardrail_id=guardrail_id,
            agent_id=data['agent_id'],
            test_inputs=data['test_inputs'],
            initiated_by=initiated_by,
            tenant_id=tenant_id,
        )
        return jsonify(test_run_schema.dump(test_run)), 201
    except GuardrailNotFoundError:
        return jsonify({'error': 'Guardrail not found'}), 404
    except GuardrailServiceError as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/guardrails/<guardrail_id>/test-runs', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_test_runs(guardrail_id):
    """List test run history for a guardrail."""
    tenant_id = _get_tenant_id()
    runs = GuardrailService.list_test_runs(guardrail_id, tenant_id)
    return jsonify({'test_runs': test_run_list_schema.dump(runs)})


@api_bp.route('/guardrails/<guardrail_id>/test-runs/<run_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_test_run(guardrail_id, run_id):
    """Get a specific test run result."""
    tenant_id = _get_tenant_id()
    try:
        run = GuardrailService.get_test_run(guardrail_id, run_id, tenant_id)
        return jsonify(test_run_schema.dump(run))
    except GuardrailNotFoundError:
        return jsonify({'error': 'Test run not found'}), 404


# --- Observability ---

def _parse_datetime(value):
    """Parse ISO datetime string, return None if invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


@api_bp.route('/guardrails/observability/summary', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def guardrail_observability_summary():
    """Get high-level observability summary."""
    tenant_id = _get_tenant_id()
    summary = GuardrailObservabilityService.get_summary(tenant_id)
    return jsonify(summary)


@api_bp.route('/guardrails/observability/trigger-rates', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def guardrail_observability_trigger_rates():
    """Get time-bucketed trigger rates."""
    tenant_id = _get_tenant_id()
    rates = GuardrailObservabilityService.get_trigger_rates(
        tenant_id=tenant_id,
        date_from=_parse_datetime(request.args.get('date_from')),
        date_to=_parse_datetime(request.args.get('date_to')),
        agent_name=request.args.get('agent_name'),
        guardrail_id=request.args.get('guardrail_id'),
        interval=request.args.get('interval', '1h'),
    )
    return jsonify({'trigger_rates': rates})


@api_bp.route('/guardrails/observability/latency', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def guardrail_observability_latency():
    """Get latency breakdown by mechanism."""
    tenant_id = _get_tenant_id()
    breakdown = GuardrailObservabilityService.get_latency_breakdown(
        tenant_id=tenant_id,
        date_from=_parse_datetime(request.args.get('date_from')),
        date_to=_parse_datetime(request.args.get('date_to')),
    )
    return jsonify({'latency': breakdown})


@api_bp.route('/guardrails/observability/top-blocked', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def guardrail_observability_top_blocked():
    """Get top blocked patterns."""
    tenant_id = _get_tenant_id()
    limit = request.args.get('limit', 20, type=int)
    patterns = GuardrailObservabilityService.get_top_blocked_patterns(
        tenant_id=tenant_id,
        date_from=_parse_datetime(request.args.get('date_from')),
        date_to=_parse_datetime(request.args.get('date_to')),
        limit=limit,
    )
    return jsonify({'patterns': patterns})


@api_bp.route('/guardrails/observability/drift', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def guardrail_observability_drift():
    """Get drift detection analysis."""
    tenant_id = _get_tenant_id()
    window_days = request.args.get('window_days', 7, type=int)
    drift = GuardrailObservabilityService.get_drift_detection(
        tenant_id=tenant_id,
        guardrail_id=request.args.get('guardrail_id'),
        window_days=window_days,
    )
    return jsonify({'drift': drift})
