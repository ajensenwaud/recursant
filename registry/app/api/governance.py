"""
Governance configuration API endpoints.

Provides endpoints for viewing and updating tenant-level governance
settings such as auto-approval configuration.
"""

from flask import jsonify, request

from app.api import api_bp
from app.api.auth import jwt_required, role_required
from app.models.user import GroupType
from app import db
from app.models.agent import GovernanceConfig


@api_bp.route('/governance/config', methods=['GET'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def get_governance_config():
    """Get governance config for the current tenant."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    config = GovernanceConfig.query.filter_by(tenant_id=tenant_id).first()

    if not config:
        # Return defaults if no config exists
        return jsonify({
            'auto_approve_enabled': False,
            'auto_approve_risk_tiers': [],
        })

    return jsonify({
        'auto_approve_enabled': config.auto_approve_enabled,
        'auto_approve_risk_tiers': config.auto_approve_risk_tiers or [],
    })


@api_bp.route('/governance/config', methods=['PUT'])
@jwt_required
@role_required(GroupType.ADMINISTRATOR)
def update_governance_config():
    """Update governance config for the current tenant."""
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    config = GovernanceConfig.query.filter_by(tenant_id=tenant_id).first()
    if not config:
        config = GovernanceConfig(tenant_id=tenant_id)
        db.session.add(config)

    if 'auto_approve_enabled' in data:
        config.auto_approve_enabled = bool(data['auto_approve_enabled'])

    if 'auto_approve_risk_tiers' in data:
        tiers = data['auto_approve_risk_tiers']
        valid_tiers = {'low', 'medium', 'high', 'critical'}
        if not isinstance(tiers, list) or not all(t in valid_tiers for t in tiers):
            return jsonify({'error': f'auto_approve_risk_tiers must be a list of: {", ".join(sorted(valid_tiers))}'}), 400
        config.auto_approve_risk_tiers = tiers

    db.session.commit()

    return jsonify({
        'auto_approve_enabled': config.auto_approve_enabled,
        'auto_approve_risk_tiers': config.auto_approve_risk_tiers or [],
    })
