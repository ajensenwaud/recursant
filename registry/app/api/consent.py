"""GDPR consent tracking API endpoints.

Provides REST endpoints for managing data subject consent records.
Sidecars query these to enforce consent-based PII flow controls.
"""

import logging
from datetime import datetime, timezone

from flask import jsonify, request
from marshmallow import ValidationError

from app import db
from app.api import api_bp
from app.api.mesh import mesh_api_key_required, mesh_or_jwt_required
from app.models.consent import DataSubjectConsent
from app.schemas.consent import ConsentGrantSchema, ConsentResponseSchema

logger = logging.getLogger(__name__)

grant_schema = ConsentGrantSchema()
response_schema = ConsentResponseSchema()
response_list_schema = ConsentResponseSchema(many=True)


def _get_tenant_id():
    return request.headers.get('X-Tenant-ID', 'default')


# ---------------------------------------------------------------------------
# Grant consent
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/consent', methods=['POST'])
@mesh_or_jwt_required
def consent_grant():
    """Grant consent for a data subject.

    POST /v1/mesh/consent

    If consent of the same type already exists and is active, this is a no-op.
    If it was previously withdrawn, it creates a new grant.
    """
    try:
        data = grant_schema.load(request.json)
    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'messages': e.messages}), 400

    tenant_id = _get_tenant_id()
    subject_id = data['data_subject_id']
    consent_type = data['consent_type']

    # Check for existing active consent of same type
    existing = DataSubjectConsent.query.filter_by(
        tenant_id=tenant_id,
        data_subject_id=subject_id,
        consent_type=consent_type,
        granted=True,
    ).filter(DataSubjectConsent.withdrawn_at.is_(None)).first()

    if existing:
        return jsonify(response_schema.dump(existing)), 200

    consent = DataSubjectConsent(
        tenant_id=tenant_id,
        data_subject_id=subject_id,
        consent_type=consent_type,
        granted=True,
        legal_basis=data.get('legal_basis'),
        source=data.get('source'),
        metadata_json=data.get('metadata'),
    )
    db.session.add(consent)
    db.session.commit()

    logger.info(f"Consent granted: subject={subject_id} type={consent_type}")
    return jsonify(response_schema.dump(consent)), 201


# ---------------------------------------------------------------------------
# Query active consent
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/consent/<subject_id>', methods=['GET'])
@mesh_or_jwt_required
def consent_query(subject_id):
    """Query active consent records for a data subject.

    GET /v1/mesh/consent/<subject_id>?consent_type=processing

    Returns all active (non-withdrawn) consent records for the subject.
    Optionally filter by consent_type query parameter.
    """
    tenant_id = _get_tenant_id()

    query = DataSubjectConsent.query.filter_by(
        tenant_id=tenant_id,
        data_subject_id=subject_id,
        granted=True,
    ).filter(DataSubjectConsent.withdrawn_at.is_(None))

    consent_type = request.args.get('consent_type')
    if consent_type:
        query = query.filter_by(consent_type=consent_type)

    consents = query.all()

    return jsonify({
        'data_subject_id': subject_id,
        'consents': response_list_schema.dump(consents),
        'has_active_consent': len(consents) > 0,
    }), 200


# ---------------------------------------------------------------------------
# Withdraw consent
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/consent/<uuid:consent_id>', methods=['DELETE'])
@mesh_or_jwt_required
def consent_withdraw(consent_id):
    """Withdraw a specific consent record.

    DELETE /v1/mesh/consent/<consent_id>

    Soft-withdraws the consent by setting withdrawn_at and granted=False.
    """
    tenant_id = _get_tenant_id()

    consent = DataSubjectConsent.query.filter_by(
        id=consent_id, tenant_id=tenant_id,
    ).first()

    if not consent:
        return jsonify({'error': 'Consent record not found'}), 404

    if not consent.granted or consent.withdrawn_at is not None:
        return jsonify({'error': 'Consent already withdrawn'}), 409

    consent.granted = False
    consent.withdrawn_at = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(f"Consent withdrawn: id={consent_id} subject={consent.data_subject_id}")
    return jsonify(response_schema.dump(consent)), 200


# ---------------------------------------------------------------------------
# Consent history (audit trail)
# ---------------------------------------------------------------------------

@api_bp.route('/mesh/consent/<subject_id>/history', methods=['GET'])
@mesh_or_jwt_required
def consent_history(subject_id):
    """Get full consent history for a data subject.

    GET /v1/mesh/consent/<subject_id>/history

    Returns all consent records (active and withdrawn) for audit purposes.
    """
    tenant_id = _get_tenant_id()

    consents = DataSubjectConsent.query.filter_by(
        tenant_id=tenant_id,
        data_subject_id=subject_id,
    ).order_by(DataSubjectConsent.created_at.desc()).all()

    return jsonify({
        'data_subject_id': subject_id,
        'history': response_list_schema.dump(consents),
        'total': len(consents),
    }), 200
