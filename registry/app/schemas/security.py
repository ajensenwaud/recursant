"""
Marshmallow schemas for security testing validation and serialization.
"""

import re
from marshmallow import Schema, fields, validate, validates, ValidationError

from app.models import ScanType, ScanStatus, ScanResultStatus, SeverityLevel


# Semantic version regex pattern
SEMVER_PATTERN = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'


# ============================================================================
# Detection Patterns Schema (nested in test cases)
# ============================================================================

class DetectionPatternsSchema(Schema):
    """Schema for test case detection patterns configuration."""
    failure_indicators = fields.List(
        fields.String(),
        load_default=[],
        metadata={'description': 'Regex patterns indicating test failure'}
    )
    success_indicators = fields.List(
        fields.String(),
        load_default=[],
        metadata={'description': 'Regex patterns indicating test success'}
    )
    detection_method = fields.String(
        load_default='regex',
        validate=validate.OneOf(['regex', 'keyword', 'semantic'])
    )


# ============================================================================
# Scan Config Schema (nested in policies)
# ============================================================================

class ScanConfigSchema(Schema):
    """Schema for per-scan-type configuration within a policy."""
    enabled = fields.Boolean(load_default=True)
    blocking = fields.Boolean(load_default=True)
    timeout_ms = fields.Integer(
        load_default=30000,
        validate=validate.Range(min=1000, max=300000)
    )


# ============================================================================
# Security Test Case Schemas
# ============================================================================

class SecurityTestCaseCreateSchema(Schema):
    """Schema for creating a custom security test case."""
    name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=255)
    )
    description = fields.String(
        required=True,
        validate=validate.Length(min=1, max=5000)
    )
    scan_type = fields.String(
        required=True,
        validate=validate.OneOf([e.value for e in ScanType])
    )
    category = fields.String(
        required=True,
        validate=validate.Length(min=1, max=100)
    )
    input_template = fields.String(
        required=True,
        validate=validate.Length(min=1, max=10000),
        metadata={'description': 'The prompt/input to send to the agent'}
    )
    detection_patterns = fields.Nested(
        DetectionPatternsSchema,
        required=True
    )
    expected_behavior = fields.String(
        required=True,
        validate=validate.Length(min=1, max=2000)
    )
    remediation_guidance = fields.String(
        allow_none=True,
        validate=validate.Length(max=5000)
    )
    severity = fields.String(
        load_default='medium',
        validate=validate.OneOf([e.value for e in SeverityLevel])
    )
    is_blocking = fields.Boolean(load_default=True)
    owasp_reference = fields.String(
        allow_none=True,
        validate=validate.Length(max=50)
    )
    cwe_reference = fields.String(
        allow_none=True,
        validate=validate.Length(max=50)
    )
    external_references = fields.List(
        fields.URL(),
        load_default=[]
    )
    version = fields.String(
        load_default='1.0.0',
        validate=validate.Length(max=50)
    )

    @validates('version')
    def validate_version(self, value):
        """Version must follow semantic versioning."""
        if value and not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )


class SecurityTestCaseUpdateSchema(Schema):
    """Schema for updating a custom security test case."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(validate=validate.Length(min=1, max=5000))
    scan_type = fields.String(validate=validate.OneOf([e.value for e in ScanType]))
    category = fields.String(validate=validate.Length(min=1, max=100))
    input_template = fields.String(validate=validate.Length(min=1, max=10000))
    detection_patterns = fields.Nested(DetectionPatternsSchema)
    expected_behavior = fields.String(validate=validate.Length(min=1, max=2000))
    remediation_guidance = fields.String(allow_none=True, validate=validate.Length(max=5000))
    severity = fields.String(validate=validate.OneOf([e.value for e in SeverityLevel]))
    is_blocking = fields.Boolean()
    owasp_reference = fields.String(allow_none=True, validate=validate.Length(max=50))
    cwe_reference = fields.String(allow_none=True, validate=validate.Length(max=50))
    external_references = fields.List(fields.URL())
    version = fields.String(validate=validate.Length(max=50))
    is_active = fields.Boolean()

    @validates('version')
    def validate_version(self, value):
        """Version must follow semantic versioning."""
        if value and not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )


class SecurityTestCaseSchema(Schema):
    """Schema for security test case response."""
    id = fields.String(dump_only=True)
    tenant_id = fields.String(allow_none=True)
    is_builtin = fields.Boolean()
    scan_type = fields.Method('get_scan_type')
    name = fields.String()
    category = fields.String()
    description = fields.String()
    input_template = fields.String()
    detection_patterns = fields.Dict()
    expected_behavior = fields.String()
    remediation_guidance = fields.String()
    severity = fields.Method('get_severity')
    is_blocking = fields.Boolean()
    owasp_reference = fields.String()
    cwe_reference = fields.String()
    external_references = fields.List(fields.String())
    version = fields.String()
    is_active = fields.Boolean()
    created_by = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()

    def get_scan_type(self, obj):
        return obj.scan_type.value if obj.scan_type else None

    def get_severity(self, obj):
        return obj.severity.value if obj.severity else None


class SecurityTestCaseListSchema(Schema):
    """Schema for listing security test cases (lighter response)."""
    id = fields.String()
    name = fields.String()
    scan_type = fields.Method('get_scan_type')
    category = fields.String()
    severity = fields.Method('get_severity')
    is_blocking = fields.Boolean()
    is_builtin = fields.Boolean()
    is_active = fields.Boolean()
    owasp_reference = fields.String()

    def get_scan_type(self, obj):
        return obj.scan_type.value if obj.scan_type else None

    def get_severity(self, obj):
        return obj.severity.value if obj.severity else None


# ============================================================================
# Security Policy Schemas
# ============================================================================

class SecurityPolicyCreateSchema(Schema):
    """Schema for creating a security policy."""
    name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=255)
    )
    description = fields.String(
        allow_none=True,
        validate=validate.Length(max=2000)
    )
    version = fields.String(
        load_default='1.0.0',
        validate=validate.Length(max=50)
    )
    applicable_risk_tiers = fields.List(
        fields.String(validate=validate.OneOf(['low', 'medium', 'high', 'critical'])),
        required=True,
        validate=validate.Length(min=1)
    )
    scan_configs = fields.Dict(
        keys=fields.String(validate=validate.OneOf([e.value for e in ScanType])),
        values=fields.Nested(ScanConfigSchema),
        required=True
    )
    is_default = fields.Boolean(load_default=False)

    @validates('version')
    def validate_version(self, value):
        """Version must follow semantic versioning."""
        if value and not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )


class SecurityPolicyUpdateSchema(Schema):
    """Schema for updating a security policy."""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, validate=validate.Length(max=2000))
    version = fields.String(validate=validate.Length(max=50))
    applicable_risk_tiers = fields.List(
        fields.String(validate=validate.OneOf(['low', 'medium', 'high', 'critical'])),
        validate=validate.Length(min=1)
    )
    scan_configs = fields.Dict(
        keys=fields.String(validate=validate.OneOf([e.value for e in ScanType])),
        values=fields.Nested(ScanConfigSchema)
    )
    is_active = fields.Boolean()
    is_default = fields.Boolean()

    @validates('version')
    def validate_version(self, value):
        """Version must follow semantic versioning."""
        if value and not re.match(SEMVER_PATTERN, value):
            raise ValidationError(
                'Version must follow semantic versioning format (MAJOR.MINOR.PATCH). '
                f'Got: {value}'
            )


class SecurityPolicySchema(Schema):
    """Schema for security policy response."""
    id = fields.UUID(dump_only=True)
    name = fields.String()
    description = fields.String()
    version = fields.String()
    applicable_risk_tiers = fields.List(fields.String())
    scan_configs = fields.Dict()
    is_active = fields.Boolean()
    is_default = fields.Boolean()
    tenant_id = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class SecurityPolicyListSchema(Schema):
    """Schema for listing security policies (lighter response)."""
    id = fields.UUID()
    name = fields.String()
    version = fields.String()
    applicable_risk_tiers = fields.List(fields.String())
    is_active = fields.Boolean()
    is_default = fields.Boolean()
    tenant_id = fields.String()


# ============================================================================
# Security Scan Result Schemas
# ============================================================================

class SecurityScanResultSchema(Schema):
    """Schema for individual scan result response."""
    id = fields.UUID(dump_only=True)
    scan_id = fields.UUID()
    scan_type = fields.Method('get_scan_type')
    test_case_id = fields.String()
    status = fields.Method('get_status')
    is_blocking = fields.Boolean()
    severity = fields.Method('get_severity')
    input_payload = fields.String()
    agent_response = fields.String()
    expected_behavior = fields.String()
    actual_behavior = fields.String()
    remediation_guidance = fields.String()
    reference_urls = fields.List(fields.String())
    execution_time_ms = fields.Integer()
    error_message = fields.String()
    created_at = fields.DateTime()

    def get_scan_type(self, obj):
        return obj.scan_type.value if obj.scan_type else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_severity(self, obj):
        return obj.severity.value if obj.severity else None


class SecurityScanResultListSchema(Schema):
    """Schema for listing scan results (lighter response)."""
    id = fields.UUID()
    scan_type = fields.Method('get_scan_type')
    test_case_id = fields.String()
    status = fields.Method('get_status')
    is_blocking = fields.Boolean()
    severity = fields.Method('get_severity')
    execution_time_ms = fields.Integer()
    error_message = fields.String()

    def get_scan_type(self, obj):
        return obj.scan_type.value if obj.scan_type else None

    def get_status(self, obj):
        return obj.status.value if obj.status else None

    def get_severity(self, obj):
        return obj.severity.value if obj.severity else None


# ============================================================================
# Security Scan Schemas
# ============================================================================

class SecurityScanTriggerSchema(Schema):
    """Schema for triggering a security scan."""
    policy_id = fields.UUID(
        allow_none=True,
        metadata={'description': 'Policy to use. If not specified, uses default for agent risk tier.'}
    )
    scan_types = fields.List(
        fields.String(validate=validate.OneOf([e.value for e in ScanType])),
        allow_none=True,
        metadata={'description': 'Specific scan types to run. If not specified, runs all enabled in policy.'}
    )


class SecurityScanSchema(Schema):
    """Schema for security scan response."""
    id = fields.UUID(dump_only=True)
    agent_id = fields.UUID()
    policy_id = fields.UUID()
    policy_version = fields.String()
    previous_scan_id = fields.UUID()
    status = fields.Method('get_status')
    total_tests = fields.Integer()
    passed_count = fields.Integer()
    failed_count = fields.Integer()
    skipped_count = fields.Integer()
    error_count = fields.Integer()
    all_blocking_passed = fields.Boolean()
    result_signature = fields.String()
    signature_algorithm = fields.String()
    triggered_by = fields.String()
    initiated_by = fields.String()
    started_at = fields.DateTime()
    completed_at = fields.DateTime()
    created_at = fields.DateTime()

    # Include results if available
    results = fields.List(fields.Nested(SecurityScanResultSchema), dump_default=[])

    def get_status(self, obj):
        return obj.status.value if obj.status else None


class SecurityScanListSchema(Schema):
    """Schema for listing security scans (lighter response)."""
    id = fields.UUID()
    agent_id = fields.UUID()
    status = fields.Method('get_status')
    total_tests = fields.Integer()
    passed_count = fields.Integer()
    failed_count = fields.Integer()
    all_blocking_passed = fields.Boolean()
    triggered_by = fields.String()
    started_at = fields.DateTime()
    completed_at = fields.DateTime()
    created_at = fields.DateTime()

    def get_status(self, obj):
        return obj.status.value if obj.status else None
