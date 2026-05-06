"""
Dashboard API endpoints.

Provides statistics and summary data for the admin web interface.
"""

from flask import jsonify
from sqlalchemy import func

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app import db
from app.models import Agent, AgentStatus, SecurityScan, ScanStatus, Evaluation, EvaluationStatus


@api_bp.route('/dashboard/stats', methods=['GET'])
@jwt_required
@role_required(GroupType.USER)
def get_dashboard_stats():
    """
    Get dashboard statistics.

    Returns summary counts for agents, security scans, and evaluations.

    Returns:
        {
            "agents": {
                "total": 100,
                "by_status": {
                    "draft": 10,
                    "submitted": 5,
                    "testing": 2,
                    ...
                }
            },
            "security_scans": {
                "total": 150,
                "passed": 120,
                "failed": 25,
                "pending": 5
            },
            "evaluations": {
                "total": 140,
                "passed": 110,
                "failed": 20,
                "pending": 10
            },
            "pending_approvals": 8
        }
    """
    # Agent counts by status
    agent_status_counts = db.session.query(
        Agent.status,
        func.count(Agent.id)
    ).filter(
        Agent.deleted_at.is_(None)
    ).group_by(Agent.status).all()

    agent_by_status = {status.value: count for status, count in agent_status_counts}
    total_agents = sum(agent_by_status.values())

    # Security scan counts
    scan_status_counts = db.session.query(
        SecurityScan.status,
        func.count(SecurityScan.id)
    ).group_by(SecurityScan.status).all()

    scan_by_status = {status.value: count for status, count in scan_status_counts}
    total_scans = sum(scan_by_status.values())

    # Evaluation counts
    eval_status_counts = db.session.query(
        Evaluation.status,
        func.count(Evaluation.id)
    ).group_by(Evaluation.status).all()

    eval_by_status = {status.value: count for status, count in eval_status_counts}
    total_evals = sum(eval_by_status.values())

    # Pending approvals count
    pending_approvals = db.session.query(func.count(Agent.id)).filter(
        Agent.status == AgentStatus.PENDING_APPROVAL,
        Agent.deleted_at.is_(None)
    ).scalar() or 0

    return jsonify({
        'agents': {
            'total': total_agents,
            'by_status': agent_by_status
        },
        'security_scans': {
            'total': total_scans,
            'passed': scan_by_status.get('passed', 0),
            'failed': scan_by_status.get('failed', 0),
            'pending': scan_by_status.get('pending', 0) + scan_by_status.get('running', 0)
        },
        'evaluations': {
            'total': total_evals,
            'passed': eval_by_status.get('passed', 0),
            'failed': eval_by_status.get('failed', 0),
            'pending': eval_by_status.get('pending', 0) + eval_by_status.get('running', 0)
        },
        'pending_approvals': pending_approvals
    })
