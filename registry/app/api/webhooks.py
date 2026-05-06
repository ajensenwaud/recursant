"""REST endpoints for webhook management."""

from flask import g, request, jsonify
from marshmallow import ValidationError

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.webhook import (
    WebhookEndpointCreateSchema,
    WebhookEndpointUpdateSchema,
    WebhookEndpointSchema,
    WebhookSubscriptionCreateSchema,
    WebhookSubscriptionSchema,
    WebhookDeliveryLogSchema,
)
from app.services.webhook_service import (
    WebhookService,
    WebhookNotFoundError,
)


# --- Endpoint CRUD ---

@api_bp.route('/webhooks', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_webhook_endpoints():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result = WebhookService.list_endpoints(tenant_id, page, per_page)
    schema = WebhookEndpointSchema(many=True)
    return jsonify({
        'endpoints': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })


@api_bp.route('/webhooks', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_webhook_endpoint():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    identity = g.current_user.get('username', 'unknown')
    try:
        data = WebhookEndpointCreateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    endpoint = WebhookService.create_endpoint(data, identity, tenant_id)
    return jsonify(WebhookEndpointSchema().dump(endpoint)), 201


@api_bp.route('/webhooks/<uuid:endpoint_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_webhook_endpoint(endpoint_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        endpoint = WebhookService.get_endpoint(endpoint_id, tenant_id)
    except WebhookNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(WebhookEndpointSchema().dump(endpoint))


@api_bp.route('/webhooks/<uuid:endpoint_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_webhook_endpoint(endpoint_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        data = WebhookEndpointUpdateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    try:
        endpoint = WebhookService.update_endpoint(endpoint_id, data, tenant_id)
    except WebhookNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(WebhookEndpointSchema().dump(endpoint))


@api_bp.route('/webhooks/<uuid:endpoint_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_webhook_endpoint(endpoint_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        WebhookService.delete_endpoint(endpoint_id, tenant_id)
    except WebhookNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify({'status': 'deleted'})


@api_bp.route('/webhooks/<uuid:endpoint_id>/test', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def test_webhook_endpoint(endpoint_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        result = WebhookService.test_endpoint(endpoint_id, tenant_id)
    except WebhookNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify(result)


# --- Subscriptions ---

@api_bp.route('/webhook-subscriptions', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_webhook_subscriptions():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    webhook_id = request.args.get('webhook_id')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result = WebhookService.list_subscriptions(
        tenant_id, webhook_id=webhook_id, page=page, per_page=per_page,
    )
    schema = WebhookSubscriptionSchema(many=True)
    return jsonify({
        'subscriptions': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })


@api_bp.route('/webhook-subscriptions', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_webhook_subscription():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        data = WebhookSubscriptionCreateSchema().load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation failed', 'details': e.messages}), 400

    sub = WebhookService.create_subscription(data, tenant_id)
    return jsonify(WebhookSubscriptionSchema().dump(sub)), 201


@api_bp.route('/webhook-subscriptions/<uuid:subscription_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_webhook_subscription(subscription_id):
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    try:
        WebhookService.delete_subscription(subscription_id, tenant_id)
    except WebhookNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify({'status': 'deleted'})


# --- Delivery logs ---

@api_bp.route('/webhook-delivery-logs', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def list_webhook_delivery_logs():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    subscription_id = request.args.get('subscription_id')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result = WebhookService.list_delivery_logs(
        tenant_id, subscription_id=subscription_id, page=page, per_page=per_page,
    )
    schema = WebhookDeliveryLogSchema(many=True)
    return jsonify({
        'delivery_logs': schema.dump(result.items),
        'total': result.total,
        'page': result.page,
        'per_page': result.per_page,
        'pages': result.pages,
    })
