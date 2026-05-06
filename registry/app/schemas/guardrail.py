"""Marshmallow schemas for guardrail CRUD and sidecar sync."""

from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError

from app.models.guardrail import (
    GuardrailType,
    GuardrailStatus,
    EnforcementMode,
    GuardrailMechanism,
    GuardrailScope,
    TestRunStatus,
)


class GuardrailCreateSchema(Schema):
    """Schema for creating a guardrail."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    type = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in GuardrailType]),
    )
    enforcement_mode = fields.String(
        load_default='block',
        validate=validate.OneOf([e.value for e in EnforcementMode]),
    )
    mechanism = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in GuardrailMechanism]),
    )
    config = fields.Dict(load_default=dict)
    scope = fields.String(
        load_default='all_agents',
        validate=validate.OneOf([e.value for e in GuardrailScope]),
    )
    priority = fields.Integer(load_default=100, validate=validate.Range(min=1, max=10000))
    version = fields.String(allow_none=True, validate=validate.Length(max=50))

    @validates_schema
    def validate_mechanism_config(self, data, **kwargs):
        """Validate mechanism-specific config."""
        mechanism = data.get('mechanism')
        config = data.get('config', {})

        if mechanism == 'regex':
            patterns = config.get('patterns', [])
            if not patterns:
                raise ValidationError(
                    'regex mechanism requires config.patterns list',
                    field_name='config',
                )
            for p in patterns:
                if not isinstance(p, dict) or 'pattern' not in p:
                    raise ValidationError(
                        'Each pattern must have a "pattern" field',
                        field_name='config',
                    )

        elif mechanism == 'llm_judge':
            if not config.get('system_prompt'):
                raise ValidationError(
                    'llm_judge mechanism requires config.system_prompt',
                    field_name='config',
                )

        elif mechanism == 'vector_lookup':
            if not config.get('collection_name'):
                raise ValidationError(
                    'vector_lookup mechanism requires config.collection_name',
                    field_name='config',
                )

        elif mechanism == 'ml_classifier':
            if not config.get('endpoint_url'):
                raise ValidationError(
                    'ml_classifier mechanism requires config.endpoint_url',
                    field_name='config',
                )


class GuardrailUpdateSchema(Schema):
    """Schema for updating a guardrail (draft only)."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    enforcement_mode = fields.String(
        validate=validate.OneOf([e.value for e in EnforcementMode]),
    )
    config = fields.Dict()
    scope = fields.String(
        validate=validate.OneOf([e.value for e in GuardrailScope]),
    )
    priority = fields.Integer(validate=validate.Range(min=1, max=10000))
    version = fields.String(allow_none=True, validate=validate.Length(max=50))


class GuardrailSchema(Schema):
    """Full guardrail dump."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    type = fields.Method('get_type')
    status = fields.Method('get_status')
    enforcement_mode = fields.Method('get_enforcement_mode')
    mechanism = fields.Method('get_mechanism')
    config = fields.Dict()
    scope = fields.Method('get_scope')
    priority = fields.Integer()
    version = fields.String()
    metric_id = fields.UUID(allow_none=True)
    created_by = fields.String()
    approved_by = fields.String()
    approved_at = fields.DateTime()
    tenant_id = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_type(self, obj):
        return obj.type.value if obj.type else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_enforcement_mode(self, obj):
        return obj.enforcement_mode.value if obj.enforcement_mode else None

    def get_mechanism(self, obj):
        return obj.mechanism.value if obj.mechanism else None

    def get_scope(self, obj):
        return obj.scope.value if obj.scope else None


class GuardrailListSchema(Schema):
    """Summary schema for list views."""
    id = fields.UUID()
    name = fields.String()
    type = fields.Method('get_type')
    status = fields.Method('get_status')
    enforcement_mode = fields.Method('get_enforcement_mode')
    mechanism = fields.Method('get_mechanism')
    scope = fields.Method('get_scope')
    priority = fields.Integer()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_type(self, obj):
        return obj.type.value if obj.type else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_enforcement_mode(self, obj):
        return obj.enforcement_mode.value if obj.enforcement_mode else None

    def get_mechanism(self, obj):
        return obj.mechanism.value if obj.mechanism else None

    def get_scope(self, obj):
        return obj.scope.value if obj.scope else None


class GuardrailAssignmentCreateSchema(Schema):
    """Schema for assigning guardrails to agents."""
    agent_ids = fields.List(fields.UUID(), required=True, validate=validate.Length(min=1))


class GuardrailAssignmentSchema(Schema):
    """Schema for guardrail assignment dump."""
    id = fields.UUID(dump_only=True)
    guardrail_id = fields.UUID()
    agent_id = fields.UUID()
    agent_name = fields.String()
    tenant_id = fields.String()
    created_at = fields.DateTime()


class GuardrailTestRunCreateSchema(Schema):
    """Schema for creating a test run."""
    agent_id = fields.UUID(required=True)
    test_inputs = fields.List(
        fields.Dict(),
        required=True,
        validate=validate.Length(min=1),
    )


class GuardrailTestRunSchema(Schema):
    """Schema for test run dump."""
    id = fields.UUID(dump_only=True)
    guardrail_id = fields.UUID()
    agent_id = fields.UUID()
    status = fields.Method('get_status')
    test_inputs = fields.Raw()
    test_results = fields.Raw()
    passed_count = fields.Integer()
    failed_count = fields.Integer()
    initiated_by = fields.String()
    tenant_id = fields.String()
    created_at = fields.DateTime()
    completed_at = fields.DateTime()

    def get_status(self, obj):
        return obj.status.value if obj.status else None


class GuardrailForSidecarSchema(Schema):
    """Minimal schema for sidecar sync — only what enforcement needs."""
    id = fields.UUID()
    type = fields.Method('get_type')
    mechanism = fields.Method('get_mechanism')
    config = fields.Dict()
    enforcement_mode = fields.Method('get_enforcement_mode')
    priority = fields.Integer()
    name = fields.String()
    metric_id = fields.UUID(allow_none=True)

    def get_type(self, obj):
        return obj.type.value if obj.type else None

    def get_mechanism(self, obj):
        return obj.mechanism.value if obj.mechanism else None

    def get_enforcement_mode(self, obj):
        return obj.enforcement_mode.value if obj.enforcement_mode else None
