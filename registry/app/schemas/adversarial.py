"""Marshmallow schemas for adversarial testing suites and runs."""

from marshmallow import Schema, fields, validate


VALID_ATTACK_TYPES = ['encoding', 'jailbreak', 'injection', 'pii_bypass', 'exfiltration']


# ============================================================================
# Suite Schemas
# ============================================================================

class AdversarialTestSuiteCreateSchema(Schema):
    """Schema for creating an adversarial test suite."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    attack_types = fields.List(
        fields.String(validate=validate.OneOf(VALID_ATTACK_TYPES)),
        required=True,
        validate=validate.Length(min=1),
    )
    target_guardrail_ids = fields.List(fields.UUID(), load_default=[])
    target_agent_names = fields.List(fields.String(), load_default=[])
    schedule_enabled = fields.Boolean(load_default=False)
    schedule_interval_minutes = fields.Integer(allow_none=True)
    evasion_rate_threshold = fields.Float(
        load_default=0.1,
        validate=validate.Range(min=0, max=1),
    )
    alert_on_threshold_breach = fields.Boolean(load_default=True)
    generation_config = fields.Dict(allow_none=True)


class AdversarialTestSuiteUpdateSchema(Schema):
    """Schema for updating an adversarial test suite (all fields optional)."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    attack_types = fields.List(
        fields.String(validate=validate.OneOf(VALID_ATTACK_TYPES)),
        validate=validate.Length(min=1),
    )
    target_guardrail_ids = fields.List(fields.UUID())
    target_agent_names = fields.List(fields.String())
    schedule_enabled = fields.Boolean()
    schedule_interval_minutes = fields.Integer(allow_none=True)
    evasion_rate_threshold = fields.Float(validate=validate.Range(min=0, max=1))
    alert_on_threshold_breach = fields.Boolean()
    generation_config = fields.Dict(allow_none=True)
    status = fields.String()


class AdversarialTestSuiteSchema(Schema):
    """Full adversarial test suite response."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    attack_types = fields.List(fields.String())
    target_guardrail_ids = fields.List(fields.UUID())
    target_agent_names = fields.List(fields.String())
    schedule_enabled = fields.Boolean()
    schedule_interval_minutes = fields.Integer(allow_none=True)
    evasion_rate_threshold = fields.Float()
    alert_on_threshold_breach = fields.Boolean()
    generation_config = fields.Dict(allow_none=True)
    status = fields.String()
    created_by = fields.String()
    tenant_id = fields.String()
    last_run_at = fields.DateTime(allow_none=True)
    next_run_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class AdversarialTestSuiteListSchema(Schema):
    """Compact list schema for adversarial test suites."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    status = fields.String()
    attack_types = fields.List(fields.String())
    schedule_enabled = fields.Boolean()
    evasion_rate_threshold = fields.Float()
    last_run_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()


# ============================================================================
# Run Schemas
# ============================================================================

class AdversarialTestRunSchema(Schema):
    """Full adversarial test run response."""
    id = fields.UUID(dump_only=True)
    suite_id = fields.UUID()
    status = fields.String()
    triggered_by = fields.String()
    total_inputs = fields.Integer()
    blocked_count = fields.Integer()
    evaded_count = fields.Integer()
    error_count = fields.Integer()
    evasion_rate = fields.Float()
    generated_inputs = fields.Raw(allow_none=True)
    results = fields.Raw(allow_none=True)
    threshold_breached = fields.Boolean()
    alert_sent = fields.Boolean()
    result_signature = fields.String(allow_none=True)
    signature_algorithm = fields.String(allow_none=True)
    started_at = fields.DateTime()
    completed_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()


class AdversarialTestRunListSchema(Schema):
    """Compact list schema for adversarial test runs."""
    id = fields.UUID(dump_only=True)
    suite_id = fields.UUID()
    status = fields.String()
    total_inputs = fields.Integer()
    evaded_count = fields.Integer()
    evasion_rate = fields.Float()
    threshold_breached = fields.Boolean()
    started_at = fields.DateTime()
    completed_at = fields.DateTime(allow_none=True)


# ============================================================================
# Custom Attack Schemas
# ============================================================================

VALID_SEVERITIES = ['low', 'medium', 'high', 'critical']


class CustomAttackCreateSchema(Schema):
    """Schema for creating a custom attack entry."""
    attack_type = fields.String(
        required=True,
        validate=validate.OneOf(VALID_ATTACK_TYPES),
    )
    variant_name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=255),
    )
    text = fields.String(required=True, validate=validate.Length(min=1))
    description = fields.String(allow_none=True)
    severity = fields.String(
        load_default='medium',
        validate=validate.OneOf(VALID_SEVERITIES),
    )
    source = fields.String(allow_none=True, validate=validate.Length(max=255))
    tags = fields.List(fields.String(), load_default=[])


class CustomAttackUpdateSchema(Schema):
    """Schema for updating a custom attack (all fields optional)."""
    attack_type = fields.String(validate=validate.OneOf(VALID_ATTACK_TYPES))
    variant_name = fields.String(validate=validate.Length(min=1, max=255))
    text = fields.String(validate=validate.Length(min=1))
    description = fields.String(allow_none=True)
    severity = fields.String(validate=validate.OneOf(VALID_SEVERITIES))
    source = fields.String(allow_none=True, validate=validate.Length(max=255))
    tags = fields.List(fields.String())


class CustomAttackSchema(Schema):
    """Full custom attack response schema."""
    id = fields.UUID(dump_only=True)
    attack_type = fields.String()
    variant_name = fields.String()
    text = fields.String()
    description = fields.String()
    severity = fields.String()
    source = fields.String()
    tags = fields.List(fields.String())
    created_by = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class CustomAttackListSchema(Schema):
    """Compact list schema for custom attacks."""
    id = fields.UUID(dump_only=True)
    attack_type = fields.String()
    variant_name = fields.String()
    severity = fields.String()
    source = fields.String()
    created_at = fields.DateTime()


class CustomAttackImportSchema(Schema):
    """Schema for bulk importing custom attacks (JSON array)."""
    attacks = fields.List(
        fields.Nested(CustomAttackCreateSchema),
        required=True,
        validate=validate.Length(min=1, max=500),
    )


class GenerationConfigSchema(Schema):
    """Schema for validating generation_config on a suite."""
    provider = fields.String(
        required=True,
        validate=validate.OneOf(['openai', 'anthropic', 'google']),
    )
    model = fields.String(required=True)
    temperature = fields.Float(
        load_default=0.7,
        validate=validate.Range(min=0, max=2),
    )
    max_tokens = fields.Integer(
        load_default=2048,
        validate=validate.Range(min=100, max=8192),
    )
    strategies = fields.List(
        fields.String(validate=validate.OneOf([
            'mutation', 'category_targeted', 'creative',
        ])),
        required=True,
        validate=validate.Length(min=1),
    )
    num_variants_per_strategy = fields.Integer(
        load_default=5,
        validate=validate.Range(min=1, max=50),
    )
