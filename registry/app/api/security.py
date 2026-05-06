"""
API routes for security testing functionality.

Provides endpoints for:
- Security scans (trigger, list, get)
- Security policies (CRUD)
- Security test cases (CRUD - custom tests)
"""

import logging
import threading

from flask import request, jsonify, current_app, g
from marshmallow import ValidationError
from uuid import UUID

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas import (
    SecurityScanSchema,
    SecurityScanTriggerSchema,
    SecurityScanListSchema,
    SecurityScanResultSchema,
    SecurityPolicySchema,
    SecurityPolicyCreateSchema,
    SecurityPolicyUpdateSchema,
    SecurityPolicyListSchema,
    SecurityTestCaseSchema,
    SecurityTestCaseCreateSchema,
    SecurityTestCaseUpdateSchema,
    SecurityTestCaseListSchema,
)
from app.services.security_service import (
    SecurityService,
    SecurityScanNotFoundError,
    SecurityPolicyNotFoundError,
    SecurityTestCaseNotFoundError,
    ScanAlreadyInProgressError,
    AgentNotEligibleForScanError,
    CannotModifyBuiltinError,
    SecurityServiceError,
)
from app.models import ScanStatus, ScanType
from app.services.audit_service import AuditService


# Schema instances
scan_schema = SecurityScanSchema()
scan_trigger_schema = SecurityScanTriggerSchema()
scan_list_schema = SecurityScanListSchema(many=True)
scan_result_schema = SecurityScanResultSchema(many=True)

policy_schema = SecurityPolicySchema()
policy_create_schema = SecurityPolicyCreateSchema()
policy_update_schema = SecurityPolicyUpdateSchema()
policy_list_schema = SecurityPolicyListSchema(many=True)

test_case_schema = SecurityTestCaseSchema()
test_case_create_schema = SecurityTestCaseCreateSchema()
test_case_update_schema = SecurityTestCaseUpdateSchema()
test_case_list_schema = SecurityTestCaseListSchema(many=True)


def get_current_user():
    """Get the current user from the JWT context."""
    user_info = getattr(g, 'current_user', None)
    if user_info:
        return user_info['username']
    return request.headers.get('X-User-ID', 'anonymous')


def get_tenant_id():
    """Get the tenant ID from the request context."""
    return request.headers.get('X-Tenant-ID', 'default')


# ============================================================================
# Security Scans
# ============================================================================

@api_bp.route('/agents/<uuid:agent_id>/security-scans', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def trigger_security_scan(agent_id: UUID):
    """
    Trigger a security scan for an agent.

    POST /v1/agents/{id}/security-scans

    Request body (optional):
        - policy_id: UUID of policy to use (optional, uses default if not specified)
        - scan_types: List of specific scan types to run (optional, runs all if not specified)

    Returns: Created scan with 201 status
    """
    data = {}
    if request.json:
        try:
            data = scan_trigger_schema.load(request.json)
        except ValidationError as e:
            return jsonify({
                'error': 'Validation error',
                'messages': e.messages
            }), 400

    try:
        scan = SecurityService.trigger_scan(
            agent_id=agent_id,
            policy_id=data.get('policy_id'),
            scan_types=data.get('scan_types'),
            triggered_by='manual',
            initiated_by=get_current_user(),
        )

        AuditService.log('security_scan.triggered', 'security_scan', scan.id,
                         detail={'agent_id': str(agent_id)})

        # Execute the scan in a background thread
        app = current_app._get_current_object()
        scan_id = scan.id

        def run_scan():
            with app.app_context():
                try:
                    SecurityService.execute_scan(scan_id)
                except Exception as exec_error:
                    logging.error(f"Scan execution failed: {exec_error}")

        thread = threading.Thread(target=run_scan, daemon=True)
        thread.start()

        return jsonify(scan_schema.dump(scan)), 201

    except AgentNotEligibleForScanError as e:
        return jsonify({
            'error': 'Agent not eligible',
            'message': str(e)
        }), 400

    except ScanAlreadyInProgressError as e:
        return jsonify({
            'error': 'Scan already in progress',
            'message': str(e)
        }), 409

    except SecurityPolicyNotFoundError as e:
        return jsonify({
            'error': 'Policy not found',
            'message': str(e)
        }), 404

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


@api_bp.route('/agents/<uuid:agent_id>/security-scans', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_security_scans(agent_id: UUID):
    """
    List security scan history for an agent.

    GET /v1/agents/{id}/security-scans

    Query parameters:
        - status: Filter by scan status
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20, max: 100)

    Returns: Paginated list of scans
    """
    status_param = request.args.get('status')
    status = ScanStatus(status_param) if status_param else None
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    scans, total, pages = SecurityService.list_scans(
        agent_id=agent_id,
        status=status,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'scans': scan_list_schema.dump(scans),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/security-scans/<uuid:scan_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_security_scan(agent_id: UUID, scan_id: UUID):
    """
    Get security scan details with results.

    GET /v1/agents/{id}/security-scans/{scan_id}

    Returns: Scan details including all test results
    """
    try:
        scan = SecurityService.get_scan(scan_id)

        # Verify scan belongs to the agent
        if scan.agent_id != agent_id:
            return jsonify({
                'error': 'Not found',
                'message': f"Scan '{scan_id}' not found for agent '{agent_id}'"
            }), 404

        # Include results in response
        result = scan_schema.dump(scan)
        result['results'] = scan_result_schema.dump(list(scan.results))

        return jsonify(result), 200

    except SecurityScanNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


# ============================================================================
# Security Policies
# ============================================================================

@api_bp.route('/security-policies', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_security_policies():
    """
    List security policies.

    GET /v1/security-policies

    Query parameters:
        - is_active: Filter by active status
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20, max: 100)

    Returns: Paginated list of policies
    """
    is_active_param = request.args.get('is_active')
    is_active = is_active_param.lower() == 'true' if is_active_param else None
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    policies, total, pages = SecurityService.list_policies(
        tenant_id=get_tenant_id(),
        is_active=is_active,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'policies': policy_list_schema.dump(policies),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/security-policies/<uuid:policy_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_security_policy(policy_id: UUID):
    """
    Get security policy details.

    GET /v1/security-policies/{id}

    Returns: Policy details
    """
    try:
        policy = SecurityService.get_policy(
            policy_id=policy_id,
            tenant_id=get_tenant_id()
        )
        return jsonify(policy_schema.dump(policy)), 200

    except SecurityPolicyNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


@api_bp.route('/security-policies', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_security_policy():
    """
    Create a custom security policy.

    POST /v1/security-policies

    Request body: Policy configuration

    Returns: Created policy with 201 status
    """
    try:
        data = policy_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages
        }), 400

    try:
        policy = SecurityService.create_policy(
            data=data,
            tenant_id=get_tenant_id()
        )
        return jsonify(policy_schema.dump(policy)), 201

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400


@api_bp.route('/security-policies/<uuid:policy_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_security_policy(policy_id: UUID):
    """
    Update a security policy.

    PUT /v1/security-policies/{id}

    Request body: Fields to update

    Returns: Updated policy
    """
    try:
        data = policy_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages
        }), 400

    try:
        policy = SecurityService.update_policy(
            policy_id=policy_id,
            data=data,
            tenant_id=get_tenant_id()
        )
        return jsonify(policy_schema.dump(policy)), 200

    except SecurityPolicyNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400


@api_bp.route('/security-policies/<uuid:policy_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_security_policy(policy_id: UUID):
    """
    Delete a security policy.

    DELETE /v1/security-policies/{id}

    Returns: 204 No Content on success

    Note: Only custom (tenant-specific) policies can be deleted.
    """
    try:
        SecurityService.delete_policy(
            policy_id=policy_id,
            tenant_id=get_tenant_id()
        )
        return '', 204

    except SecurityPolicyNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400


# ============================================================================
# Security Test Cases
# ============================================================================

@api_bp.route('/security-test-cases/reset', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def reset_security_test_cases():
    """
    Reset built-in security test cases to OWASP defaults.

    POST /v1/security-test-cases/reset

    Returns: Summary of created/updated counts
    """
    try:
        result = SecurityService.reset_to_defaults(
            tenant_id=get_tenant_id()
        )
        AuditService.log('security_test_case.defaults_reset', 'security_test_case',
                         detail=result)
        return jsonify(result), 200

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


@api_bp.route('/security-test-cases', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_security_test_cases():
    """
    List security test cases (built-in + custom).

    GET /v1/security-test-cases

    Query parameters:
        - scan_type: Filter by scan type
        - is_builtin: Filter built-in (true) or custom (false) tests
        - is_active: Filter by active status
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20, max: 100)

    Returns: Paginated list of test cases
    """
    scan_type = request.args.get('scan_type')
    is_builtin_param = request.args.get('is_builtin')
    is_active_param = request.args.get('is_active')

    is_builtin = None
    if is_builtin_param is not None:
        is_builtin = is_builtin_param.lower() == 'true'

    is_active = None
    if is_active_param is not None:
        is_active = is_active_param.lower() == 'true'

    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    test_cases, total, pages = SecurityService.list_test_cases(
        tenant_id=get_tenant_id(),
        scan_type=scan_type,
        is_builtin=is_builtin,
        is_active=is_active,
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


@api_bp.route('/security-test-cases/<test_case_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_security_test_case(test_case_id: str):
    """
    Get security test case details.

    GET /v1/security-test-cases/{id}

    Returns: Test case details
    """
    try:
        test_case = SecurityService.get_test_case(
            test_case_id=test_case_id,
            tenant_id=get_tenant_id()
        )
        return jsonify(test_case_schema.dump(test_case)), 200

    except SecurityTestCaseNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


@api_bp.route('/security-test-cases', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_security_test_case():
    """
    Create a custom security test case.

    POST /v1/security-test-cases

    Request body: Test case definition

    Returns: Created test case with 201 status
    """
    try:
        data = test_case_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages
        }), 400

    try:
        test_case = SecurityService.create_test_case(
            data=data,
            tenant_id=get_tenant_id(),
            created_by=get_current_user()
        )
        AuditService.log('security_test_case.created', 'security_test_case',
                         resource_name=test_case.name)
        return jsonify(test_case_schema.dump(test_case)), 201

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400


@api_bp.route('/security-test-cases/<test_case_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_security_test_case(test_case_id: str):
    """
    Update a custom security test case.

    PUT /v1/security-test-cases/{id}

    Request body: Fields to update

    Returns: Updated test case

    Note: Built-in test cases cannot be modified.
    """
    try:
        data = test_case_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages
        }), 400

    try:
        test_case = SecurityService.update_test_case(
            test_case_id=test_case_id,
            data=data,
            tenant_id=get_tenant_id()
        )
        AuditService.log('security_test_case.updated', 'security_test_case',
                         resource_name=test_case.name)
        return jsonify(test_case_schema.dump(test_case)), 200

    except SecurityTestCaseNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except CannotModifyBuiltinError as e:
        return jsonify({
            'error': 'Cannot modify built-in test',
            'message': str(e)
        }), 403

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400


@api_bp.route('/security-test-cases/<test_case_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_security_test_case(test_case_id: str):
    """
    Delete a custom security test case.

    DELETE /v1/security-test-cases/{id}

    Returns: 204 No Content on success

    Note: Built-in test cases cannot be deleted.
    """
    try:
        SecurityService.delete_test_case(
            test_case_id=test_case_id,
            tenant_id=get_tenant_id()
        )
        AuditService.log('security_test_case.deleted', 'security_test_case',
                         detail={'test_case_id': test_case_id})
        return '', 204

    except SecurityTestCaseNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except CannotModifyBuiltinError as e:
        return jsonify({
            'error': 'Cannot delete built-in test',
            'message': str(e)
        }), 403

    except SecurityServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 400
