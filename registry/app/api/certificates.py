"""Certificate management API endpoints.

Provides certificate renewal (CSR signing) and status endpoints
for sidecar certificate auto-rotation.
"""

import logging
from datetime import datetime, timezone

from flask import jsonify, request

from app import db
from app.api import api_bp
from app.api.mesh import mesh_api_key_required
from app.models.certificates import IssuedCertificate
from app.services.ca_service import CAService

logger = logging.getLogger(__name__)

# Singleton CA service
_ca_service = CAService()


def _get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


@api_bp.route('/mesh/certificates/renew', methods=['POST'])
@mesh_api_key_required
def cert_renew():
    """Sign a CSR and return the new certificate.

    POST /v1/mesh/certificates/renew
    {
        "agent_id": "...",
        "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----..."
    }
    """
    data = request.json
    if not data:
        return jsonify({'error': 'Missing request body'}), 400

    agent_id = data.get('agent_id')
    csr_pem = data.get('csr_pem')

    if not csr_pem:
        return jsonify({'error': 'csr_pem is required'}), 400

    try:
        result = _ca_service.sign_csr(csr_pem)
    except FileNotFoundError as e:
        logger.error("ca_not_configured", error=str(e))
        return jsonify({'error': 'CA not configured'}), 503
    except Exception as e:
        logger.error("csr_signing_failed", error=str(e))
        return jsonify({'error': f'CSR signing failed: {e}'}), 500

    # Record the issued certificate for audit
    tenant_id = _get_tenant_id()
    issued_cert = IssuedCertificate(
        agent_id=agent_id or 'unknown',
        serial_number=result['serial_number'],
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.fromisoformat(result['expires_at']),
        fingerprint=result['fingerprint'],
        status='active',
        tenant_id=tenant_id,
    )
    db.session.add(issued_cert)
    db.session.commit()

    logger.info(
        "certificate_issued",
        agent_id=agent_id,
        serial=result['serial_number'][:20],
    )

    return jsonify(result), 200


@api_bp.route('/mesh/certificates/<agent_id>', methods=['GET'])
@mesh_api_key_required
def cert_status(agent_id):
    """Get current certificate metadata for an agent.

    GET /v1/mesh/certificates/<agent_id>
    """
    tenant_id = _get_tenant_id()

    certs = IssuedCertificate.query.filter_by(
        agent_id=agent_id,
        tenant_id=tenant_id,
        status='active',
    ).order_by(IssuedCertificate.issued_at.desc()).all()

    return jsonify({
        'agent_id': agent_id,
        'certificates': [
            {
                'id': str(c.id),
                'serial_number': c.serial_number,
                'issued_at': c.issued_at.isoformat(),
                'expires_at': c.expires_at.isoformat(),
                'fingerprint': c.fingerprint,
                'status': c.status,
            }
            for c in certs
        ],
        'count': len(certs),
    }), 200
