"""REST endpoints for stage-based guardrail configurations."""

from flask import g, request, jsonify
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.guardrail_config import (
    GuardrailConfigCreateSchema,
    GuardrailConfigUpdateSchema,
    GuardrailConfigSchema,
    GuardrailConfigListSchema,
    GuardrailConfigEntryCreateSchema,
    GuardrailConfigEntrySchema,
)
from app.services.guardrail_config_service import (
    GuardrailConfigService,
    GuardrailConfigNotFoundError,
    GuardrailConfigValidationError,
)


# --- Config CRUD ---

@api_bp.route('/guardrail-configs', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_guardrail_configs():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result = GuardrailConfigService.list_configs(tenant_id, page, per_page)
    schema = GuardrailConfigListSchema(many=True)
    return jsonify({
        'configs': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })


@api_bp.route('/guardrail-configs', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_guardrail_config():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')
    try:
        data = GuardrailConfigCreateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    config = GuardrailConfigService.create_config(data, identity, tenant_id)
    return jsonify(GuardrailConfigSchema().dump(config)), 201


@api_bp.route('/guardrail-configs/<uuid:config_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_guardrail_config(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        config = GuardrailConfigService.get_config(config_id, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailConfigSchema().dump(config))


@api_bp.route('/guardrail-configs/<uuid:config_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_guardrail_config(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        data = GuardrailConfigUpdateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        config = GuardrailConfigService.update_config(config_id, data, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailConfigSchema().dump(config))


@api_bp.route('/guardrail-configs/<uuid:config_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_guardrail_config(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        GuardrailConfigService.delete_config(config_id, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except GuardrailConfigValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'status': 'deleted'})


# --- Activate / Clone / Diff ---

@api_bp.route('/guardrail-configs/<uuid:config_id>/activate', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def activate_guardrail_config(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')
    try:
        config = GuardrailConfigService.activate_config(config_id, identity, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailConfigSchema().dump(config))


@api_bp.route('/guardrail-configs/<uuid:config_id>/clone', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def clone_guardrail_config(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')
    data = request.json or {}
    new_name = data.get('name')
    if not new_name:
        return jsonify({'error': 'name is required'}), 400

    try:
        clone = GuardrailConfigService.clone_config(config_id, new_name, identity, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailConfigSchema().dump(clone)), 201


@api_bp.route('/guardrail-configs/diff', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def diff_guardrail_configs():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    config_a = request.args.get('config_a')
    config_b = request.args.get('config_b')
    if not config_a or not config_b:
        return jsonify({'error': 'config_a and config_b query params required'}), 400

    try:
        diff = GuardrailConfigService.diff_configs(config_a, config_b, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(diff)


# --- Entry CRUD ---

@api_bp.route('/guardrail-configs/<uuid:config_id>/entries', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_config_entries(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        entries = GuardrailConfigService.list_entries(config_id, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    schema = GuardrailConfigEntrySchema(many=True)
    return jsonify({'entries': schema.dump(entries)})


@api_bp.route('/guardrail-configs/<uuid:config_id>/entries', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def add_config_entry(config_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        data = GuardrailConfigEntryCreateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        entry = GuardrailConfigService.add_entry(config_id, data, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(GuardrailConfigEntrySchema().dump(entry)), 201


@api_bp.route('/guardrail-configs/<uuid:config_id>/entries/<uuid:entry_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def remove_config_entry(config_id, entry_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        GuardrailConfigService.remove_entry(config_id, entry_id, tenant_id)
    except GuardrailConfigNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify({'status': 'deleted'})
