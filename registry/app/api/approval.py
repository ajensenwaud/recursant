"""
Approval API endpoints.

Provides endpoints for listing pending approvals, submitting
approval decisions (approve / reject), listing active/approved agents,
and suspending agents.

REQ-APR-005: All approvals must include justification comment.
REQ-APR-009: Approvals can be viewed via a web interface.
"""

from datetime import datetime, timezone

from flask import jsonify, request
from sqlalchemy import or_

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app import db
from app.models import Agent, AgentStatus
from app.services.audit_service import AuditService


@api_bp.route('/approvals/pending', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_pending_approvals():
    """
    List agents that are pending approval.

    Returns:
        { "agents": [ { id, name, version, risk_tier, owner_id, submitted_at, status } ] }
    """
    agents = Agent.query.filter(
        Agent.status == AgentStatus.PENDING_APPROVAL,
        Agent.deleted_at.is_(None)
    ).order_by(Agent.updated_at.desc()).all()

    return jsonify({
        'agents': [
            {
                'id': str(agent.id),
                'name': agent.name,
                'version': agent.version,
                'risk_tier': agent.risk_tier.value if agent.risk_tier else None,
                'owner_id': agent.owner_id,
                'submitted_at': agent.updated_at.isoformat() if agent.updated_at else None,
                'status': agent.status.value,
            }
            for agent in agents
        ]
    })


@api_bp.route('/agents/<uuid:agent_id>/approval', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_approval_status(agent_id):
    """
    Get the current approval status of an agent.

    Returns:
        { "status": "pending_approval", "agent_id": "..." }
    """
    agent = Agent.query.filter(
        Agent.id == agent_id,
        Agent.deleted_at.is_(None)
    ).first()

    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    return jsonify({
        'agent_id': str(agent.id),
        'status': agent.status.value,
    })


@api_bp.route('/agents/<uuid:agent_id>/approval', methods=['POST'])
@jwt_required
@role_required(GroupType.APPROVER)
def submit_approval(agent_id):
    """
    Submit an approval decision for an agent.

    Request body:
        { "decision": "approve" | "reject", "justification": "..." }

    REQ-APR-005: Justification is mandatory.
    """
    agent = Agent.query.filter(
        Agent.id == agent_id,
        Agent.deleted_at.is_(None)
    ).first()

    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    if agent.status != AgentStatus.PENDING_APPROVAL:
        return jsonify({
            'error': f'Agent is not pending approval (current status: {agent.status.value})'
        }), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    decision = data.get('decision')
    justification = data.get('justification', '').strip()

    if decision not in ('approve', 'reject'):
        return jsonify({'error': 'Decision must be "approve" or "reject"'}), 400

    if not justification:
        return jsonify({'error': 'Justification is required (REQ-APR-005)'}), 400

    if decision == 'approve':
        agent.status = AgentStatus.APPROVED
    else:
        agent.status = AgentStatus.REJECTED

    agent.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    action = 'approval.approved' if decision == 'approve' else 'approval.rejected'
    AuditService.log(action, 'agent', agent.id, agent.name,
                     detail={'decision': decision, 'justification': justification})

    return jsonify({
        'agent_id': str(agent.id),
        'status': agent.status.value,
        'decision': decision,
    })


@api_bp.route('/agents/active', methods=['GET'])
@jwt_required
@role_required(GroupType.APPROVER)
def get_active_agents():
    """
    List agents that have been approved or are active.

    Returns:
        { "agents": [ { id, name, version, endpoint_url, risk_tier, owner_id, status, updated_at } ] }
    """
    agents = Agent.query.filter(
        or_(
            Agent.status == AgentStatus.APPROVED,
            Agent.status == AgentStatus.ACTIVE,
        ),
        Agent.deleted_at.is_(None)
    ).order_by(Agent.updated_at.desc()).all()

    return jsonify({
        'agents': [
            {
                'id': str(agent.id),
                'name': agent.name,
                'version': agent.version,
                'endpoint_url': agent.endpoint_url,
                'risk_tier': agent.risk_tier.value if agent.risk_tier else None,
                'owner_id': agent.owner_id,
                'status': agent.status.value,
                'updated_at': agent.updated_at.isoformat() if agent.updated_at else None,
            }
            for agent in agents
        ]
    })


@api_bp.route('/agents/<uuid:agent_id>/suspend', methods=['POST'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def suspend_agent(agent_id):
    """
    Suspend an approved/active agent.

    Request body:
        { "justification": "..." }
    """
    agent = Agent.query.filter(
        Agent.id == agent_id,
        Agent.deleted_at.is_(None)
    ).first()

    if not agent:
        return jsonify({'error': 'Agent not found'}), 404

    if agent.status not in (AgentStatus.APPROVED, AgentStatus.ACTIVE):
        return jsonify({
            'error': f'Agent must be approved or active to suspend (current status: {agent.status.value})'
        }), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    justification = data.get('justification', '').strip()
    if not justification:
        return jsonify({'error': 'Justification is required'}), 400

    agent.status = AgentStatus.SUSPENDED
    agent.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    AuditService.log('agent.suspended', 'agent', agent.id, agent.name,
                     detail={'justification': justification})

    return jsonify({
        'agent_id': str(agent.id),
        'status': agent.status.value,
    })
