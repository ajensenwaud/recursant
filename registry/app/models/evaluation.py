"""
Evaluation models for AI agent guardrails evaluation.

Provides models for evaluation suites, test cases, evaluations, and results.
Uses LLM-as-a-judge techniques with domain-specific test suites.
"""

from datetime import datetime, timezone
import enum
import uuid
from decimal import Decimal

from sqlalchemy.dialects.postgresql import UUID, JSONB
from app import db


class EvaluationStatus(enum.Enum):
    """Status of an evaluation execution."""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class EvaluationResultStatus(enum.Enum):
    """Status of an individual test result."""
    PASSED = 'passed'
    FAILED = 'failed'
    ERROR = 'error'


class EvaluationCategory(enum.Enum):
    """Categories for evaluation test cases."""
    SAFETY = 'safety'           # Critical - harmful/dangerous outputs
    POLICY = 'policy'           # Critical - organization policy compliance
    HALLUCINATION = 'hallucination'  # High - fabricated information
    BOUNDARY = 'boundary'       # High - stays within capabilities
    QUALITY = 'quality'         # Medium - accurate, relevant responses
    TONE = 'tone'               # Medium - professional communication style


class LLMProvider(enum.Enum):
    """Supported LLM providers for the judge."""
    OPENAI = 'openai'
    ANTHROPIC = 'anthropic'
    GOOGLE = 'google'
    MOONSHOT = 'moonshot'
    OPENROUTER = 'openrouter'
    CUSTOM = 'custom'


class EvaluationSuite(db.Model):
    """
    Defines a collection of test cases and judge configuration.

    An evaluation suite contains multiple test cases and configuration
    for the LLM judge that will evaluate agent responses.
    """
    __tablename__ = 'evaluation_suites'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(50), default='1.0.0')

    # Applicability
    applicable_risk_tiers = db.Column(JSONB, nullable=False, default=list)
    is_baseline = db.Column(db.Boolean, default=False)  # REQ-EVAL-001: baseline suite
    is_extended = db.Column(db.Boolean, default=False)  # REQ-EVAL-002: extended for high/critical

    # Judge configuration
    judge_provider = db.Column(db.Enum(LLMProvider))
    judge_model = db.Column(db.String(100))
    judge_config = db.Column(JSONB, nullable=False, default=dict)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    tenant_id = db.Column(db.String(255), nullable=True)  # NULL = global

    # Audit
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    test_cases = db.relationship(
        'EvaluationTestCase',
        backref='suite',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    evaluations = db.relationship(
        'Evaluation',
        back_populates='suite',
        lazy='dynamic'
    )

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_evaluation_suite_tenant_name'),
    )

    def __repr__(self):
        return f'<EvaluationSuite {self.name}>'


class AggregationMethod(enum.Enum):
    """How to aggregate scores across multiple evaluation cases."""
    MINIMUM = 'minimum'   # Test passes only if ALL cases pass (use for safety/blocking)
    AVERAGE = 'average'   # Average score across all cases (use for quality)
    MAXIMUM = 'maximum'   # Best score wins (lenient)


class EvaluationTestCase(db.Model):
    """
    Individual test case within an evaluation suite.

    Each test case defines multiple evaluation cases (input/expected pairs)
    and grading criteria for evaluating agent responses.
    """
    __tablename__ = 'evaluation_test_cases'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suite_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('evaluation_suites.id'),
        nullable=False
    )

    # Test definition
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.Enum(EvaluationCategory), nullable=False)

    # Evaluation cases - array of {input, expected} pairs
    # Structure: [{"input": "prompt text", "expected": "expected behavior"}, ...]
    evaluation_cases = db.Column(JSONB, nullable=False, default=list)

    # Grading
    grading_criteria = db.Column(JSONB, nullable=False, default=list)
    passing_threshold = db.Column(db.Numeric(3, 2), default=Decimal('0.70'))

    # How to aggregate scores when multiple cases exist
    aggregation_method = db.Column(
        db.Enum(AggregationMethod),
        default=AggregationMethod.MINIMUM,
        nullable=False
    )

    # Metadata
    is_blocking = db.Column(db.Boolean, default=False)  # If fails, entire evaluation fails
    weight = db.Column(db.Numeric(3, 2), default=Decimal('1.00'))  # Weight in overall score

    # Audit
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.Index(
            'uq_evaluation_test_case_suite_name_active',
            'suite_id', 'name',
            unique=True,
            postgresql_where=db.text('deleted_at IS NULL'),
        ),
    )

    def __repr__(self):
        return f'<EvaluationTestCase {self.name}>'


class Evaluation(db.Model):
    """
    Single execution of an evaluation suite against an agent.

    Records the overall status and results of running an evaluation suite
    against an agent's responses.
    """
    __tablename__ = 'evaluations'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('agents.id'),
        nullable=False
    )
    suite_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('evaluation_suites.id'),
        nullable=False
    )

    # Execution state
    status = db.Column(
        db.Enum(EvaluationStatus),
        nullable=False,
        default=EvaluationStatus.PENDING
    )

    # Results summary
    total_tests = db.Column(db.Integer, default=0)
    passed_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    weighted_score = db.Column(db.Numeric(5, 4), default=Decimal('0.0000'))
    all_blocking_passed = db.Column(db.Boolean, default=True)

    # Judge info
    judge_provider = db.Column(db.String(50))
    judge_model = db.Column(db.String(100))

    # Signing (REQ-EVAL-006)
    result_signature = db.Column(db.String(512))
    signature_algorithm = db.Column(db.String(50))

    # Audit
    triggered_by = db.Column(db.String(50), default='manual')  # 'automatic', 'manual'
    initiated_by = db.Column(db.String(255))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    agent = db.relationship(
        'Agent',
        backref=db.backref('evaluations', lazy='dynamic')
    )
    suite = db.relationship('EvaluationSuite', back_populates='evaluations')
    results = db.relationship(
        'EvaluationResult',
        back_populates='evaluation',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Evaluation {self.id} status={self.status.value}>'


class EvaluationResult(db.Model):
    """
    Result of a single test case execution.

    Contains detailed information about how an agent performed on a
    specific test case, including the judge's reasoning and scores.
    When multiple evaluation cases exist, case_results stores per-case details.
    """
    __tablename__ = 'evaluation_results'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('evaluations.id'),
        nullable=False
    )
    test_case_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('evaluation_test_cases.id'),
        nullable=False
    )

    # Aggregated result (across all evaluation cases)
    status = db.Column(db.Enum(EvaluationResultStatus), nullable=False)
    score = db.Column(db.Numeric(5, 4))  # 0.0000-1.0000 (aggregated)
    passed = db.Column(db.Boolean)  # aggregated score >= threshold

    # Per-case detailed results
    # Structure: [{"input": "...", "expected": "...", "response": "...",
    #              "score": 0.85, "reasoning": "...", "passed": true}, ...]
    case_results = db.Column(JSONB, default=list)

    # Summary fields (for backward compatibility / quick access)
    input_sent = db.Column(db.Text)  # First case input (for display)
    agent_response = db.Column(db.Text)  # First case response (for display)
    judge_reasoning = db.Column(db.Text)  # Aggregated reasoning
    criteria_scores = db.Column(JSONB)  # Aggregated {"criterion_name": score, ...}

    # Metrics (totals across all cases)
    agent_latency_ms = db.Column(db.Integer)
    judge_latency_ms = db.Column(db.Integer)
    agent_tokens_used = db.Column(db.Integer)
    judge_tokens_used = db.Column(db.Integer)
    cases_evaluated = db.Column(db.Integer, default=1)  # Number of cases run

    # Error handling
    error_message = db.Column(db.Text)

    # Audit
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    evaluation = db.relationship('Evaluation', back_populates='results')
    test_case = db.relationship('EvaluationTestCase')

    def __repr__(self):
        return f'<EvaluationResult {self.id} status={self.status.value} score={self.score}>'
