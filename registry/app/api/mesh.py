"""Mesh control plane API endpoints.

Provides REST endpoints for sidecar registration, heartbeat, discovery,
policy distribution, and audit log collection.

Authentication: Sidecars authenticate via X-Mesh-API-Key header.
"""

import hashlib
import json
import logging
import queue
import time
from datetime import datetime, timezone
from functools import wraps
from uuid import UUID

from flask import Response, current_app, jsonify, request
from marshmallow import ValidationError

from app import db
from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.agent import Agent, AgentStatus, Capability
from app.models.mesh import (
    MeshAuditLog,
    MeshComplianceRule,
    MeshEgressRule,
    MeshPolicy,
    MeshRegistration,
    MeshTool,
    MeshToolAssignment,
)
from app.models.user import GroupType
from app.services.audit_service import AuditService
from app.services.mesh_events import socketio
from app.schemas.mesh import (
    MeshAuditLogSchema,
    MeshAuditSubmitSchema,
    MeshComplianceRuleCreateSchema,
    MeshComplianceRuleSchema,
    MeshDeregisterSchema,
    MeshDiscoverAgentSchema,
    MeshEgressRuleCreateSchema,
    MeshEgressRuleSchema,
    MeshHeartbeatSchema,
    MeshPolicyCreateSchema,
    MeshPolicyListSchema,
    MeshPolicySchema,
    MeshRegisterSchema,
    MeshRegistrationSchema,
    MeshToolAssignmentCreateSchema,
    MeshToolAssignmentSchema,
    MeshToolCreateSchema,
    MeshToolSchema,
    MeshToolUpdateSchema,
    MeshToolWithAssignmentsSchema,
)

logger = logging.getLogger(__name__)

# Lazy-initialized Kafka producer for registry-side event production
_kafka_producer = None


def _get_kafka_producer():
    """Get the Kafka producer, initializing on first call if configured."""
    global _kafka_producer
    if _kafka_producer is None:
        import os
        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")
        if bootstrap:
            try:
                from confluent_kafka import Producer
                _kafka_producer = Producer({
                    "bootstrap.servers": bootstrap,
                    "client.id": "registry",
                    "acks": "1",
                    "linger.ms": 50,
                })
                logger.info("Registry Kafka producer initialized: %s", bootstrap)
            except (ImportError, Exception) as exc:
                logger.warning("Kafka producer unavailable: %s", exc)
                _kafka_producer = False  # Sentinel to avoid retrying
        else:
            _kafka_producer = False
    return _kafka_producer if _kafka_producer else None


def _produce_to_kafka(topic: str, value: dict, key: str | None = None) -> bool:
    """Produce a JSON event to Kafka. Returns True if sent, False if Kafka unavailable."""
    producer = _get_kafka_producer()
    if not producer:
        return False
    try:
        serialized = json.dumps(value, default=str).encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        producer.produce(topic, value=serialized, key=key_bytes)
        producer.poll(0)
        return True
    except Exception as exc:
        logger.error("Kafka produce failed: %s", exc)
        return False

# Schema instances
register_schema = MeshRegisterSchema()
heartbeat_schema = MeshHeartbeatSchema()
deregister_schema = MeshDeregisterSchema()
registration_schema = MeshRegistrationSchema()
discover_agent_schema = MeshDiscoverAgentSchema(many=True)
policy_create_schema = MeshPolicyCreateSchema()
policy_schema = MeshPolicySchema()
policy_list_schema = MeshPolicyListSchema(many=True)
audit_submit_schema = MeshAuditSubmitSchema()
audit_log_schema = MeshAuditLogSchema(many=True)
compliance_rule_create_schema = MeshComplianceRuleCreateSchema()
compliance_rule_schema = MeshComplianceRuleSchema()
compliance_rule_list_schema = MeshComplianceRuleSchema(many=True)
tool_create_schema = MeshToolCreateSchema()
tool_update_schema = MeshToolUpdateSchema()
tool_schema = MeshToolSchema()
tool_list_schema = MeshToolSchema(many=True)
tool_assignment_create_schema = MeshToolAssignmentCreateSchema()
tool_assignment_schema = MeshToolAssignmentSchema()
tool_assignment_list_schema = MeshToolAssignmentSchema(many=True)
egress_rule_create_schema = MeshEgressRuleCreateSchema()
egress_rule_schema = MeshEgressRuleSchema()
egress_rule_list_schema = MeshEgressRuleSchema(many=True)
tool_with_assignments_schema = MeshToolWithAssignmentsSchema(many=True)


def _get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


def _emit_governance_audit(
    a2a_method: str,
    outcome: str,
    *,
    source_agent_name: str = "registry",
    dest_agent_name: str | None = None,
    decision: str = "allow",
    details: dict | None = None,
    direction: str = "control_plane",
):
    """Create a MeshAuditLog record for a control-plane governance event.

    This ensures tool approvals, assignments, registrations, egress rule
    changes, etc. appear in the mesh audit log alongside data-plane events.
    """
    tenant_id = _get_tenant_id()
    now = datetime.now(timezone.utc)
    detail_str = json.dumps(details or {}, sort_keys=True)
    msg_hash = hashlib.sha256(detail_str.encode()).hexdigest()

    record = MeshAuditLog(
        timestamp=now,
        source_agent_name=source_agent_name,
        dest_agent_name=dest_agent_name,
        a2a_method=a2a_method,
        message_hash=msg_hash,
        direction=direction,
        decision=decision,
        outcome=outcome,
        details=details,
        sidecar_id="control-plane",
        tenant_id=tenant_id,
        cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
    )
    db.session.add(record)
    db.session.commit()

    event = {
        'source_agent_name': source_agent_name,
        'dest_agent_name': dest_agent_name,
        'a2a_method': a2a_method,
        'outcome': outcome,
        'decision': decision,
        'direction': direction,
        'message_hash': msg_hash,
        'timestamp': now.isoformat(),
    }
    socketio.emit('audit', event, namespace='/mesh')


def mesh_api_key_required(f):
    """Decorator to require a valid mesh API key for sidecar endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Mesh-API-Key')
        expected_key = current_app.config.get('MESH_API_KEY')

        if not expected_key:
            # If no key configured, allow all (dev mode)
            return f(*args, **kwargs)

        if not api_key or api_key != expected_key:
            return jsonify({'error': 'Invalid or missing mesh API key'}), 401

        return f(*args, **kwargs)

    return decorated


def mesh_or_jwt_required(f):
    """Accept either mesh API key (sidecars) or JWT Bearer token (frontend)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Try mesh API key first
        api_key = request.headers.get('X-Mesh-API-Key')
        expected_key = current_app.config.get('MESH_API_KEY')
        if expected_key and api_key == expected_key:
            return f(*args, **kwargs)
        if not expected_key and api_key:
            return f(*args, **kwargs)

        # Fall back to JWT
        from app.api.auth import decode_token
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                decode_token(token)
                return f(*args, **kwargs)
            except Exception:
                pass

        return jsonify({'error': 'Authentication required'}), 401

    return decorated


# ---------------------------------------------------------------------------
# Registration endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/register', methods=['POST'])
@mesh_api_key_required
def mesh_register():
    """Register a sidecar with the mesh.

    POST /v1/mesh/register

    Only agents in ACTIVE status can register. Returns current policies
    so the sidecar has them immediately.
    """
    try:
        data = register_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    agent_id = data['agent_id']
    tenant_id = _get_tenant_id()

    # Verify agent exists and is ACTIVE
    agent = Agent.query.filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.deleted_at.is_(None),
    ).first()

    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    if agent.status == AgentStatus.APPROVED:
        # Auto-activate on sidecar registration
        agent.status = AgentStatus.ACTIVE
        logger.info(f"Agent {agent.name} auto-activated via sidecar registration")
    elif agent.status != AgentStatus.ACTIVE:
        return jsonify({
            'error': f'Agent must be APPROVED or ACTIVE to register (current status: {agent.status.value})',
        }), 403

    # Upsert registration
    registration = MeshRegistration.query.filter_by(agent_id=agent_id).first()
    if registration:
        registration.sidecar_url = data['sidecar_url']
        registration.agent_card = data['agent_card']
        registration.sovereignty_zone = data.get('sovereignty_zone')
        registration.last_heartbeat = datetime.now(timezone.utc)
        registration.status = 'healthy'
    else:
        registration = MeshRegistration(
            agent_id=agent_id,
            sidecar_url=data['sidecar_url'],
            agent_card=data['agent_card'],
            sovereignty_zone=data.get('sovereignty_zone'),
            tenant_id=tenant_id,
            cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
        )
        db.session.add(registration)

    db.session.commit()

    AuditService.log(
        action='mesh.sidecar.registered',
        resource_type='sidecar',
        resource_id=str(registration.id),
        resource_name=agent.name,
        detail={
            'sidecar_url': data['sidecar_url'],
            'sovereignty_zone': data.get('sovereignty_zone'),
        },
    )

    _emit_governance_audit(
        'mesh/register',
        'success',
        dest_agent_name=agent.name,
        details={'sidecar_url': data['sidecar_url'], 'agent_id': str(agent_id)},
    )

    # Notify mesh visualiser clients — via Kafka if available, else direct
    reg_event = {
        'type': 'register',
        'agent_id': str(agent_id),
        'agent_name': agent.name,
        'sidecar_url': data['sidecar_url'],
        'agent_card': data['agent_card'],
        'sovereignty_zone': data.get('sovereignty_zone'),
    }
    if not _produce_to_kafka("mesh.registrations", reg_event, key=agent.name):
        socketio.emit('registration', reg_event, namespace='/mesh')
        _broadcast_sse_event('registration', reg_event)

    # Return registration + current policies
    policies = MeshPolicy.query.filter_by(tenant_id=tenant_id).order_by(
        MeshPolicy.priority
    ).all()

    return jsonify({
        'status': 'registered',
        'agent_id': str(agent_id),
        'registration': registration_schema.dump(registration),
        'policies': policy_list_schema.dump(policies),
    }), 200


@api_bp.route('/mesh/heartbeat', methods=['POST'])
@mesh_api_key_required
def mesh_heartbeat():
    """Update sidecar heartbeat.

    POST /v1/mesh/heartbeat
    """
    try:
        data = heartbeat_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    registration = MeshRegistration.query.filter_by(
        agent_id=data['agent_id']
    ).first()

    if not registration:
        return jsonify({'error': 'Agent not registered in mesh'}), 404

    registration.last_heartbeat = datetime.now(timezone.utc)
    registration.status = 'healthy'
    db.session.commit()

    return jsonify({'status': 'ok', 'agent_id': str(data['agent_id'])}), 200


@api_bp.route('/mesh/deregister', methods=['POST'])
@mesh_api_key_required
def mesh_deregister():
    """Deregister a sidecar from the mesh.

    POST /v1/mesh/deregister
    """
    try:
        data = deregister_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    registration = MeshRegistration.query.filter_by(
        agent_id=data['agent_id']
    ).first()

    if not registration:
        return jsonify({'error': 'Agent not registered in mesh'}), 404

    # During rolling deployments the old pod's deregister can race with
    # the new pod's register.  If the caller supplies its own sidecar_url,
    # only delete the registration if it matches — otherwise a terminating
    # pod would remove the registration that the replacement pod just created.
    caller_url = data.get('sidecar_url')
    if caller_url and registration.sidecar_url != caller_url:
        logger.info(
            "deregister_skipped_url_mismatch",
            agent_id=str(data['agent_id']),
            registered_url=registration.sidecar_url,
            caller_url=caller_url,
        )
        return jsonify({'status': 'skipped', 'agent_id': str(data['agent_id'])}), 200

    agent = db.session.get(Agent, registration.agent_id)
    agent_name = agent.name if agent else str(data['agent_id'])
    reg_id = str(registration.id)
    sidecar_url = registration.sidecar_url
    sovereignty_zone = registration.sovereignty_zone

    db.session.delete(registration)
    db.session.commit()

    AuditService.log(
        action='mesh.sidecar.deregistered',
        resource_type='sidecar',
        resource_id=reg_id,
        resource_name=agent_name,
        detail={
            'sidecar_url': sidecar_url,
            'sovereignty_zone': sovereignty_zone,
        },
    )

    _emit_governance_audit(
        'mesh/deregister',
        'success',
        dest_agent_name=agent_name,
        details={'sidecar_url': sidecar_url, 'agent_id': str(data['agent_id'])},
    )

    # Notify mesh visualiser clients — via Kafka if available, else direct
    dereg_event = {
        'type': 'deregister',
        'agent_id': str(data['agent_id']),
        'agent_name': agent_name,
    }
    if not _produce_to_kafka("mesh.registrations", dereg_event, key=agent_name):
        socketio.emit('registration', dereg_event, namespace='/mesh')
        _broadcast_sse_event('registration', dereg_event)

    return jsonify({'status': 'deregistered', 'agent_id': str(data['agent_id'])}), 200


# ---------------------------------------------------------------------------
# Frontend-facing registration list (JWT auth)
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/registrations', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def mesh_registrations():
    """List mesh sidecar registrations for the frontend.

    GET /v1/mesh/registrations
    """
    tenant_id = _get_tenant_id()

    registrations = db.session.query(MeshRegistration).join(
        Agent, Agent.id == MeshRegistration.agent_id
    ).filter(
        MeshRegistration.tenant_id == tenant_id,
        Agent.deleted_at.is_(None),
    ).order_by(MeshRegistration.registered_at.desc()).all()

    result = []
    for reg in registrations:
        agent = reg.agent
        result.append({
            'id': str(reg.id),
            'agent_id': str(reg.agent_id),
            'agent_name': agent.name if agent else None,
            'sidecar_url': reg.sidecar_url,
            'sovereignty_zone': reg.sovereignty_zone,
            'registered_at': reg.registered_at.isoformat() if reg.registered_at else None,
            'last_heartbeat': reg.last_heartbeat.isoformat() if reg.last_heartbeat else None,
            'status': reg.status,
            'agent_card': reg.agent_card,
            'endpoint_type': agent.endpoint_type.value if agent and agent.endpoint_type else None,
            'classification': agent.classification.value if agent and agent.classification else None,
            'risk_tier': agent.risk_tier.value if agent and agent.risk_tier else None,
            'data_sensitivity': agent.data_sensitivity.value if agent and agent.data_sensitivity else None,
        })

    return jsonify({'registrations': result}), 200


# ---------------------------------------------------------------------------
# Agent lookup (for sidecars to resolve agent_id by name)
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/agents/lookup', methods=['GET'])
@mesh_api_key_required
def mesh_agent_lookup():
    """Look up an agent by name using mesh API key auth.

    GET /v1/mesh/agents/lookup?name=Research+Assistant

    Returns the agent's ID so sidecars can resolve their agent_id at startup
    without needing admin JWT credentials.
    """
    agent_name = request.args.get('name')
    if not agent_name:
        return jsonify({'error': 'Missing required parameter: name'}), 400

    tenant_id = _get_tenant_id()

    agent = Agent.query.filter(
        Agent.name == agent_name,
        Agent.tenant_id == tenant_id,
        Agent.deleted_at.is_(None),
    ).first()

    if not agent:
        return jsonify({'error': f'Agent not found: {agent_name}'}), 404

    return jsonify({
        'agent_id': str(agent.id),
        'name': agent.name,
        'status': agent.status.value,
    }), 200


# ---------------------------------------------------------------------------
# Discovery endpoint
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/discover', methods=['GET'])
@mesh_api_key_required
def mesh_discover():
    """Discover agents by skill.

    GET /v1/mesh/discover?skill=fact-check&sovereignty_zone=eu

    Returns only healthy, registered agents whose capabilities match.
    """
    skill = request.args.get('skill')
    sovereignty_zone = request.args.get('sovereignty_zone')
    tenant_id = _get_tenant_id()

    query = db.session.query(MeshRegistration).join(
        Agent, Agent.id == MeshRegistration.agent_id
    ).filter(
        MeshRegistration.tenant_id == tenant_id,
        MeshRegistration.status.in_(['healthy']),
        Agent.deleted_at.is_(None),
        Agent.status == AgentStatus.ACTIVE,
    )

    if skill:
        query = query.join(
            Capability, Capability.agent_id == Agent.id
        ).filter(Capability.name == skill)

    if sovereignty_zone:
        query = query.filter(MeshRegistration.sovereignty_zone == sovereignty_zone)

    registrations = query.all()

    # Build response with agent info
    agents = []
    for reg in registrations:
        agent = reg.agent
        capabilities = Capability.query.filter_by(agent_id=agent.id).all()
        agents.append({
            'agent_id': agent.id,
            'name': agent.name,
            'sidecar_url': reg.sidecar_url,
            'skills': [c.name for c in capabilities],
            'version': agent.version,
            'status': reg.status,
            'last_heartbeat': reg.last_heartbeat,
            'sovereignty_zone': reg.sovereignty_zone,
            'classification': agent.classification,
            'traffic_weight': reg.traffic_weight,
        })

    return jsonify({'agents': discover_agent_schema.dump(agents)}), 200


# ---------------------------------------------------------------------------
# Agent Card endpoint
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/agents/<uuid:agent_id>/card', methods=['GET'])
@mesh_api_key_required
def mesh_agent_card(agent_id):
    """Get an agent's A2A Agent Card from its mesh registration.

    GET /v1/mesh/agents/{id}/card
    """
    registration = MeshRegistration.query.filter_by(agent_id=agent_id).first()

    if not registration:
        return jsonify({'error': 'Agent not registered in mesh'}), 404

    return jsonify(registration.agent_card), 200


# ---------------------------------------------------------------------------
# Policy endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/policies', methods=['GET'])
@mesh_or_jwt_required
def mesh_get_policies():
    """Get authorisation policies for the tenant.

    GET /v1/mesh/policies

    Sidecars poll this endpoint to get current policies.
    """
    tenant_id = _get_tenant_id()

    policies = MeshPolicy.query.filter_by(tenant_id=tenant_id).order_by(
        MeshPolicy.priority
    ).all()

    return jsonify({'policies': policy_list_schema.dump(policies)}), 200


@api_bp.route('/mesh/policies', methods=['POST'])
@mesh_api_key_required
def mesh_create_policy():
    """Create a mesh authorisation policy.

    POST /v1/mesh/policies
    """
    try:
        data = policy_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()

    policy = MeshPolicy(
        tenant_id=tenant_id,
        source_agent_name=data['source_agent_name'],
        dest_agent_name=data['dest_agent_name'],
        action=data['action'],
        priority=data.get('priority', 0),
        cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
    )
    db.session.add(policy)
    db.session.commit()

    _emit_governance_audit(
        'policy/create',
        'success',
        details={
            'policy_id': str(policy.id),
            'source': data['source_agent_name'],
            'dest': data['dest_agent_name'],
            'action': data['action'],
        },
    )

    return jsonify(policy_schema.dump(policy)), 201


@api_bp.route('/mesh/policies/<uuid:policy_id>', methods=['DELETE'])
@mesh_api_key_required
def mesh_delete_policy(policy_id):
    """Delete a mesh authorisation policy.

    DELETE /v1/mesh/policies/{id}
    """
    policy = db.session.get(MeshPolicy, policy_id)
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404

    policy_details = {
        'policy_id': str(policy.id),
        'source': policy.source_agent_name,
        'dest': policy.dest_agent_name,
        'action': policy.action,
    }
    db.session.delete(policy)
    db.session.commit()

    _emit_governance_audit('policy/delete', 'success', details=policy_details)

    return jsonify({'status': 'deleted'}), 200


# ---------------------------------------------------------------------------
# Compliance rule endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/compliance-rules', methods=['GET'])
@mesh_api_key_required
def mesh_get_compliance_rules():
    """Get compliance rules for the tenant.

    GET /v1/mesh/compliance-rules

    Sidecars fetch these to enforce sovereignty and classification policies.
    """
    tenant_id = _get_tenant_id()

    rules = MeshComplianceRule.query.filter_by(tenant_id=tenant_id).order_by(
        MeshComplianceRule.priority
    ).all()

    # Group into sovereignty and classification rules
    sovereignty_rules = []
    classification_rules = []

    for rule in rules:
        entry = {
            'source_value': rule.source_value,
            'dest_value': rule.dest_value,
            'action': rule.action,
            'priority': rule.priority,
        }
        if rule.rule_type == 'sovereignty':
            sovereignty_rules.append({
                'source_zone': rule.source_value,
                'dest_zone': rule.dest_value,
                'action': rule.action,
            })
        elif rule.rule_type == 'classification':
            classification_rules.append({
                'min_classification': rule.source_value,
                'max_dest_classification': rule.dest_value,
                'action': rule.action,
            })

    return jsonify({
        'rules': compliance_rule_list_schema.dump(rules),
        'sovereignty_rules': sovereignty_rules,
        'classification_rules': classification_rules,
    }), 200


@api_bp.route('/mesh/compliance-rules', methods=['POST'])
@mesh_api_key_required
def mesh_create_compliance_rule():
    """Create a compliance rule.

    POST /v1/mesh/compliance-rules
    """
    try:
        data = compliance_rule_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()

    rule = MeshComplianceRule(
        tenant_id=tenant_id,
        rule_type=data['rule_type'],
        source_value=data['source_value'],
        dest_value=data['dest_value'],
        action=data['action'],
        priority=data.get('priority', 0),
        cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
    )
    db.session.add(rule)
    db.session.commit()

    _emit_governance_audit(
        'compliance/create',
        'success',
        details={
            'rule_id': str(rule.id),
            'rule_type': rule.rule_type,
            'source_value': rule.source_value,
            'dest_value': rule.dest_value,
            'action': rule.action,
        },
    )

    return jsonify(compliance_rule_schema.dump(rule)), 201


@api_bp.route('/mesh/compliance-rules/<uuid:rule_id>', methods=['DELETE'])
@mesh_api_key_required
def mesh_delete_compliance_rule(rule_id):
    """Delete a compliance rule.

    DELETE /v1/mesh/compliance-rules/{id}
    """
    rule = db.session.get(MeshComplianceRule, rule_id)
    if not rule:
        return jsonify({'error': 'Compliance rule not found'}), 404

    rule_details = {
        'rule_id': str(rule.id),
        'rule_type': rule.rule_type,
        'source_value': rule.source_value,
        'dest_value': rule.dest_value,
    }
    db.session.delete(rule)
    db.session.commit()

    _emit_governance_audit('compliance/delete', 'success', details=rule_details)

    return jsonify({'status': 'deleted'}), 200


# ---------------------------------------------------------------------------
# Tool governance endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/tools', methods=['GET'])
@mesh_or_jwt_required
def mesh_list_tools():
    """List registered tools.

    GET /v1/mesh/tools?status=approved&agent_name=X
    """
    tenant_id = _get_tenant_id()
    query = MeshTool.query.filter_by(tenant_id=tenant_id)

    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter(MeshTool.status == status_filter)

    agent_name = request.args.get('agent_name')
    if agent_name:
        query = query.join(MeshToolAssignment).filter(
            MeshToolAssignment.agent_name == agent_name,
        )

    tools = query.order_by(MeshTool.name).all()
    return jsonify({'tools': tool_list_schema.dump(tools)}), 200


@api_bp.route('/mesh/tools/with-assignments', methods=['GET'])
@mesh_or_jwt_required
def mesh_tools_with_assignments():
    """Get all tools with their assignments inlined.

    GET /v1/mesh/tools/with-assignments
    """
    tenant_id = _get_tenant_id()
    tools = MeshTool.query.filter_by(tenant_id=tenant_id).order_by(MeshTool.name).all()

    result = []
    for t in tools:
        data = tool_schema.dump(t)
        data['assignments'] = [
            {'id': str(a.id), 'agent_name': a.agent_name}
            for a in t.assignments
        ]
        result.append(data)

    return jsonify({'tools': result}), 200


@api_bp.route('/mesh/tools', methods=['POST'])
@mesh_or_jwt_required
def mesh_create_tool():
    """Create a new tool registration.

    POST /v1/mesh/tools
    """
    try:
        data = tool_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()

    existing = MeshTool.query.filter_by(tenant_id=tenant_id, name=data['name']).first()
    if existing:
        return jsonify({'error': f"Tool '{data['name']}' already exists"}), 409

    tool = MeshTool(
        tenant_id=tenant_id,
        name=data['name'],
        description=data.get('description'),
        tool_type=data.get('tool_type', 'http'),
        endpoint_url=data['endpoint_url'],
        http_method=data.get('http_method', 'POST'),
        parameters_schema=data.get('parameters_schema'),
        mcp_server_url=data.get('mcp_server_url'),
        mcp_server_name=data.get('mcp_server_name'),
        mcp_server_description=data.get('mcp_server_description'),
        backend_services=data.get('backend_services'),
        cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
    )
    db.session.add(tool)
    db.session.commit()

    _emit_governance_audit(
        'tools/create',
        'success',
        dest_agent_name=tool.name,
        details={'tool_id': str(tool.id), 'endpoint_url': tool.endpoint_url, 'status': tool.status},
    )

    return jsonify(tool_schema.dump(tool)), 201


@api_bp.route('/mesh/tools/<uuid:tool_id>', methods=['GET'])
@mesh_or_jwt_required
def mesh_get_tool(tool_id):
    """Get a single tool.

    GET /v1/mesh/tools/{id}
    """
    tool = db.session.get(MeshTool, tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404
    return jsonify(tool_schema.dump(tool)), 200


@api_bp.route('/mesh/tools/<uuid:tool_id>', methods=['PATCH'])
@mesh_or_jwt_required
def mesh_update_tool(tool_id):
    """Update a tool.

    PATCH /v1/mesh/tools/{id}
    """
    tool = db.session.get(MeshTool, tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    try:
        data = tool_update_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    for key, value in data.items():
        if value is not None:
            setattr(tool, key, value)

    db.session.commit()
    return jsonify(tool_schema.dump(tool)), 200


@api_bp.route('/mesh/tools/<uuid:tool_id>', methods=['DELETE'])
@mesh_or_jwt_required
def mesh_delete_tool(tool_id):
    """Delete a tool (draft only).

    DELETE /v1/mesh/tools/{id}
    """
    tool = db.session.get(MeshTool, tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    if tool.status != 'submitted':
        return jsonify({'error': 'Only submitted tools can be deleted'}), 400

    db.session.delete(tool)
    db.session.commit()
    return jsonify({'status': 'deleted'}), 200


@api_bp.route('/mesh/tools/<uuid:tool_id>/approve', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def mesh_approve_tool(tool_id):
    """Approve a tool for use.

    POST /v1/mesh/tools/{id}/approve
    """
    tool = db.session.get(MeshTool, tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    if tool.status != 'submitted':
        return jsonify({'error': f'Only submitted tools can be approved (current: {tool.status})'}), 400

    body = request.get_json(silent=True) or {}
    justification = body.get('justification')

    from flask import g
    tool.status = 'approved'
    tool.approved_by = getattr(g, 'current_user', {}).get('username', 'unknown')
    tool.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_governance_audit(
        'tools/approve',
        'success',
        dest_agent_name=tool.name,
        details={
            'tool_id': str(tool.id),
            'approved_by': tool.approved_by,
            'justification': justification,
        },
    )

    return jsonify(tool_schema.dump(tool)), 200


@api_bp.route('/mesh/tools/<uuid:tool_id>/revoke', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def mesh_revoke_tool(tool_id):
    """Revoke a submitted or approved tool.

    POST /v1/mesh/tools/{id}/revoke
    """
    tool = db.session.get(MeshTool, tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    if tool.status not in ('submitted', 'approved'):
        return jsonify({'error': f'Only submitted or approved tools can be revoked (current: {tool.status})'}), 400

    body = request.get_json(silent=True) or {}
    justification = body.get('justification')

    from flask import g
    tool.status = 'revoked'
    tool.revoked_by = getattr(g, 'current_user', {}).get('username', 'unknown')
    tool.revoked_at = datetime.now(timezone.utc)
    db.session.commit()

    _emit_governance_audit(
        'tools/revoke',
        'success',
        dest_agent_name=tool.name,
        details={
            'tool_id': str(tool.id),
            'revoked_by': tool.revoked_by,
            'justification': justification,
        },
    )

    return jsonify(tool_schema.dump(tool)), 200


# ---------------------------------------------------------------------------
# Tool assignment endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/tool-assignments', methods=['GET'])
@mesh_or_jwt_required
def mesh_list_tool_assignments():
    """List tool assignments.

    GET /v1/mesh/tool-assignments?agent_name=X
    """
    tenant_id = _get_tenant_id()
    query = MeshToolAssignment.query.filter_by(tenant_id=tenant_id)

    agent_name = request.args.get('agent_name')
    if agent_name:
        query = query.filter(MeshToolAssignment.agent_name == agent_name)

    assignments = query.all()
    result = []
    for a in assignments:
        d = tool_assignment_schema.dump(a)
        d['tool_name'] = a.tool.name if a.tool else None
        result.append(d)

    return jsonify({'assignments': result}), 200


@api_bp.route('/mesh/tool-assignments', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def mesh_create_tool_assignment():
    """Assign a tool to an agent.

    POST /v1/mesh/tool-assignments
    """
    try:
        data = tool_assignment_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()

    tool = db.session.get(MeshTool, data['tool_id'])
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    existing = MeshToolAssignment.query.filter_by(
        tenant_id=tenant_id,
        tool_id=data['tool_id'],
        agent_name=data['agent_name'],
    ).first()
    if existing:
        return jsonify({'error': 'Assignment already exists'}), 409

    assignment = MeshToolAssignment(
        tenant_id=tenant_id,
        tool_id=data['tool_id'],
        agent_name=data['agent_name'],
    )
    db.session.add(assignment)
    db.session.commit()

    result = tool_assignment_schema.dump(assignment)
    result['tool_name'] = tool.name

    _emit_governance_audit(
        'tools/assign',
        'success',
        dest_agent_name=data['agent_name'],
        details={'tool_id': str(tool.id), 'tool_name': tool.name, 'agent_name': data['agent_name']},
    )

    return jsonify(result), 201


@api_bp.route('/mesh/tool-assignments/<uuid:assignment_id>', methods=['DELETE'])
@jwt_required
@role_required(GroupType.APPROVER)
def mesh_delete_tool_assignment(assignment_id):
    """Remove a tool assignment.

    DELETE /v1/mesh/tool-assignments/{id}
    """
    assignment = db.session.get(MeshToolAssignment, assignment_id)
    if not assignment:
        return jsonify({'error': 'Assignment not found'}), 404

    assignment_details = {
        'assignment_id': str(assignment.id),
        'tool_id': str(assignment.tool_id),
        'tool_name': assignment.tool.name if assignment.tool else None,
        'agent_name': assignment.agent_name,
    }
    db.session.delete(assignment)
    db.session.commit()

    _emit_governance_audit(
        'tools/unassign',
        'success',
        dest_agent_name=assignment_details['agent_name'],
        details=assignment_details,
    )

    return jsonify({'status': 'deleted'}), 200


# ---------------------------------------------------------------------------
# Sidecar-facing tool/egress endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/tools/for-agent', methods=['GET'])
@mesh_api_key_required
def mesh_tools_for_agent():
    """Get approved tools assigned to an agent (sidecar-facing).

    GET /v1/mesh/tools/for-agent?agent_name=X
    """
    agent_name = request.args.get('agent_name')
    if not agent_name:
        return jsonify({'error': 'Missing required parameter: agent_name'}), 400

    tenant_id = _get_tenant_id()

    tools = db.session.query(MeshTool).join(
        MeshToolAssignment, MeshToolAssignment.tool_id == MeshTool.id,
    ).filter(
        MeshTool.tenant_id == tenant_id,
        MeshTool.status == 'approved',
        MeshToolAssignment.agent_name == agent_name,
    ).all()

    result = []
    for t in tools:
        result.append({
            'name': t.name,
            'endpoint_url': t.endpoint_url,
            'http_method': t.http_method,
            'parameters_schema': t.parameters_schema,
            'mcp_server_url': t.mcp_server_url,
        })

    return jsonify({'tools': result}), 200


@api_bp.route('/mesh/egress-rules/for-agent', methods=['GET'])
@mesh_api_key_required
def mesh_egress_rules_for_agent():
    """Get egress rules matching an agent (sidecar-facing).

    GET /v1/mesh/egress-rules/for-agent?agent_name=X

    Returns rules matching agent_name or wildcard '*', sorted by priority.
    """
    agent_name = request.args.get('agent_name')
    if not agent_name:
        return jsonify({'error': 'Missing required parameter: agent_name'}), 400

    tenant_id = _get_tenant_id()

    rules = MeshEgressRule.query.filter(
        MeshEgressRule.tenant_id == tenant_id,
        db.or_(
            MeshEgressRule.agent_name == agent_name,
            MeshEgressRule.agent_name == '*',
        ),
    ).order_by(MeshEgressRule.priority).all()

    result = []
    for r in rules:
        result.append({
            'url_pattern': r.url_pattern,
            'action': r.action,
            'priority': r.priority,
        })

    return jsonify({'rules': result}), 200


# ---------------------------------------------------------------------------
# Guardrail sidecar-facing endpoint
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/guardrails/for-agent', methods=['GET'])
@mesh_api_key_required
def mesh_guardrails_for_agent():
    """Get active guardrails for an agent (sidecar-facing).

    GET /v1/mesh/guardrails/for-agent?agent_name=X

    Returns active guardrails applicable to this agent (scope=all_agents
    plus specifically assigned), sorted by priority.
    """
    agent_name = request.args.get('agent_name')
    if not agent_name:
        return jsonify({'error': 'Missing required parameter: agent_name'}), 400

    tenant_id = _get_tenant_id()

    from app.schemas.guardrail import GuardrailForSidecarSchema
    from app.services.guardrail_service import GuardrailService

    sidecar_schema = GuardrailForSidecarSchema(many=True)
    guardrails = GuardrailService.get_guardrails_for_agent(agent_name, tenant_id)

    return jsonify({'guardrails': sidecar_schema.dump(guardrails)}), 200


# ---------------------------------------------------------------------------
# Egress rule CRUD endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/egress-rules', methods=['GET'])
@mesh_or_jwt_required
def mesh_list_egress_rules():
    """List egress rules.

    GET /v1/mesh/egress-rules
    """
    tenant_id = _get_tenant_id()
    rules = MeshEgressRule.query.filter_by(tenant_id=tenant_id).order_by(
        MeshEgressRule.priority
    ).all()

    return jsonify({'rules': egress_rule_list_schema.dump(rules)}), 200


@api_bp.route('/mesh/egress-rules', methods=['POST'])
@mesh_or_jwt_required
def mesh_create_egress_rule():
    """Create an egress rule.

    POST /v1/mesh/egress-rules
    """
    try:
        data = egress_rule_create_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()

    rule = MeshEgressRule(
        tenant_id=tenant_id,
        agent_name=data.get('agent_name', '*'),
        url_pattern=data['url_pattern'],
        action=data['action'],
        priority=data.get('priority', 0),
        cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
    )
    db.session.add(rule)
    db.session.commit()

    _emit_governance_audit(
        'egress/create',
        'success',
        dest_agent_name=rule.agent_name,
        details={
            'rule_id': str(rule.id),
            'url_pattern': rule.url_pattern,
            'action': rule.action,
            'priority': rule.priority,
        },
    )

    return jsonify(egress_rule_schema.dump(rule)), 201


@api_bp.route('/mesh/egress-rules/<uuid:rule_id>', methods=['DELETE'])
@mesh_or_jwt_required
def mesh_delete_egress_rule(rule_id):
    """Delete an egress rule.

    DELETE /v1/mesh/egress-rules/{id}
    """
    rule = db.session.get(MeshEgressRule, rule_id)
    if not rule:
        return jsonify({'error': 'Egress rule not found'}), 404

    rule_details = {
        'rule_id': str(rule.id),
        'agent_name': rule.agent_name,
        'url_pattern': rule.url_pattern,
        'action': rule.action,
    }
    db.session.delete(rule)
    db.session.commit()

    _emit_governance_audit('egress/delete', 'success', details=rule_details)

    return jsonify({'status': 'deleted'}), 200


# ---------------------------------------------------------------------------
# Guardrail event ingestion
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/guardrail-events', methods=['POST'])
@mesh_api_key_required
def mesh_submit_guardrail_events():
    """Receive guardrail evaluation events from sidecars.

    POST /v1/mesh/guardrail-events

    Accepts a batch of events for the observability pipeline.
    """
    from app.models.guardrail import GuardrailEvent

    data = request.json
    if not data or 'events' not in data:
        return jsonify({'error': 'Missing events array'}), 400

    tenant_id = _get_tenant_id()
    events_data = data['events']
    count = 0

    for evt in events_data:
        record = GuardrailEvent(
            tenant_id=tenant_id,
            guardrail_id=evt.get('guardrail_id'),
            guardrail_name=evt.get('guardrail_name'),
            guardrail_type=evt.get('guardrail_type'),
            mechanism=evt.get('mechanism'),
            agent_name=evt.get('agent_name'),
            sidecar_id=evt.get('sidecar_id'),
            action=evt.get('action', 'pass'),
            reasoning=evt.get('reasoning'),
            latency_ms=evt.get('latency_ms'),
            matched_pattern=evt.get('matched_pattern'),
            input_hash=evt.get('input_hash'),
            is_error=evt.get('is_error', False),
            error_message=evt.get('error_message'),
            metric_id=evt.get('metric_id'),
            triggered_spans=evt.get('triggered_spans'),
        )
        if evt.get('timestamp'):
            try:
                from datetime import datetime as _dt
                ts = evt['timestamp']
                if isinstance(ts, str):
                    record.timestamp = _dt.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    record.timestamp = ts
            except (ValueError, TypeError):
                pass
        db.session.add(record)
        count += 1

    db.session.commit()

    # Fire webhooks for non-pass events in a background thread
    if count > 0:
        try:
            from app.services.webhook_service import WebhookService
            import threading

            non_pass_records = [r for r in db.session.query(GuardrailEvent).filter(
                GuardrailEvent.tenant_id == tenant_id,
                GuardrailEvent.action != 'pass',
            ).order_by(GuardrailEvent.timestamp.desc()).limit(count).all()
                if r.action != 'pass']

            for record in non_pass_records:
                t = threading.Thread(
                    target=WebhookService.process_guardrail_event,
                    args=(record, tenant_id),
                    daemon=True,
                )
                t.start()
        except Exception as e:
            logger.warning("webhook_dispatch_failed: %s", e)

    # Fan-out via Kafka if available, else direct Socket.IO
    kafka_used = False
    if count > 0:
        for evt in events_data:
            evt['tenant_id'] = tenant_id
            if _produce_to_kafka("mesh.guardrails", evt, key=evt.get("agent_name")):
                kafka_used = True

        if not kafka_used:
            last_evt = events_data[-1]
            socketio.emit('guardrail-event', {
                'event_count': count,
                'latest_action': last_evt.get('action'),
                'latest_guardrail_name': last_evt.get('guardrail_name'),
                'latest_agent_name': last_evt.get('agent_name'),
                'timestamp': last_evt.get('timestamp'),
            }, namespace='/mesh')

    status_code = 202 if kafka_used else 201
    return jsonify({'status': 'accepted', 'count': count}), status_code


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/audit', methods=['POST'])
@mesh_api_key_required
def mesh_submit_audit():
    """Receive audit records from sidecars.

    POST /v1/mesh/audit

    Accepts a batch of audit records.
    """
    try:
        data = audit_submit_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()
    count = 0
    chain_warnings = []

    audit_events = []
    for record_data in data['records']:
        sidecar_id = record_data.get('sidecar_id')
        record_hash = record_data.get('record_hash')
        previous_record_hash = record_data.get('previous_record_hash')
        sequence_number = record_data.get('sequence_number')

        # Validate hash chain continuity if chain fields are present
        if sidecar_id and sequence_number is not None and record_hash:
            last_stored = MeshAuditLog.query.filter_by(
                sidecar_id=sidecar_id, tenant_id=tenant_id,
            ).order_by(MeshAuditLog.sequence_number.desc()).first()

            if last_stored and last_stored.sequence_number is not None:
                expected_seq = last_stored.sequence_number + 1
                if sequence_number != expected_seq:
                    chain_warnings.append(
                        f"sidecar={sidecar_id} seq gap: expected {expected_seq}, got {sequence_number}"
                    )
                    logger.warning("audit_chain_gap sidecar_id=%s expected=%s got=%s",
                                   sidecar_id, expected_seq, sequence_number)
                if previous_record_hash and previous_record_hash != last_stored.record_hash:
                    chain_warnings.append(
                        f"sidecar={sidecar_id} hash mismatch at seq {sequence_number}"
                    )
                    logger.warning("audit_chain_tamper sidecar_id=%s seq=%s expected_prev=%s got_prev=%s",
                                   sidecar_id, sequence_number,
                                   last_stored.record_hash, previous_record_hash)

        # Extract CoT analysis from details if present
        details = record_data.get('details')
        cot_analysis = None
        cot_risk_level = None
        cot_flags = None
        if isinstance(details, dict) and 'cot_analysis' in details:
            cot_data = details['cot_analysis']
            cot_analysis = cot_data
            cot_risk_level = cot_data.get('risk_level')
            cot_flags = cot_data.get('flags')

        count += 1
        audit_events.append({
            'source_agent_id': record_data.get('source_agent_id'),
            'source_agent_name': record_data.get('source_agent_name'),
            'dest_agent_id': record_data.get('dest_agent_id'),
            'dest_agent_name': record_data.get('dest_agent_name'),
            'a2a_method': record_data['a2a_method'],
            'outcome': record_data['outcome'],
            'decision': record_data['decision'],
            'direction': record_data.get('direction'),
            'message_hash': record_data.get('message_hash'),
            'timestamp': record_data['timestamp'].isoformat()
                if hasattr(record_data['timestamp'], 'isoformat')
                else str(record_data['timestamp']),
            'task_id': record_data.get('task_id'),
            'details': details,
            'sidecar_id': sidecar_id,
            'tenant_id': tenant_id,
            'record_hash': record_hash,
            'previous_record_hash': previous_record_hash,
            'sequence_number': sequence_number,
        })

    # Try Kafka first. If available, the pg-writer consumer handles
    # durable storage — no direct PG write needed here.
    kafka_available = False
    for event in audit_events:
        if _produce_to_kafka("mesh.audit", event, key=event.get("sidecar_id")):
            kafka_available = True
        else:
            break

    if kafka_available:
        # Kafka handles PG writes (pg-writer consumer) and WebSocket
        # broadcasts (ws-broadcaster consumer). Nothing else to do.
        result = {'status': 'accepted', 'count': count}
        if chain_warnings:
            result['chain_warnings'] = chain_warnings
        return jsonify(result), 202

    # Fallback: Kafka unavailable — write directly to PG and emit via Socket.IO
    for event in audit_events:
        ev_details = event.get('details')
        ev_cot_analysis = None
        ev_cot_risk_level = None
        ev_cot_flags = None
        if isinstance(ev_details, dict) and 'cot_analysis' in ev_details:
            ev_cot_analysis = ev_details['cot_analysis']
            ev_cot_risk_level = ev_cot_analysis.get('risk_level')
            ev_cot_flags = ev_cot_analysis.get('flags')

        ts = datetime.fromisoformat(event['timestamp'])
        record = MeshAuditLog(
            timestamp=ts,
            source_agent_id=event.get('source_agent_id'),
            source_agent_name=event.get('source_agent_name'),
            dest_agent_id=event.get('dest_agent_id'),
            dest_agent_name=event.get('dest_agent_name'),
            task_id=event.get('task_id'),
            a2a_method=event['a2a_method'],
            message_hash=event.get('message_hash', ''),
            direction=event.get('direction', 'inbound'),
            decision=event.get('decision', 'pass'),
            outcome=event.get('outcome', 'success'),
            details=ev_details,
            sidecar_id=event.get('sidecar_id'),
            tenant_id=event.get('tenant_id', tenant_id),
            cluster_id=current_app.config.get('CLUSTER_ID', 'default'),
            record_hash=event.get('record_hash'),
            previous_record_hash=event.get('previous_record_hash'),
            sequence_number=event.get('sequence_number'),
            cot_analysis=ev_cot_analysis,
            cot_risk_level=ev_cot_risk_level,
            cot_flags=ev_cot_flags,
        )
        db.session.add(record)
        socketio.emit('audit', event, namespace='/mesh')
        _broadcast_sse_event('audit', event)

    db.session.commit()

    result = {'status': 'accepted', 'count': count}
    if chain_warnings:
        result['chain_warnings'] = chain_warnings
    return jsonify(result), 201


@api_bp.route('/mesh/audit', methods=['GET'])
@mesh_or_jwt_required
def mesh_query_audit():
    """Query mesh audit logs with advanced filtering.

    GET /v1/mesh/audit?task_id=...&a2a_method=...&page=1&per_page=50

    Additional filters:
    - source_agent_name, dest_agent_name: exact match
    - direction: inbound/outbound
    - decision: pass/block
    - outcome: success/blocked/error
    - date_from, date_to: ISO datetime range
    - search: ILIKE search across agent names, method, task_id
    - sidecar_id: filter by sidecar
    - trace_id: alias for task_id (trace reconstruction)
    """
    tenant_id = _get_tenant_id()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = MeshAuditLog.query.filter_by(tenant_id=tenant_id)

    # Exact match filters
    task_id = request.args.get('task_id') or request.args.get('trace_id')
    if task_id:
        query = query.filter(MeshAuditLog.task_id == task_id)

    a2a_method = request.args.get('a2a_method')
    if a2a_method:
        query = query.filter(MeshAuditLog.a2a_method == a2a_method)

    source_agent = request.args.get('source_agent') or request.args.get('source_agent_name')
    if source_agent:
        query = query.filter(MeshAuditLog.source_agent_name == source_agent)

    dest_agent = request.args.get('dest_agent') or request.args.get('dest_agent_name')
    if dest_agent:
        query = query.filter(MeshAuditLog.dest_agent_name == dest_agent)

    direction = request.args.get('direction')
    if direction:
        query = query.filter(MeshAuditLog.direction == direction)

    decision = request.args.get('decision')
    if decision:
        query = query.filter(MeshAuditLog.decision == decision)

    outcome = request.args.get('outcome')
    if outcome:
        query = query.filter(MeshAuditLog.outcome == outcome)

    sidecar_id = request.args.get('sidecar_id')
    if sidecar_id:
        query = query.filter(MeshAuditLog.sidecar_id == sidecar_id)

    # Date range filters
    date_from = request.args.get('date_from')
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            query = query.filter(MeshAuditLog.timestamp >= dt)
        except ValueError:
            pass

    date_to = request.args.get('date_to')
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            query = query.filter(MeshAuditLog.timestamp <= dt)
        except ValueError:
            pass

    # Full-text search across multiple fields
    search = request.args.get('search')
    if search:
        like_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                MeshAuditLog.source_agent_name.ilike(like_pattern),
                MeshAuditLog.dest_agent_name.ilike(like_pattern),
                MeshAuditLog.a2a_method.ilike(like_pattern),
                MeshAuditLog.task_id.ilike(like_pattern),
            )
        )

    query = query.order_by(MeshAuditLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'records': audit_log_schema.dump(pagination.items),
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page,
    }), 200


@api_bp.route('/mesh/audit/stats', methods=['GET'])
@mesh_or_jwt_required
def mesh_audit_stats():
    """Get aggregated audit statistics.

    GET /v1/mesh/audit/stats?date_from=...&date_to=...

    Returns total count, blocked count, error count, top agents, outcome/decision breakdowns.
    """
    tenant_id = _get_tenant_id()

    base_query = MeshAuditLog.query.filter_by(tenant_id=tenant_id)

    # Apply date range
    date_from = request.args.get('date_from')
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            base_query = base_query.filter(MeshAuditLog.timestamp >= dt)
        except ValueError:
            pass

    date_to = request.args.get('date_to')
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            base_query = base_query.filter(MeshAuditLog.timestamp <= dt)
        except ValueError:
            pass

    total = base_query.count()
    blocked = base_query.filter(MeshAuditLog.outcome == 'blocked').count()
    errors = base_query.filter(MeshAuditLog.outcome == 'error').count()

    # Top source agents by volume
    top_sources = db.session.query(
        MeshAuditLog.source_agent_name,
        db.func.count(MeshAuditLog.id).label('count'),
    ).filter(
        MeshAuditLog.tenant_id == tenant_id,
        MeshAuditLog.source_agent_name.isnot(None),
    ).group_by(MeshAuditLog.source_agent_name).order_by(
        db.func.count(MeshAuditLog.id).desc()
    ).limit(10).all()

    # Top destination agents
    top_destinations = db.session.query(
        MeshAuditLog.dest_agent_name,
        db.func.count(MeshAuditLog.id).label('count'),
    ).filter(
        MeshAuditLog.tenant_id == tenant_id,
        MeshAuditLog.dest_agent_name.isnot(None),
    ).group_by(MeshAuditLog.dest_agent_name).order_by(
        db.func.count(MeshAuditLog.id).desc()
    ).limit(10).all()

    # Outcome breakdown
    outcomes = db.session.query(
        MeshAuditLog.outcome,
        db.func.count(MeshAuditLog.id).label('count'),
    ).filter(
        MeshAuditLog.tenant_id == tenant_id,
    ).group_by(MeshAuditLog.outcome).all()

    # Decision breakdown
    decisions = db.session.query(
        MeshAuditLog.decision,
        db.func.count(MeshAuditLog.id).label('count'),
    ).filter(
        MeshAuditLog.tenant_id == tenant_id,
    ).group_by(MeshAuditLog.decision).all()

    return jsonify({
        'total': total,
        'blocked': blocked,
        'errors': errors,
        'top_sources': [{'name': name, 'count': count} for name, count in top_sources],
        'top_destinations': [{'name': name, 'count': count} for name, count in top_destinations],
        'outcomes': {outcome: count for outcome, count in outcomes},
        'decisions': {decision: count for decision, count in decisions},
    }), 200


@api_bp.route('/mesh/audit/<uuid:audit_id>', methods=['GET'])
@mesh_or_jwt_required
def mesh_audit_detail(audit_id):
    """Get full detail of a single audit record.

    GET /v1/mesh/audit/{id}
    """
    record = db.session.get(MeshAuditLog, audit_id)
    if not record:
        return jsonify({'error': 'Audit record not found'}), 404

    single_schema = MeshAuditLogSchema()
    return jsonify(single_schema.dump(record)), 200


# ---------------------------------------------------------------------------
# SSE event stream (for cross-cluster event bridging)
# ---------------------------------------------------------------------------

# In-memory subscribers for SSE — each connected client gets a queue
_sse_subscribers: list[queue.Queue] = []
_sse_lock = __import__('threading').Lock()


def _broadcast_sse_event(event_type: str, data: dict) -> None:
    """Push an event to all connected SSE subscribers."""
    with _sse_lock:
        dead = []
        for q in _sse_subscribers:
            try:
                q.put_nowait((event_type, data))
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_subscribers.remove(q)


@api_bp.route('/mesh/events/stream', methods=['GET'])
@mesh_api_key_required
def mesh_event_stream():
    """Server-Sent Events stream for cross-cluster event bridging.

    GET /v1/mesh/events/stream

    Streams registration and audit events as SSE. Used by the EventBridge
    on the remote cluster to receive events in real time.
    """
    q: queue.Queue = queue.Queue(maxsize=256)
    with _sse_lock:
        _sse_subscribers.append(q)

    def generate():
        try:
            while True:
                try:
                    event_type, data = q.get(timeout=30)
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                except queue.Empty:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
