"""
API routes for evaluation endpoints.

Provides endpoints for evaluation suites, test cases, and evaluation execution.
"""

import logging
import threading

from flask import request, jsonify, current_app, g
from marshmallow import ValidationError
from uuid import UUID

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.evaluation import (
    # Suite schemas
    EvaluationSuiteSchema,
    EvaluationSuiteCreateSchema,
    EvaluationSuiteUpdateSchema,
    EvaluationSuiteListSchema,
    # Test case schemas
    EvaluationTestCaseSchema,
    EvaluationTestCaseCreateSchema,
    EvaluationTestCaseUpdateSchema,
    EvaluationTestCaseListSchema,
    # Evaluation schemas
    EvaluationSchema,
    EvaluationTriggerSchema,
    EvaluationListSchema,
)
from app.services.audit_service import AuditService
from app.services.evaluation_service import (
    EvaluationService,
    EvaluationServiceError,
    EvaluationNotFoundError,
    EvaluationSuiteNotFoundError,
    EvaluationTestCaseNotFoundError,
    EvaluationAlreadyInProgressError,
    AgentNotEligibleForEvaluationError,
    CannotModifyGlobalSuiteError,
)


# Schema instances
suite_schema = EvaluationSuiteSchema()
suite_create_schema = EvaluationSuiteCreateSchema()
suite_update_schema = EvaluationSuiteUpdateSchema()
suite_list_schema = EvaluationSuiteListSchema(many=True)

test_case_schema = EvaluationTestCaseSchema()
test_case_create_schema = EvaluationTestCaseCreateSchema()
test_case_update_schema = EvaluationTestCaseUpdateSchema()
test_case_list_schema = EvaluationTestCaseListSchema(many=True)

evaluation_schema = EvaluationSchema()
evaluation_trigger_schema = EvaluationTriggerSchema()
evaluation_list_schema = EvaluationListSchema(many=True)


def get_current_user():
    """Get the current user from the JWT context."""
    user_info = getattr(g, 'current_user', None)
    if user_info:
        return user_info['username']
    return request.headers.get('X-User-ID', 'anonymous')


def get_tenant_id():
    """Get tenant ID from request headers."""
    return request.headers.get('X-Tenant-ID', 'default')


# ============================================================================
# Evaluation Suites
# ============================================================================

@api_bp.route('/evaluation-suites', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_evaluation_suites():
    """List available evaluation suites."""
    tenant_id = get_tenant_id()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    is_active = request.args.get('is_active', type=lambda x: x.lower() == 'true')
    risk_tier = request.args.get('risk_tier')

    suites, total, pages = EvaluationService.list_suites(
        tenant_id=tenant_id,
        risk_tier=risk_tier,
        is_active=is_active,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'suites': suite_list_schema.dump(suites),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/evaluation-suites/<uuid:suite_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_evaluation_suite(suite_id: UUID):
    """Get evaluation suite details."""
    tenant_id = get_tenant_id()

    try:
        suite = EvaluationService.get_suite(suite_id, tenant_id)
        return jsonify(suite_schema.dump(suite)), 200
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404


@api_bp.route('/evaluation-suites', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_evaluation_suite():
    """Create a custom evaluation suite."""
    tenant_id = get_tenant_id()

    try:
        data = suite_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        suite = EvaluationService.create_suite(data, tenant_id)
        AuditService.log('evaluation_suite.created', 'evaluation_suite',
                         suite.id, suite.name)
        return jsonify(suite_schema.dump(suite)), 201
    except EvaluationServiceError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/evaluation-suites/<uuid:suite_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_evaluation_suite(suite_id: UUID):
    """Update an evaluation suite."""
    tenant_id = get_tenant_id()

    try:
        data = suite_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        suite = EvaluationService.update_suite(suite_id, data, tenant_id)
        AuditService.log('evaluation_suite.updated', 'evaluation_suite',
                         suite.id, suite.name)
        return jsonify(suite_schema.dump(suite)), 200
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except CannotModifyGlobalSuiteError as e:
        return jsonify({'error': str(e)}), 403
    except EvaluationServiceError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/evaluation-suites/<uuid:suite_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_evaluation_suite(suite_id: UUID):
    """Delete an evaluation suite (custom only)."""
    tenant_id = get_tenant_id()

    try:
        EvaluationService.delete_suite(suite_id, tenant_id)
        return '', 204
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except CannotModifyGlobalSuiteError as e:
        return jsonify({'error': str(e)}), 403


# ============================================================================
# Evaluation Test Cases
# ============================================================================

@api_bp.route('/evaluation-suites/<uuid:suite_id>/test-cases', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_test_cases(suite_id: UUID):
    """List test cases for a suite."""
    tenant_id = get_tenant_id()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)

    try:
        test_cases, total, pages = EvaluationService.list_test_cases(
            suite_id=suite_id,
            tenant_id=tenant_id,
            page=page,
            per_page=per_page,
        )

        return jsonify({
            'test_cases': test_case_list_schema.dump(test_cases),
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pages,
            }
        }), 200
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404


@api_bp.route('/evaluation-suites/<uuid:suite_id>/test-cases', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def add_test_case(suite_id: UUID):
    """Add a test case to a suite."""
    tenant_id = get_tenant_id()

    try:
        data = test_case_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        test_case = EvaluationService.add_test_case(suite_id, data, tenant_id)
        AuditService.log('evaluation_test_case.created', 'evaluation_test_case',
                         test_case.id, test_case.name,
                         detail={'suite_id': str(suite_id)})
        return jsonify(test_case_schema.dump(test_case)), 201
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except CannotModifyGlobalSuiteError as e:
        return jsonify({'error': str(e)}), 403
    except EvaluationServiceError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/evaluation-suites/<uuid:suite_id>/test-cases/<uuid:test_case_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_test_case(suite_id: UUID, test_case_id: UUID):
    """Get a single test case."""
    tenant_id = get_tenant_id()

    try:
        suite = EvaluationService.get_suite(suite_id, tenant_id)
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404

    from app.models.evaluation import EvaluationTestCase
    from sqlalchemy import and_
    test_case = EvaluationTestCase.query.filter(
        and_(
            EvaluationTestCase.id == test_case_id,
            EvaluationTestCase.suite_id == suite_id,
            EvaluationTestCase.deleted_at.is_(None)
        )
    ).first()

    if not test_case:
        return jsonify({'error': f"Test case '{test_case_id}' not found"}), 404

    return jsonify(test_case_schema.dump(test_case)), 200


@api_bp.route('/evaluation-suites/<uuid:suite_id>/test-cases/<uuid:test_case_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_test_case(suite_id: UUID, test_case_id: UUID):
    """Update a test case."""
    tenant_id = get_tenant_id()

    try:
        data = test_case_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        test_case = EvaluationService.update_test_case(
            suite_id, test_case_id, data, tenant_id
        )
        AuditService.log('evaluation_test_case.updated', 'evaluation_test_case',
                         test_case.id, test_case.name,
                         detail={'suite_id': str(suite_id)})
        return jsonify(test_case_schema.dump(test_case)), 200
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except EvaluationTestCaseNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except CannotModifyGlobalSuiteError as e:
        return jsonify({'error': str(e)}), 403
    except EvaluationServiceError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/evaluation-suites/<uuid:suite_id>/test-cases/<uuid:test_case_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_test_case(suite_id: UUID, test_case_id: UUID):
    """Delete a test case."""
    tenant_id = get_tenant_id()

    try:
        EvaluationService.delete_test_case(suite_id, test_case_id, tenant_id)
        AuditService.log('evaluation_test_case.deleted', 'evaluation_test_case',
                         test_case_id, detail={'suite_id': str(suite_id)})
        return '', 204
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except EvaluationTestCaseNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except CannotModifyGlobalSuiteError as e:
        return jsonify({'error': str(e)}), 403


# ============================================================================
# Evaluations
# ============================================================================

@api_bp.route('/agents/<uuid:agent_id>/evaluations', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def trigger_evaluation(agent_id: UUID):
    """Trigger an evaluation for an agent."""
    current_user = get_current_user()

    try:
        data = evaluation_trigger_schema.load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    suite_id = data.get('suite_id')

    try:
        evaluations_list = EvaluationService.trigger_evaluation(
            agent_id=agent_id,
            suite_id=suite_id,
            triggered_by='manual',
            initiated_by=current_user,
        )

        AuditService.log('evaluation.triggered', 'evaluation',
                         evaluations_list[0].id,
                         detail={'agent_id': str(agent_id),
                                 'suite_id': str(suite_id) if suite_id else None})

        # Execute each evaluation in a background thread
        app = current_app._get_current_object()

        for evaluation in evaluations_list:
            eval_id = evaluation.id

            def run_eval(eid=eval_id):
                with app.app_context():
                    try:
                        EvaluationService.execute_evaluation(eid)
                    except Exception as exec_error:
                        logging.error(f"Evaluation execution failed: {exec_error}")

            thread = threading.Thread(target=run_eval, daemon=True)
            thread.start()

        # Return first evaluation for backwards compatibility
        return jsonify(evaluation_schema.dump(evaluations_list[0])), 201

    except AgentNotEligibleForEvaluationError as e:
        return jsonify({'error': str(e)}), 404
    except EvaluationSuiteNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except EvaluationAlreadyInProgressError as e:
        return jsonify({'error': str(e)}), 409
    except EvaluationServiceError as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/agents/<uuid:agent_id>/evaluations', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_evaluations(agent_id: UUID):
    """List evaluation history for an agent."""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    evaluations, total, pages = EvaluationService.list_evaluations(
        agent_id=agent_id,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'evaluations': evaluation_list_schema.dump(evaluations),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/evaluations/<uuid:eval_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_evaluation(agent_id: UUID, eval_id: UUID):
    """Get evaluation with results."""
    try:
        evaluation = EvaluationService.get_evaluation(eval_id)

        # Verify agent_id matches
        if str(evaluation.agent_id) != str(agent_id):
            return jsonify({'error': 'Evaluation not found for this agent'}), 404

        return jsonify(evaluation_schema.dump(evaluation)), 200
    except EvaluationNotFoundError as e:
        return jsonify({'error': str(e)}), 404
