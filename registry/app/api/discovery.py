"""Discovery API endpoints for network agent auto-discovery."""

from flask import request, jsonify, g
from marshmallow import ValidationError
from uuid import UUID

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app.schemas.discovery import (
    DiscoveryScanCreateSchema,
    DiscoveryScanSchema,
    DiscoveryScanListSchema,
    DiscoveredAgentSchema,
    DiscoveredAgentListSchema,
    DiscoveredToolSchema,
    DiscoveredToolListSchema,
    OnboardAgentSchema,
    BulkOnboardSchema,
    OnboardToolSchema,
    DiscoveryScanScheduleSchema,
    DiscoveryScanScheduleCreateSchema,
    DiscoveryStatsSchema,
)
from app.services.discovery_service import (
    DiscoveryService,
    ScanNotFoundError,
    ScanAlreadyCompletedError,
    DiscoveredAgentNotFoundError,
    DiscoveredToolNotFoundError,
    AlreadyOnboardedError,
    AlreadyGovernedError,
    ScheduleNotFoundError,
)
from app.services.audit_service import AuditService


# Schema instances
scan_create_schema = DiscoveryScanCreateSchema()
scan_schema = DiscoveryScanSchema()
scan_list_schema = DiscoveryScanListSchema(many=True)
agent_schema = DiscoveredAgentSchema()
agent_list_schema = DiscoveredAgentListSchema(many=True)
tool_schema = DiscoveredToolSchema()
tool_list_schema = DiscoveredToolListSchema(many=True)
onboard_agent_schema = OnboardAgentSchema()
bulk_onboard_schema = BulkOnboardSchema()
onboard_tool_schema = OnboardToolSchema()
schedule_schema = DiscoveryScanScheduleSchema()
schedule_create_schema = DiscoveryScanScheduleCreateSchema()
stats_schema = DiscoveryStatsSchema()


def get_current_user():
    user_info = getattr(g, 'current_user', None)
    if user_info:
        return user_info['username']
    return request.headers.get('X-User-ID', 'anonymous')


def get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


def _parse_uuid(value, label='ID'):
    """Parse a UUID string, returning (uuid, None) or (None, error_response)."""
    try:
        return UUID(value), None
    except (ValueError, AttributeError):
        return None, (jsonify({'error': f'Invalid {label}'}), 400)


# ========================================================================
# Scan CRUD
# ========================================================================

@api_bp.route('/discovery/scans', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_discovery_scan():
    """Create and start a new discovery scan."""
    try:
        data = scan_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = get_tenant_id()
    scan = DiscoveryService.create_scan(data, tenant_id, created_by=get_current_user())
    AuditService.log('discovery.scan.created', 'discovery_scan', scan.id, scan.name)
    return jsonify(scan_schema.dump(scan)), 201


@api_bp.route('/discovery/scans', methods=['GET'])
@jwt_required
def list_discovery_scans():
    """List discovery scans with optional filtering."""
    tenant_id = get_tenant_id()
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    scans, total = DiscoveryService.list_scans(tenant_id, status=status, page=page, per_page=per_page)

    return jsonify({
        'scans': scan_list_schema.dump(scans),
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }), 200


@api_bp.route('/discovery/scans/<scan_id>', methods=['GET'])
@jwt_required
def get_discovery_scan(scan_id):
    """Get discovery scan details."""
    parsed_id, err = _parse_uuid(scan_id, 'scan ID')
    if err:
        return err
    try:
        scan = DiscoveryService.get_scan(parsed_id, get_tenant_id())
        return jsonify(scan_schema.dump(scan)), 200
    except ScanNotFoundError:
        return jsonify({'error': 'Scan not found'}), 404


@api_bp.route('/discovery/scans/<scan_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def cancel_discovery_scan(scan_id):
    """Cancel a running discovery scan."""
    parsed_id, err = _parse_uuid(scan_id, 'scan ID')
    if err:
        return err
    try:
        scan = DiscoveryService.cancel_scan(parsed_id, get_tenant_id())
        AuditService.log('discovery.scan.cancelled', 'discovery_scan', scan.id, scan.name)
        return jsonify(scan_schema.dump(scan)), 200
    except ScanNotFoundError:
        return jsonify({'error': 'Scan not found'}), 404
    except ScanAlreadyCompletedError as e:
        return jsonify({'error': str(e)}), 409


@api_bp.route('/discovery/scans/<scan_id>/rerun', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def rerun_discovery_scan(scan_id):
    """Re-run a completed discovery scan with the same config."""
    parsed_id, err = _parse_uuid(scan_id, 'scan ID')
    if err:
        return err
    try:
        scan = DiscoveryService.rerun_scan(parsed_id, get_tenant_id(), created_by=get_current_user())
        AuditService.log('discovery.scan.rerun', 'discovery_scan', scan.id, scan.name)
        return jsonify(scan_schema.dump(scan)), 201
    except ScanNotFoundError:
        return jsonify({'error': 'Original scan not found'}), 404


# ========================================================================
# Discovered Agents
# ========================================================================

@api_bp.route('/discovery/agents', methods=['GET'])
@jwt_required
def list_discovered_agents():
    """List discovered agents with optional governance status filter."""
    tenant_id = get_tenant_id()
    governance_status = request.args.get('governance_status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    agents, total = DiscoveryService.list_discovered_agents(
        tenant_id, governance_status=governance_status, page=page, per_page=per_page,
    )
    return jsonify({
        'agents': agent_list_schema.dump(agents),
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }), 200


@api_bp.route('/discovery/agents/<agent_id>', methods=['GET'])
@jwt_required
def get_discovered_agent(agent_id):
    """Get discovered agent details."""
    parsed_id, err = _parse_uuid(agent_id, 'agent ID')
    if err:
        return err
    try:
        agent = DiscoveryService.get_discovered_agent(parsed_id, get_tenant_id())
        return jsonify(agent_schema.dump(agent)), 200
    except DiscoveredAgentNotFoundError:
        return jsonify({'error': 'Discovered agent not found'}), 404


@api_bp.route('/discovery/agents/<agent_id>/onboard', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def onboard_discovered_agent(agent_id):
    """Onboard a discovered agent into the registry."""
    parsed_id, err = _parse_uuid(agent_id, 'agent ID')
    if err:
        return err
    try:
        options = onboard_agent_schema.load(request.json or {})
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        agent = DiscoveryService.onboard_agent(parsed_id, get_tenant_id(), options)
        AuditService.log('discovery.agent.onboarded', 'agent', agent.id, agent.name)
        return jsonify({
            'registry_agent_id': str(agent.id),
            'name': agent.name,
            'status': agent.status.value if hasattr(agent.status, 'value') else str(agent.status),
        }), 201
    except DiscoveredAgentNotFoundError:
        return jsonify({'error': 'Discovered agent not found'}), 404
    except (AlreadyOnboardedError, AlreadyGovernedError) as e:
        return jsonify({'error': str(e)}), 409


@api_bp.route('/discovery/agents/bulk-onboard', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def bulk_onboard_agents():
    """Bulk onboard multiple discovered agents."""
    try:
        data = bulk_onboard_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    results = DiscoveryService.bulk_onboard_agents(
        data['agent_ids'], get_tenant_id(), data,
    )

    successes = sum(1 for r in results if r['status'] == 'success')
    conflicts = sum(1 for r in results if r['status'] == 'conflict')
    errors = sum(1 for r in results if r['status'] == 'error')

    status_code = 201 if errors == 0 and conflicts == 0 else 207
    return jsonify({
        'results': results,
        'summary': {'success': successes, 'conflict': conflicts, 'error': errors},
    }), status_code


@api_bp.route('/discovery/agents/<agent_id>/quarantine', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def quarantine_discovered_agent(agent_id):
    """Quarantine a discovered agent — generates deny policies."""
    parsed_id, err = _parse_uuid(agent_id, 'agent ID')
    if err:
        return err
    try:
        agent = DiscoveryService.quarantine_agent(parsed_id, get_tenant_id())
        AuditService.log('discovery.agent.quarantined', 'discovered_agent', agent.id, agent.name)
        return jsonify({'governance_status': agent.governance_status}), 200
    except DiscoveredAgentNotFoundError:
        return jsonify({'error': 'Discovered agent not found'}), 404


@api_bp.route('/discovery/agents/<agent_id>/dismiss', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def dismiss_discovered_agent(agent_id):
    """Dismiss a discovered agent — mark as intentionally ungoverned."""
    parsed_id, err = _parse_uuid(agent_id, 'agent ID')
    if err:
        return err
    try:
        agent = DiscoveryService.dismiss_agent(parsed_id, get_tenant_id())
        AuditService.log('discovery.agent.dismissed', 'discovered_agent', agent.id, agent.name)
        return jsonify({'governance_status': agent.governance_status}), 200
    except DiscoveredAgentNotFoundError:
        return jsonify({'error': 'Discovered agent not found'}), 404


# ========================================================================
# Discovered Tools
# ========================================================================

@api_bp.route('/discovery/tools', methods=['GET'])
@jwt_required
def list_discovered_tools():
    """List discovered MCP tools."""
    tenant_id = get_tenant_id()
    governance_status = request.args.get('governance_status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    tools, total = DiscoveryService.list_discovered_tools(
        tenant_id, governance_status=governance_status, page=page, per_page=per_page,
    )
    return jsonify({
        'tools': tool_list_schema.dump(tools),
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }), 200


@api_bp.route('/discovery/tools/<tool_id>/onboard', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def onboard_discovered_tool(tool_id):
    """Onboard a discovered MCP tool into the MeshTool registry."""
    parsed_id, err = _parse_uuid(tool_id, 'tool ID')
    if err:
        return err
    try:
        result = DiscoveryService.onboard_tool(parsed_id, get_tenant_id())
        AuditService.log('discovery.tool.onboarded', 'mesh_tool', UUID(result['tool_id']), result['tool_name'])
        return jsonify(result), 201
    except DiscoveredToolNotFoundError:
        return jsonify({'error': 'Discovered tool not found'}), 404
    except (AlreadyOnboardedError, AlreadyGovernedError) as e:
        return jsonify({'error': str(e)}), 409


# ========================================================================
# Topology & Stats
# ========================================================================

@api_bp.route('/discovery/topology', methods=['GET'])
@jwt_required
def get_topology():
    """Get network topology graph."""
    tenant_id = get_tenant_id()
    subnet = request.args.get('subnet')
    governance_status = request.args.get('governance_status')
    topology = DiscoveryService.get_topology(tenant_id, subnet=subnet, governance_status=governance_status)
    return jsonify(topology), 200


@api_bp.route('/discovery/stats', methods=['GET'])
@jwt_required
def get_discovery_stats():
    """Get governance coverage statistics."""
    stats = DiscoveryService.get_stats(get_tenant_id())
    return jsonify(stats), 200


# ========================================================================
# Schedules
# ========================================================================

@api_bp.route('/discovery/schedules', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def create_schedule():
    """Create a recurring scan schedule."""
    try:
        data = schedule_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    schedule = DiscoveryService.create_schedule(data, get_tenant_id())
    AuditService.log('discovery.schedule.created', 'discovery_schedule', schedule.id, schedule.name)
    return jsonify(schedule_schema.dump(schedule)), 201


@api_bp.route('/discovery/schedules', methods=['GET'])
@jwt_required
def list_schedules():
    """List scan schedules."""
    schedules = DiscoveryService.list_schedules(get_tenant_id())
    return jsonify({'schedules': schedule_schema.dump(schedules, many=True)}), 200


@api_bp.route('/discovery/schedules/<schedule_id>', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_schedule(schedule_id):
    """Update a scan schedule."""
    parsed_id, err = _parse_uuid(schedule_id, 'schedule ID')
    if err:
        return err
    try:
        data = schedule_create_schema.load(request.json, partial=True)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    try:
        schedule = DiscoveryService.update_schedule(parsed_id, get_tenant_id(), data)
        return jsonify(schedule_schema.dump(schedule)), 200
    except ScheduleNotFoundError:
        return jsonify({'error': 'Schedule not found'}), 404


@api_bp.route('/discovery/schedules/<schedule_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def delete_schedule(schedule_id):
    """Delete a scan schedule."""
    parsed_id, err = _parse_uuid(schedule_id, 'schedule ID')
    if err:
        return err
    try:
        DiscoveryService.delete_schedule(parsed_id, get_tenant_id())
        return '', 204
    except ScheduleNotFoundError:
        return jsonify({'error': 'Schedule not found'}), 404
