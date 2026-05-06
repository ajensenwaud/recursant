"""Marshmallow schemas for guardrail configurations."""

from marshmallow import Schema, fields, validate


class GuardrailConfigCreateSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)


class GuardrailConfigUpdateSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)


class GuardrailConfigEntrySchema(Schema):
    id = fields.UUID(dump_only=True)
    config_id = fields.UUID()
    guardrail_id = fields.UUID()
    enforcement_mode_override = fields.String(allow_none=True)
    enabled = fields.Boolean()
    priority_override = fields.Integer(allow_none=True)
    config_override = fields.Dict(allow_none=True)


class GuardrailConfigSchema(Schema):
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    is_active = fields.Boolean()
    tenant_id = fields.String()
    created_by = fields.String()
    activated_by = fields.String(allow_none=True)
    activated_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    entries = fields.List(fields.Nested(GuardrailConfigEntrySchema), dump_default=[])


class GuardrailConfigListSchema(Schema):
    id = fields.UUID()
    name = fields.String()
    description = fields.String()
    is_active = fields.Boolean()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class GuardrailConfigEntryCreateSchema(Schema):
    guardrail_id = fields.UUID(required=True)
    enforcement_mode_override = fields.String(
        allow_none=True,
        validate=validate.OneOf(['block', 'warn', 'redact', None]),
    )
    enabled = fields.Boolean(load_default=True)
    priority_override = fields.Integer(
        allow_none=True,
        validate=validate.Range(min=1, max=10000),
    )
    config_override = fields.Dict(allow_none=True)
