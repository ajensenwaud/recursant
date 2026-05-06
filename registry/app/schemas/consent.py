"""Marshmallow schemas for GDPR consent endpoints."""

from marshmallow import Schema, fields, validate


class ConsentGrantSchema(Schema):
    """Schema for granting consent."""
    data_subject_id = fields.String(required=True, validate=validate.Length(min=1, max=255))
    consent_type = fields.String(
        required=True,
        validate=validate.OneOf(['processing', 'sharing', 'marketing']),
    )
    legal_basis = fields.String(
        allow_none=True, load_default=None,
        validate=validate.Length(max=100),
    )
    source = fields.String(allow_none=True, load_default=None, validate=validate.Length(max=255))
    metadata = fields.Dict(allow_none=True, load_default=None)


class ConsentResponseSchema(Schema):
    """Schema for a consent record response."""
    id = fields.UUID(dump_only=True)
    tenant_id = fields.String()
    data_subject_id = fields.String()
    consent_type = fields.String()
    granted = fields.Boolean()
    granted_at = fields.DateTime()
    withdrawn_at = fields.DateTime(allow_none=True)
    legal_basis = fields.String(allow_none=True)
    source = fields.String(allow_none=True)
    metadata = fields.Dict(allow_none=True, attribute='metadata_json')
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
