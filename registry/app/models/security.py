"""
Security testing models for AI agent vulnerability scanning.

Provides database models for security scans, results, policies, and pluggable test cases.
Supports both built-in OWASP LLM Top 10 tests and user-created custom tests.
"""

from datetime import datetime, timezone
import enum
import uuid

from sqlalchemy.dialects.postgresql import UUID, JSONB

from app import db


class ScanType(enum.Enum):
    """Types of security scans that can be performed on agents."""
    PROMPT_INJECTION = 'prompt_injection'
    DATA_EXFILTRATION = 'data_exfiltration'
    TOOL_ABUSE = 'tool_abuse'
    EGRESS_VALIDATION = 'egress_validation'
    CREDENTIAL_HANDLING = 'credential_handling'
    INPUT_VALIDATION = 'input_validation'
    CUSTOM = 'custom'


class ScanStatus(enum.Enum):
    """Status of a security scan execution."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ScanResultStatus(enum.Enum):
    """Status of an individual test result."""
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    ERROR = 'error'


class SeverityLevel(enum.Enum):
    """Severity levels for security findings."""
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class SecurityPolicy(db.Model):
    """
    Configurable security policies per risk tier.

    Defines which scan types are enabled, blocking, and their timeouts
    for different risk levels. Supports tenant-specific policies.
    """
    __tablename__ = 'security_policies'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(50), nullable=False, default='1.0.0')

    # Which risk tiers this policy applies to (e.g., ["high", "critical"])
    applicable_risk_tiers = db.Column(JSONB, nullable=False, default=list)

    # Configuration per scan type: {"prompt_injection": {"enabled": true, "blocking": true, "timeout_ms": 30000}}
    scan_configs = db.Column(JSONB, nullable=False, default=dict)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    # Tenant-specific policies (NULL for global policies)
    tenant_id = db.Column(db.String(255), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    scans = db.relationship('SecurityScan', back_populates='policy', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_security_policy_tenant_name'),
    )

    def __repr__(self):
        return f'<SecurityPolicy {self.name} v{self.version}>'


class SecurityScan(db.Model):
    """
    Main security scan entity tracking execution against an agent.

    Records the overall scan status, aggregate results, and links to
    individual test results. Supports result signing for integrity.
    """
    __tablename__ = 'security_scans'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('agents.id'), nullable=False, index=True)
    policy_id = db.Column(UUID(as_uuid=True), db.ForeignKey('security_policies.id'), nullable=True)
    policy_version = db.Column(db.String(50), nullable=True)

    # For re-submissions (REQ-SEC-005)
    previous_scan_id = db.Column(UUID(as_uuid=True), db.ForeignKey('security_scans.id'), nullable=True)

    status = db.Column(db.Enum(ScanStatus), nullable=False, default=ScanStatus.PENDING)

    # Aggregate counts
    total_tests = db.Column(db.Integer, nullable=False, default=0)
    passed_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    error_count = db.Column(db.Integer, nullable=False, default=0)

    # REQ-SEC-001: All blocking tests must pass for agent approval
    all_blocking_passed = db.Column(db.Boolean, nullable=True)

    # REQ-SEC-003: Result signing for integrity
    result_signature = db.Column(db.String(512), nullable=True)
    signature_algorithm = db.Column(db.String(50), nullable=True, default='HMAC-SHA256')

    # Audit fields
    triggered_by = db.Column(db.String(50), nullable=False, default='manual')  # 'automatic', 'manual', 'scheduled'
    initiated_by = db.Column(db.String(255), nullable=True)  # user ID or 'system'

    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    agent = db.relationship('Agent', back_populates='security_scans')
    policy = db.relationship('SecurityPolicy', back_populates='scans')
    results = db.relationship('SecurityScanResult', back_populates='scan', lazy='dynamic', cascade='all, delete-orphan')
    previous_scan = db.relationship('SecurityScan', remote_side=[id], backref='rescan')

    def __repr__(self):
        return f'<SecurityScan {self.id} status={self.status.value}>'


class SecurityTestCase(db.Model):
    """
    Pluggable test case definitions for security scanning.

    Supports both built-in OWASP LLM Top 10 tests (is_builtin=True, tenant_id=NULL)
    and user-created custom tests (is_builtin=False, tenant_id set).
    """
    __tablename__ = 'security_test_cases'

    # UUID for custom tests, descriptive string like "OWASP-LLM-01-001" for built-in
    id = db.Column(db.String(100), primary_key=True)

    # Tenant ownership (NULL for built-in system tests)
    tenant_id = db.Column(db.String(255), nullable=True, index=True)
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)

    # Test definition
    scan_type = db.Column(db.Enum(ScanType), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # e.g., "direct_injection", "pii_disclosure"
    description = db.Column(db.Text, nullable=False)

    # Test execution configuration
    input_template = db.Column(db.Text, nullable=False)  # The prompt to send to the agent
    detection_patterns = db.Column(JSONB, nullable=False)  # {"failure_indicators": [...], "success_indicators": [...], "detection_method": "regex"}
    expected_behavior = db.Column(db.Text, nullable=False)  # What the agent should do

    # Remediation guidance (REQ-SEC-004)
    remediation_guidance = db.Column(db.Text, nullable=True)

    # Severity and blocking
    severity = db.Column(db.Enum(SeverityLevel), nullable=False, default=SeverityLevel.MEDIUM)
    is_blocking = db.Column(db.Boolean, nullable=False, default=True)

    # Reference information
    owasp_reference = db.Column(db.String(50), nullable=True)  # e.g., "LLM01"
    cwe_reference = db.Column(db.String(50), nullable=True)  # e.g., "CWE-94"
    external_references = db.Column(JSONB, nullable=True)  # Array of URLs

    # Versioning and status
    version = db.Column(db.String(50), nullable=False, default='1.0.0')
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Audit fields
    created_by = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    results = db.relationship('SecurityScanResult', back_populates='test_case', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_security_test_case_tenant_name'),
    )

    def __repr__(self):
        return f'<SecurityTestCase {self.id} {self.name}>'


class SecurityScanResult(db.Model):
    """
    Individual test result from a security scan.

    Records the input sent, agent response, evaluation outcome,
    and remediation guidance for each test case execution.
    """
    __tablename__ = 'security_scan_results'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = db.Column(UUID(as_uuid=True), db.ForeignKey('security_scans.id'), nullable=False, index=True)
    scan_type = db.Column(db.Enum(ScanType), nullable=False)
    test_case_id = db.Column(db.String(100), db.ForeignKey('security_test_cases.id'), nullable=True)

    # Result status
    status = db.Column(db.Enum(ScanResultStatus), nullable=False)
    is_blocking = db.Column(db.Boolean, nullable=False, default=True)
    severity = db.Column(db.Enum(SeverityLevel), nullable=False)

    # Execution details
    input_payload = db.Column(db.Text, nullable=True)  # What was sent to the agent
    agent_response = db.Column(db.Text, nullable=True)  # What the agent returned
    expected_behavior = db.Column(db.Text, nullable=True)
    actual_behavior = db.Column(db.Text, nullable=True)  # Summary of what happened

    # Remediation (REQ-SEC-004)
    remediation_guidance = db.Column(db.Text, nullable=True)
    reference_urls = db.Column(JSONB, nullable=True)  # Array of reference URLs

    # Execution metrics
    execution_time_ms = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    scan = db.relationship('SecurityScan', back_populates='results')
    test_case = db.relationship('SecurityTestCase', back_populates='results')

    def __repr__(self):
        return f'<SecurityScanResult {self.id} {self.status.value}>'
