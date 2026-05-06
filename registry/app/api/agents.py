from flask import request, jsonify, g
from marshmallow import ValidationError
from uuid import UUID

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas import (
    AgentSchema,
    AgentCreateSchema,
    AgentUpdateSchema,
    AgentVersionSchema,
    AgentListSchema,
)
from app.services.audit_service import AuditService
from app.services.agent_service import (
    AgentService,
    AgentNotFoundError,
    AgentValidationError,
    DuplicateAgentError,
    GuardrailProfileError,
    AgentServiceError,
)


# Schema instances
agent_schema = AgentSchema()
agent_create_schema = AgentCreateSchema()
agent_update_schema = AgentUpdateSchema()
agent_version_schema = AgentVersionSchema()
agent_list_schema = AgentListSchema(many=True)


def get_current_user():
    """Get the current user from the JWT context."""
    user_info = getattr(g, 'current_user', None)
    if user_info:
        return user_info['username']
    return request.headers.get('X-User-ID', 'anonymous')


def get_tenant_id():
    """
    Get the tenant ID from the request context.
    In production, this would be extracted from OAuth2 token.
    """
    return request.headers.get('X-Tenant-ID', 'default')


@api_bp.route('/agents', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_agent():
    """
    Create a new agent.

    POST /v1/agents

    Request body: Agent metadata as per schema
    Returns: Created agent with 201 status
    """
    try:
        data = agent_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages,
            'requirement': 'REQ-SUB-001'
        }), 400

    # Set tenant from context if not provided
    if 'tenant_id' not in data or data['tenant_id'] == 'default':
        data['tenant_id'] = get_tenant_id()

    try:
        agent = AgentService.create_agent(data, created_by=get_current_user())
        AuditService.log('agent.created', 'agent', agent.id, agent.name)
        return jsonify(agent_schema.dump(agent)), 201

    except DuplicateAgentError as e:
        return jsonify({
            'error': 'Duplicate agent',
            'message': str(e),
            'requirement': 'REQ-SUB-002'
        }), 409

    except GuardrailProfileError as e:
        return jsonify({
            'error': 'Guardrail profile error',
            'message': str(e),
            'requirement': 'REQ-SUB-007'
        }), 400

    except AgentServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


@api_bp.route('/agents/<uuid:agent_id>', methods=['GET'])
@jwt_required
@role_required(GroupType.USER)
def get_agent(agent_id: UUID):
    """
    Retrieve an agent by ID.

    GET /v1/agents/{id}

    Returns: Agent details
    """
    try:
        agent = AgentService.get_agent(agent_id)
        return jsonify(agent_schema.dump(agent)), 200

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


@api_bp.route('/agents/<uuid:agent_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_agent(agent_id: UUID):
    """
    Update an existing agent.

    PUT /v1/agents/{id}

    Request body: Fields to update
    Returns: Updated agent

    Note: Updates may trigger re-evaluation depending on changed fields.
    """
    try:
        data = agent_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'messages': e.messages
        }), 400

    try:
        agent = AgentService.update_agent(
            agent_id,
            data,
            updated_by=get_current_user()
        )
        AuditService.log('agent.updated', 'agent', agent.id, agent.name)
        return jsonify(agent_schema.dump(agent)), 200

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except GuardrailProfileError as e:
        return jsonify({
            'error': 'Guardrail profile error',
            'message': str(e),
            'requirement': 'REQ-SUB-007'
        }), 400

    except AgentServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


@api_bp.route('/agents/<uuid:agent_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_agent(agent_id: UUID):
    """
    Decommission an agent (soft delete).

    DELETE /v1/agents/{id}

    Returns: 204 No Content on success

    Note: Agents are soft-deleted and can still be retrieved
    for audit purposes.
    """
    try:
        AgentService.delete_agent(agent_id)
        AuditService.log('agent.deleted', 'agent', agent_id)
        return '', 204

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except AgentServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


@api_bp.route('/agents', methods=['GET'])
@jwt_required
@role_required(GroupType.USER)
def list_agents():
    """
    List agents with optional filtering.

    GET /v1/agents

    Query parameters:
    - status: Filter by agent status
    - team_id: Filter by team
    - include_deleted: Include soft-deleted agents (default: false)
    - page: Page number (default: 1)
    - per_page: Items per page (default: 20, max: 100)

    Returns: Paginated list of agents
    """
    from app.models import AgentStatus

    # Parse query parameters
    status_param = request.args.get('status')
    status = AgentStatus(status_param) if status_param else None

    team_id = request.args.get('team_id')
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    agents, total, pages = AgentService.list_agents(
        tenant_id=get_tenant_id(),
        status=status,
        team_id=team_id,
        include_deleted=include_deleted,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        'agents': agent_list_schema.dump(agents),
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }
    }), 200


@api_bp.route('/agents/<uuid:agent_id>/versions', methods=['GET'])
@jwt_required
@role_required(GroupType.USER)
def list_agent_versions(agent_id: UUID):
    """
    List all versions of an agent.

    GET /v1/agents/{id}/versions

    Returns: List of agent versions
    """
    try:
        versions = AgentService.get_agent_versions(agent_id)
        return jsonify({
            'versions': agent_version_schema.dump(versions, many=True)
        }), 200

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


@api_bp.route('/agents/<uuid:agent_id>/versions/<version>', methods=['GET'])
@jwt_required
@role_required(GroupType.USER)
def get_agent_version(agent_id: UUID, version: str):
    """
    Retrieve a specific version of an agent.

    GET /v1/agents/{id}/versions/{version}

    Returns: Agent version details including snapshot
    """
    try:
        version_record = AgentService.get_agent_version(agent_id, version)
        return jsonify(agent_version_schema.dump(version_record)), 200

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404


@api_bp.route('/agents/<uuid:agent_id>/submit', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def submit_agent(agent_id: UUID):
    """
    Submit an agent for review.

    POST /v1/agents/{id}/submit

    Transitions agent from DRAFT to SUBMITTED status.
    Returns: Updated agent
    """
    try:
        agent = AgentService.submit_agent(agent_id)
        AuditService.log('agent.submitted', 'agent', agent.id, agent.name)
        return jsonify(agent_schema.dump(agent)), 200

    except AgentNotFoundError as e:
        return jsonify({
            'error': 'Not found',
            'message': str(e)
        }), 404

    except AgentValidationError as e:
        return jsonify({
            'error': 'Validation error',
            'message': str(e)
        }), 400

    except AgentServiceError as e:
        return jsonify({
            'error': 'Service error',
            'message': str(e)
        }), 500


# Error handlers for the API blueprint
@api_bp.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400


@api_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found', 'message': str(error)}), 404


@api_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500
