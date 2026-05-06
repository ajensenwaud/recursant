"""
Audit log API endpoints.

Provides read-only access to immutable audit log entries.
Only administrators can view audit logs.
No POST/PUT/DELETE endpoints — entries are immutable by design.
"""

from datetime import datetime

from flask import request, jsonify

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.audit import AuditLogSchema, AuditLogListSchema
from app.services.audit_service import AuditService


audit_log_schema = AuditLogSchema()
audit_log_list_schema = AuditLogListSchema(many=True)


def get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


@api_bp.route('/audit-logs', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def list_audit_logs():
    """
    List audit log entries with filters.

    GET /v1/audit-logs

    Query parameters:
        - action: Filter by action (e.g. agent.created)
        - resource_type: Filter by resource type (e.g. agent, user)
        - user_id: Filter by acting user
        - date_from: ISO datetime lower bound
        - date_to: ISO datetime upper bound
        - page: Page number (default: 1)
        - per_page: Items per page (default: 50, max: 100)
    """
    action = request.args.get('action')
    resource_type = request.args.get('resource_type')
    user_id = request.args.get('user_id')
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 50)), 100)

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.fromisoformat(date_from_str)
        except ValueError:
            return jsonify({'error': 'Invalid date_from format'}), 400
    if date_to_str:
        try:
            date_to = datetime.fromisoformat(date_to_str)
        except ValueError:
            return jsonify({'error': 'Invalid date_to format'}), 400

    logs, total, pages = AuditService.list_logs(
        tenant_id=get_tenant_id(),
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'logs': audit_log_list_schema.dump(logs),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/audit-logs/<uuid:log_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_audit_log(log_id):
    """
    Get a single audit log entry with full detail.

    GET /v1/audit-logs/{id}
    """
    entry = AuditService.get_log(log_id)
    if not entry:
        return jsonify({'error': 'Audit log entry not found'}), 404

    # Verify tenant access
    if entry.tenant_id != get_tenant_id():
        return jsonify({'error': 'Audit log entry not found'}), 404

    return jsonify(audit_log_schema.dump(entry)), 200
