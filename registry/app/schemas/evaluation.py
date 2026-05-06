"""
Marshmallow schemas for evaluation models.

Provides validation and serialization for evaluation suites, test cases,
evaluations, and results.
"""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError, post_dump
from app.models.evaluation import (
    EvaluationStatus,
    EvaluationResultStatus,
    EvaluationCategory,
    LLMProvider,
    AggregationMethod,
)
from app.models.agent import RiskTier


# ============================================================================
# Nested Schemas
# ============================================================================

class JudgeConfigSchema(Schema):
    """Configuration for the LLM judge."""
    provider = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in LLMProvider])
    )
    model = fields.String(required=True, validate=validate.Length(min=1))
    api_base = fields.Url(allow_none=True)
    api_key = fields.String(load_only=True, allow_none=True)  # Never dump the API key
    temperature = fields.Float(load_default=0.0, validate=validate.Range(min=0.0, max=2.0))
    max_tokens = fields.Integer(load_default=1024, validate=validate.Range(min=1))
    timeout = fields.Integer(load_default=60, validate=validate.Range(min=1, max=300))
    system_prompt_override = fields.String(allow_none=True)


class GradingCriterionSchema(Schema):
    """Schema for individual grading criterion."""
    criterion = fields.String(required=True, validate=validate.Length(min=1))
    weight = fields.Float(load_default=1.0, validate=validate.Range(min=0.0, max=10.0))


class EvaluationCaseSchema(Schema):
    """Schema for an individual evaluation case (input/expected pair)."""
    input = fields.String(required=True, validate=validate.Length(min=1))
    expected = fields.String(required=True, validate=validate.Length(min=1))


# ============================================================================
# Test Case Schemas
# ============================================================================

class EvaluationTestCaseCreateSchema(Schema):
    """Schema for creating a test case."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    category = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in EvaluationCategory])
    )
    evaluation_cases = fields.List(
        fields.Nested(EvaluationCaseSchema),
        required=True,
        validate=validate.Length(min=1)
    )
    grading_criteria = fields.List(
        fields.Nested(GradingCriterionSchema),
        required=True,
        validate=validate.Length(min=1)
    )
    passing_threshold = fields.Float(
        load_default=0.7,
        validate=validate.Range(min=0.0, max=1.0)
    )
    aggregation_method = fields.String(
        load_default='minimum',
        validate=validate.OneOf([e.value for e in AggregationMethod])
    )
    is_blocking = fields.Boolean(load_default=False)
    weight = fields.Float(load_default=1.0, validate=validate.Range(min=0.0, max=10.0))


class EvaluationTestCaseUpdateSchema(Schema):
    """Schema for updating a test case."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    category = fields.String(
        validate=validate.OneOf([e.value for e in EvaluationCategory])
    )
    evaluation_cases = fields.List(
        fields.Nested(EvaluationCaseSchema),
        validate=validate.Length(min=1)
    )
    grading_criteria = fields.List(
        fields.Nested(GradingCriterionSchema),
        validate=validate.Length(min=1)
    )
    passing_threshold = fields.Float(validate=validate.Range(min=0.0, max=1.0))
    aggregation_method = fields.String(
        validate=validate.OneOf([e.value for e in AggregationMethod])
    )
    is_blocking = fields.Boolean()
    weight = fields.Float(validate=validate.Range(min=0.0, max=10.0))


class EvaluationTestCaseSchema(Schema):
    """Schema for test case response."""
    id = fields.UUID(dump_only=True)
    suite_id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    category = fields.Method("get_category")
    evaluation_cases = fields.List(fields.Nested(EvaluationCaseSchema))
    grading_criteria = fields.List(fields.Nested(GradingCriterionSchema))
    passing_threshold = fields.Float()
    aggregation_method = fields.Method("get_aggregation_method")
    is_blocking = fields.Boolean()
    weight = fields.Float()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_category(self, obj):
        return obj.category.value if obj.category else None

    def get_aggregation_method(self, obj):
        return obj.aggregation_method.value if obj.aggregation_method else 'minimum'


class EvaluationTestCaseListSchema(Schema):
    """Lightweight schema for test case listing."""
    id = fields.UUID(dump_only=True)
    suite_id = fields.UUID(dump_only=True)
    name = fields.String()
    category = fields.Method("get_category")
    is_blocking = fields.Boolean()
    passing_threshold = fields.Float()

    def get_category(self, obj):
        return obj.category.value if obj.category else None


# ============================================================================
# Suite Schemas
# ============================================================================

class EvaluationSuiteCreateSchema(Schema):
    """Schema for creating an evaluation suite."""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    version = fields.String(load_default='1.0.0', validate=validate.Length(max=50))
    applicable_risk_tiers = fields.List(
        fields.String(validate=validate.OneOf([e.value for e in RiskTier])),
        required=True,
        validate=validate.Length(min=1)
    )
    is_baseline = fields.Boolean(load_default=False)
    is_extended = fields.Boolean(load_default=False)
    judge_config = fields.Nested(JudgeConfigSchema, required=True)
    test_cases = fields.List(
        fields.Nested(EvaluationTestCaseCreateSchema),
        load_default=[]
    )


class EvaluationSuiteUpdateSchema(Schema):
    """Schema for updating an evaluation suite."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True)
    version = fields.String(validate=validate.Length(max=50))
    applicable_risk_tiers = fields.List(
        fields.String(validate=validate.OneOf([e.value for e in RiskTier])),
        validate=validate.Length(min=1)
    )
    is_baseline = fields.Boolean()
    is_extended = fields.Boolean()
    is_active = fields.Boolean()
    judge_config = fields.Nested(JudgeConfigSchema)


class EvaluationSuiteSchema(Schema):
    """Schema for evaluation suite response."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    version = fields.String()
    applicable_risk_tiers = fields.List(fields.String())
    is_baseline = fields.Boolean()
    is_extended = fields.Boolean()
    judge_provider = fields.Method("get_judge_provider")
    judge_model = fields.String()
    judge_config = fields.Dict()
    is_active = fields.Boolean()
    tenant_id = fields.String()
    test_cases = fields.List(fields.Nested(EvaluationTestCaseSchema))
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_judge_provider(self, obj):
        return obj.judge_provider.value if obj.judge_provider else None

    @post_dump
    def remove_api_key(self, data, **kwargs):
        """Ensure API key is never exposed in response."""
        if data.get('judge_config') and 'api_key' in data['judge_config']:
            del data['judge_config']['api_key']
        return data


class EvaluationSuiteListSchema(Schema):
    """Lightweight schema for suite listing."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    version = fields.String()
    applicable_risk_tiers = fields.List(fields.String())
    is_baseline = fields.Boolean()
    is_extended = fields.Boolean()
    is_active = fields.Boolean()
    judge_provider = fields.Method("get_judge_provider")
    judge_model = fields.String()
    test_case_count = fields.Method("get_test_case_count")
    created_at = fields.DateTime()

    def get_judge_provider(self, obj):
        return obj.judge_provider.value if obj.judge_provider else None

    def get_test_case_count(self, obj):
        return obj.test_cases.count() if obj.test_cases else 0


# ============================================================================
# Evaluation Trigger Schema
# ============================================================================

class EvaluationTriggerSchema(Schema):
    """Schema for triggering an evaluation."""
    suite_id = fields.UUID(required=False, load_default=None)


# ============================================================================
# Result Schemas
# ============================================================================

class EvaluationResultSchema(Schema):
    """Schema for evaluation result response."""
    id = fields.UUID(dump_only=True)
    evaluation_id = fields.UUID(dump_only=True)
    test_case_id = fields.UUID(dump_only=True)
    status = fields.Method("get_status")
    score = fields.Float()
    passed = fields.Boolean()
    case_results = fields.List(fields.Dict())  # Per-case detailed results
    cases_evaluated = fields.Integer()
    input_sent = fields.String()  # First case input (for display)
    agent_response = fields.String()  # First case response (for display)
    judge_reasoning = fields.String()  # Aggregated reasoning
    criteria_scores = fields.Dict()
    agent_latency_ms = fields.Integer()
    judge_latency_ms = fields.Integer()
    agent_tokens_used = fields.Integer()
    judge_tokens_used = fields.Integer()
    error_message = fields.String()
    created_at = fields.DateTime()

    # Include test case info for context
    test_case = fields.Nested(EvaluationTestCaseListSchema)

    def get_status(self, obj):
        return obj.status.value if obj.status else None


class EvaluationResultListSchema(Schema):
    """Lightweight schema for result listing."""
    id = fields.UUID(dump_only=True)
    test_case_id = fields.UUID(dump_only=True)
    status = fields.Method("get_status")
    score = fields.Float()
    passed = fields.Boolean()

    def get_status(self, obj):
        return obj.status.value if obj.status else None


# ============================================================================
# Evaluation Schemas
# ============================================================================

class EvaluationSchema(Schema):
    """Schema for evaluation response."""
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    suite_id = fields.UUID(dump_only=True)
    status = fields.Method("get_status")
    total_tests = fields.Integer()
    passed_count = fields.Integer()
    failed_count = fields.Integer()
    error_count = fields.Integer()
    weighted_score = fields.Float()
    all_blocking_passed = fields.Boolean()
    judge_provider = fields.String()
    judge_model = fields.String()
    result_signature = fields.String()
    signature_algorithm = fields.String()
    triggered_by = fields.String()
    initiated_by = fields.String()
    started_at = fields.DateTime()
    completed_at = fields.DateTime()
    created_at = fields.DateTime()

    # Include full results for detail view
    results = fields.List(fields.Nested(EvaluationResultSchema))

    def get_status(self, obj):
        return obj.status.value if obj.status else None


class EvaluationListSchema(Schema):
    """Lightweight schema for evaluation listing."""
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID(dump_only=True)
    suite_id = fields.UUID(dump_only=True)
    suite_name = fields.Method("get_suite_name")
    status = fields.Method("get_status")
    total_tests = fields.Integer()
    passed_count = fields.Integer()
    failed_count = fields.Integer()
    weighted_score = fields.Float()
    all_blocking_passed = fields.Boolean()
    triggered_by = fields.String()
    created_at = fields.DateTime()
    completed_at = fields.DateTime()

    def get_suite_name(self, obj):
        return obj.suite.name if obj.suite else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None
