"""Marshmallow schemas for guardrail metrics."""

from marshmallow import Schema, fields, validate

from app.models.guardrail_metric import MetricCategory


class GuardrailMetricCreateSchema(Schema):
    """Schema for creating a guardrail metric."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    display_name = fields.String(allow_none=True, validate=validate.Length(max=255))
    description = fields.String(allow_none=True)
    category = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in MetricCategory]),
    )
    mechanism = fields.String(
        required=True,
        validate=validate.OneOf(['llm_judge', 'regex', 'vector_lookup', 'ml_classifier']),
    )
    config = fields.Dict(load_default=dict)
    version = fields.String(allow_none=True, validate=validate.Length(max=50))
    scoring_rubric = fields.Dict(allow_none=True)


class GuardrailMetricUpdateSchema(Schema):
    """Schema for updating a guardrail metric."""
    display_name = fields.String(allow_none=True, validate=validate.Length(max=255))
    description = fields.String(allow_none=True)
    category = fields.String(
        validate=validate.OneOf([e.value for e in MetricCategory]),
    )
    config = fields.Dict()
    version = fields.String(allow_none=True, validate=validate.Length(max=50))
    scoring_rubric = fields.Dict(allow_none=True)


class GuardrailMetricSchema(Schema):
    """Full metric dump."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    display_name = fields.String()
    description = fields.String()
    category = fields.Method('get_category')
    mechanism = fields.String()
    config = fields.Dict()
    version = fields.String()
    is_builtin = fields.Boolean()
    scoring_rubric = fields.Dict()
    tenant_id = fields.String()
    created_by = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_category(self, obj):
        return obj.category.value if obj.category else None


class GuardrailMetricListSchema(Schema):
    """Summary schema for list views."""
    id = fields.UUID()
    name = fields.String()
    display_name = fields.String()
    category = fields.Method('get_category')
    mechanism = fields.String()
    is_builtin = fields.Boolean()
    version = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_category(self, obj):
        return obj.category.value if obj.category else None


class GuardrailMetricScoreSchema(Schema):
    """Score dump."""
    id = fields.UUID(dump_only=True)
    metric_id = fields.UUID()
    agent_name = fields.String()
    score = fields.Float()
    details = fields.Dict()
    source = fields.String()
    tenant_id = fields.String()
    timestamp = fields.DateTime()


class CreateGuardrailFromMetricSchema(Schema):
    """Schema for deploying a metric as a guardrail."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    type = fields.String(
        required=True,
        validate=validate.OneOf(['pre_processing', 'post_processing', 'structural']),
    )
    enforcement_mode = fields.String(
        load_default='block',
        validate=validate.OneOf(['block', 'warn', 'redact']),
    )
    scope = fields.String(
        load_default='all_agents',
        validate=validate.OneOf(['all_agents', 'specific_agents']),
    )
    priority = fields.Integer(load_default=100, validate=validate.Range(min=1, max=10000))


class RecordScoreSchema(Schema):
    """Schema for recording a metric score."""
    agent_name = fields.String(required=True)
    score = fields.Float(required=True, validate=validate.Range(min=0.0, max=1.0))
    details = fields.Dict(allow_none=True)
    source = fields.String(
        load_default='evaluation',
        validate=validate.OneOf(['evaluation', 'sidecar', 'adversarial']),
    )
