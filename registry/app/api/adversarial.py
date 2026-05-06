"""Adversarial testing API endpoints."""

import logging
import threading

from flask import g, jsonify, request
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.adversarial import (
    AdversarialTestSuiteCreateSchema,
    AdversarialTestSuiteListSchema,
    AdversarialTestSuiteSchema,
    AdversarialTestSuiteUpdateSchema,
    AdversarialTestRunListSchema,
    AdversarialTestRunSchema,
    CustomAttackCreateSchema,
    CustomAttackImportSchema,
    CustomAttackListSchema,
    CustomAttackSchema,
    CustomAttackUpdateSchema,
)
from app.services.adversarial_service import (
    AdversarialNotFoundError,
    AdversarialService,
    AdversarialServiceError,
    AdversarialValidationError,
)

logger = logging.getLogger(__name__)

# Schema instances
suite_create_schema = AdversarialTestSuiteCreateSchema()
suite_update_schema = AdversarialTestSuiteUpdateSchema()
suite_schema = AdversarialTestSuiteSchema()
suite_list_schema = AdversarialTestSuiteListSchema(many=True)
run_schema = AdversarialTestRunSchema()
run_list_schema = AdversarialTestRunListSchema(many=True)
custom_attack_create_schema = CustomAttackCreateSchema()
custom_attack_update_schema = CustomAttackUpdateSchema()
custom_attack_schema = CustomAttackSchema()
custom_attack_list_schema = CustomAttackListSchema(many=True)
custom_attack_import_schema = CustomAttackImportSchema()


def _get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


# --- Suite CRUD ---

@api_bp.route('/adversarial-suites', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_adversarial_suite():
    """Create a new adversarial test suite."""
    try:
        data = suite_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    created_by = g.current_user.get('username', 'unknown')

    try:
        suite = AdversarialService.create_suite(data, created_by, tenant_id)
        return jsonify(suite_schema.dump(suite)), 201
    except AdversarialValidationError as e:
        return jsonify({'error': str(e)}), 400
    except AdversarialServiceError as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/adversarial-suites', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_adversarial_suites():
    """List adversarial test suites."""
    tenant_id = _get_tenant_id()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    items, total, pages = AdversarialService.list_suites(tenant_id, page, per_page)
    return jsonify({
        'suites': suite_list_schema.dump(items),
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    })


@api_bp.route('/adversarial-suites/<suite_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_adversarial_suite(suite_id):
    """Get adversarial test suite details."""
    tenant_id = _get_tenant_id()
    try:
        suite = AdversarialService.get_suite(suite_id, tenant_id)
        return jsonify(suite_schema.dump(suite))
    except AdversarialNotFoundError:
        return jsonify({'error': 'Suite not found'}), 404


@api_bp.route('/adversarial-suites/<suite_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_adversarial_suite(suite_id):
    """Update an adversarial test suite."""
    try:
        data = suite_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    tenant_id = _get_tenant_id()
    try:
        suite = AdversarialService.update_suite(suite_id, data, tenant_id)
        return jsonify(suite_schema.dump(suite))
    except AdversarialNotFoundError:
        return jsonify({'error': 'Suite not found'}), 404
    except AdversarialValidationError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/adversarial-suites/<suite_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_adversarial_suite(suite_id):
    """Soft-delete an adversarial test suite."""
    tenant_id = _get_tenant_id()
    try:
        AdversarialService.delete_suite(suite_id, tenant_id)
        return jsonify({'message': 'Suite deleted'}), 200
    except AdversarialNotFoundError:
        return jsonify({'error': 'Suite not found'}), 404


# --- Run management ---

@api_bp.route('/adversarial-suites/<suite_id>/run', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def trigger_adversarial_run(suite_id):
    """Trigger an adversarial test run (executes in background thread)."""
    tenant_id = _get_tenant_id()
    triggered_by = g.current_user.get('username', 'unknown')

    try:
        run = AdversarialService.trigger_run(suite_id, triggered_by, tenant_id)

        # Capture app ref while still in request context
        from flask import current_app
        app = current_app._get_current_object()

        # Execute in background thread
        def _execute():
            with app.app_context():
                try:
                    AdversarialService.execute_run(str(run.id), tenant_id)
                except Exception:
                    logger.exception("adversarial_run_failed run_id=%s", run.id)

        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()

        return jsonify(run_schema.dump(run)), 201
    except AdversarialNotFoundError:
        return jsonify({'error': 'Suite not found'}), 404
    except AdversarialServiceError as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/adversarial-suites/<suite_id>/runs', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_adversarial_runs(suite_id):
    """List runs for an adversarial test suite."""
    tenant_id = _get_tenant_id()
    try:
        runs = AdversarialService.list_runs(suite_id, tenant_id)
        return jsonify({'runs': run_list_schema.dump(runs)})
    except AdversarialNotFoundError:
        return jsonify({'error': 'Suite not found'}), 404


@api_bp.route('/adversarial-suites/<suite_id>/runs/<run_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_adversarial_run(suite_id, run_id):
    """Get a specific adversarial test run."""
    tenant_id = _get_tenant_id()
    try:
        run = AdversarialService.get_run(suite_id, run_id, tenant_id)
        return jsonify(run_schema.dump(run))
    except AdversarialNotFoundError:
        return jsonify({'error': 'Run not found'}), 404


# --- Alerts ---

@api_bp.route('/adversarial-alerts', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_adversarial_alerts():
    """List runs where the evasion rate threshold was breached."""
    tenant_id = _get_tenant_id()
    from app.models.adversarial import AdversarialTestRun
    runs = AdversarialTestRun.query.filter_by(
        tenant_id=tenant_id,
        threshold_breached=True,
    ).order_by(AdversarialTestRun.created_at.desc()).limit(50).all()
    return jsonify({'alerts': run_list_schema.dump(runs)})


# --- Custom Attack CRUD ---

@api_bp.route('/custom-attacks', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_custom_attack():
    """Create a custom attack entry."""
    try:
        data = custom_attack_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    tenant_id = _get_tenant_id()
    created_by = g.current_user.get('username', 'unknown')
    try:
        attack = AdversarialService.create_custom_attack(data, created_by, tenant_id)
        return jsonify(custom_attack_schema.dump(attack)), 201
    except AdversarialValidationError as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/custom-attacks', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_custom_attacks():
    """List custom attacks with optional filter by attack_type."""
    tenant_id = _get_tenant_id()
    attack_type = request.args.get('attack_type')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    items, total, pages = AdversarialService.list_custom_attacks(
        tenant_id, attack_type=attack_type, page=page, per_page=per_page,
    )
    return jsonify({
        'attacks': custom_attack_list_schema.dump(items),
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    })


@api_bp.route('/custom-attacks/<attack_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_custom_attack(attack_id):
    """Get a custom attack by ID."""
    tenant_id = _get_tenant_id()
    try:
        attack = AdversarialService.get_custom_attack(attack_id, tenant_id)
        return jsonify(custom_attack_schema.dump(attack))
    except AdversarialNotFoundError:
        return jsonify({'error': 'Custom attack not found'}), 404


@api_bp.route('/custom-attacks/<attack_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_custom_attack(attack_id):
    """Update a custom attack."""
    try:
        data = custom_attack_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    tenant_id = _get_tenant_id()
    try:
        attack = AdversarialService.update_custom_attack(attack_id, data, tenant_id)
        return jsonify(custom_attack_schema.dump(attack))
    except AdversarialNotFoundError:
        return jsonify({'error': 'Custom attack not found'}), 404


@api_bp.route('/custom-attacks/<attack_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_custom_attack(attack_id):
    """Soft-delete a custom attack."""
    tenant_id = _get_tenant_id()
    try:
        AdversarialService.delete_custom_attack(attack_id, tenant_id)
        return jsonify({'message': 'Custom attack deleted'}), 200
    except AdversarialNotFoundError:
        return jsonify({'error': 'Custom attack not found'}), 404


@api_bp.route('/custom-attacks/import', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def import_custom_attacks():
    """Bulk import custom attacks from JSON."""
    try:
        data = custom_attack_import_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400
    tenant_id = _get_tenant_id()
    created_by = g.current_user.get('username', 'unknown')
    result = AdversarialService.import_custom_attacks(data['attacks'], created_by, tenant_id)
    return jsonify(result), 200


@api_bp.route('/custom-attacks/export', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def export_custom_attacks():
    """Export custom attacks as JSON."""
    tenant_id = _get_tenant_id()
    attack_type = request.args.get('attack_type')
    attacks = AdversarialService.export_custom_attacks(tenant_id, attack_type=attack_type)
    return jsonify({'attacks': attacks, 'count': len(attacks)})
