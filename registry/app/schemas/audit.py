"""Marshmallow schemas for AuditLog model."""

from marshmallow import Schema, fields


class AuditLogSchema(Schema):
    """Full audit log entry schema."""
    id = fields.UUID(dump_only=True)
    timestamp = fields.DateTime(dump_only=True)
    user_id = fields.UUID(dump_only=True, allow_none=True)
    username = fields.String(dump_only=True)
    action = fields.String(dump_only=True)
    resource_type = fields.String(dump_only=True)
    resource_id = fields.UUID(dump_only=True, allow_none=True)
    resource_name = fields.String(dump_only=True, allow_none=True)
    detail = fields.Raw(dump_only=True, allow_none=True)
    ip_address = fields.String(dump_only=True, allow_none=True)
    tenant_id = fields.String(dump_only=True)


class AuditLogListSchema(Schema):
    """Compact audit log entry for list views (omits detail JSON)."""
    id = fields.UUID(dump_only=True)
    timestamp = fields.DateTime(dump_only=True)
    user_id = fields.UUID(dump_only=True, allow_none=True)
    username = fields.String(dump_only=True)
    action = fields.String(dump_only=True)
    resource_type = fields.String(dump_only=True)
    resource_id = fields.UUID(dump_only=True, allow_none=True)
    resource_name = fields.String(dump_only=True, allow_none=True)
    ip_address = fields.String(dump_only=True, allow_none=True)
