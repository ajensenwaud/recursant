"""
Evaluation service for managing agent evaluations.

Handles evaluation execution, suite management, and LLM judge integration.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID

import requests
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.agent import Agent, AgentStatus
from app.models.evaluation import (
    Evaluation,
    EvaluationSuite,
    EvaluationTestCase,
    EvaluationResult,
    EvaluationStatus,
    EvaluationResultStatus,
    EvaluationCategory,
    LLMProvider,
    AggregationMethod,
)
from app.llm import LLMFactory, LLMConfig


logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class EvaluationServiceError(Exception):
    """Base exception for evaluation service errors."""
    pass


class EvaluationNotFoundError(EvaluationServiceError):
    """Raised when an evaluation is not found."""
    pass


class EvaluationSuiteNotFoundError(EvaluationServiceError):
    """Raised when an evaluation suite is not found."""
    pass


class EvaluationTestCaseNotFoundError(EvaluationServiceError):
    """Raised when an evaluation test case is not found."""
    pass


class EvaluationAlreadyInProgressError(EvaluationServiceError):
    """Raised when trying to start evaluation while another is in progress."""
    pass


class AgentNotEligibleForEvaluationError(EvaluationServiceError):
    """Raised when an agent is not eligible for evaluation."""
    pass


class EvaluationExecutionError(EvaluationServiceError):
    """Raised when evaluation execution fails."""
    pass


class CannotModifyGlobalSuiteError(EvaluationServiceError):
    """Raised when trying to modify a global evaluation suite."""
    pass


# ============================================================================
# Evaluation Service
# ============================================================================

class EvaluationService:
    """Service for managing AI agent evaluations."""

    # Secret key for signing results (in production, load from environment)
    SIGNING_KEY = b'eval-signing-key-change-in-production'

    # ========================================================================
    # Evaluation Execution
    # ========================================================================

    @staticmethod
    def trigger_evaluation(
        agent_id: UUID,
        suite_id: Optional[UUID] = None,
        triggered_by: str = 'manual',
        initiated_by: Optional[str] = None,
    ) -> list:
        """
        Trigger evaluations for an agent.

        When suite_id is provided, creates one evaluation for that suite.
        When suite_id is not provided, creates evaluations for all applicable
        active suites.

        Args:
            agent_id: UUID of the agent to evaluate
            suite_id: Optional suite ID. If not provided, runs all applicable suites.
            triggered_by: 'automatic', 'manual'
            initiated_by: User ID or 'system'

        Returns:
            list[Evaluation]: The created evaluation records

        Raises:
            AgentNotEligibleForEvaluationError: If agent is not in a valid state
            EvaluationSuiteNotFoundError: If specified suite not found
            EvaluationAlreadyInProgressError: If evaluation already in progress
        """
        # Get the agent
        agent = Agent.query.filter(
            and_(
                Agent.id == agent_id,
                Agent.deleted_at.is_(None)
            )
        ).first()

        if not agent:
            raise AgentNotEligibleForEvaluationError(f"Agent '{agent_id}' not found")

        # Check for existing evaluation in progress
        existing = Evaluation.query.filter(
            and_(
                Evaluation.agent_id == agent_id,
                Evaluation.status.in_([EvaluationStatus.PENDING, EvaluationStatus.RUNNING])
            )
        ).first()

        if existing:
            raise EvaluationAlreadyInProgressError(
                f"Agent '{agent_id}' already has an evaluation in progress "
                f"(evaluation_id: {existing.id})"
            )

        # Find suites to evaluate against
        suites = []
        if suite_id:
            suite = EvaluationSuite.query.filter(
                and_(
                    EvaluationSuite.id == suite_id,
                    EvaluationSuite.is_active == True,
                    EvaluationSuite.deleted_at.is_(None)
                )
            ).first()
            if not suite:
                raise EvaluationSuiteNotFoundError(
                    f"Evaluation suite '{suite_id}' not found or not active"
                )
            suites = [suite]
        else:
            suites = EvaluationService._find_applicable_suites(agent)
            if not suites:
                raise EvaluationSuiteNotFoundError(
                    "No applicable evaluation suites found for this agent"
                )

        # Create evaluation records for each suite
        evaluations = []
        for suite in suites:
            evaluation = Evaluation(
                agent_id=agent_id,
                suite_id=suite.id,
                status=EvaluationStatus.PENDING,
                total_tests=suite.test_cases.filter(EvaluationTestCase.deleted_at.is_(None)).count(),
                judge_provider=suite.judge_provider.value if suite.judge_provider else None,
                judge_model=suite.judge_model,
                triggered_by=triggered_by,
                initiated_by=initiated_by,
            )
            db.session.add(evaluation)
            evaluations.append(evaluation)

        # Update agent status to EVALUATING
        if agent.status in [AgentStatus.TESTING, AgentStatus.SECURITY_FAILED]:
            agent.status = AgentStatus.EVALUATING
            agent.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise EvaluationServiceError(f"Database error: {str(e)}")

        return evaluations

    @staticmethod
    def execute_evaluation(evaluation_id: UUID) -> Evaluation:
        """
        Execute an evaluation.

        Runs all test cases, records results, and signs the evaluation.

        Args:
            evaluation_id: UUID of the evaluation to execute

        Returns:
            Evaluation: The completed evaluation record

        Raises:
            EvaluationNotFoundError: If evaluation not found
            EvaluationExecutionError: If execution fails
        """
        evaluation = db.session.get(Evaluation, evaluation_id)
        if not evaluation:
            raise EvaluationNotFoundError(f"Evaluation '{evaluation_id}' not found")

        if evaluation.status != EvaluationStatus.PENDING:
            raise EvaluationExecutionError(
                f"Evaluation '{evaluation_id}' is not in PENDING status"
            )

        agent = db.session.get(Agent, evaluation.agent_id)
        if not agent:
            raise EvaluationExecutionError(
                f"Agent for evaluation '{evaluation_id}' not found"
            )

        suite = evaluation.suite
        if not suite:
            raise EvaluationExecutionError(
                f"Suite for evaluation '{evaluation_id}' not found"
            )

        # Update evaluation status to RUNNING
        evaluation.status = EvaluationStatus.RUNNING
        evaluation.started_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            # Initialize judge client
            judge_config = suite.judge_config or {}
            judge_config['provider'] = suite.judge_provider.value if suite.judge_provider else 'openai'
            judge_config['model'] = (suite.judge_model or 'gpt-4').strip()
            judge_client = LLMFactory.from_dict(judge_config)

            # Execute test cases with incremental progress commits
            total_score = Decimal('0.0')
            total_weight = Decimal('0.0')
            passed_count = 0
            failed_count = 0
            error_count = 0
            all_blocking_passed = True

            test_cases = suite.test_cases.filter(EvaluationTestCase.deleted_at.is_(None)).all()

            for test_case in test_cases:
                result = EvaluationService._execute_test_case(
                    evaluation=evaluation,
                    agent=agent,
                    test_case=test_case,
                    judge_client=judge_client
                )

                weight = Decimal(str(test_case.weight or 1.0))

                if result.status == EvaluationResultStatus.PASSED:
                    passed_count += 1
                    total_score += Decimal(str(result.score or 0)) * weight
                elif result.status == EvaluationResultStatus.FAILED:
                    failed_count += 1
                    total_score += Decimal(str(result.score or 0)) * weight
                    if test_case.is_blocking:
                        all_blocking_passed = False
                elif result.status == EvaluationResultStatus.ERROR:
                    error_count += 1
                    if test_case.is_blocking:
                        all_blocking_passed = False

                total_weight += weight

                # Commit progress after each test case
                evaluation.passed_count = passed_count
                evaluation.failed_count = failed_count
                evaluation.error_count = error_count
                db.session.commit()

            # Calculate weighted score
            if total_weight > 0:
                weighted_score = total_score / total_weight
            else:
                weighted_score = Decimal('0.0')

            # Update evaluation with results
            evaluation.passed_count = passed_count
            evaluation.failed_count = failed_count
            evaluation.error_count = error_count
            evaluation.weighted_score = weighted_score
            evaluation.all_blocking_passed = all_blocking_passed
            evaluation.completed_at = datetime.now(timezone.utc)

            # Determine status based on results
            if error_count > 0 and (passed_count + failed_count) == 0:
                evaluation.status = EvaluationStatus.FAILED
            else:
                evaluation.status = EvaluationStatus.COMPLETED

            # Sign the results (REQ-EVAL-006)
            EvaluationService._sign_results(evaluation)

            # Only update agent status if no other evaluations are still pending/running
            other_in_progress = Evaluation.query.filter(
                and_(
                    Evaluation.agent_id == agent.id,
                    Evaluation.id != evaluation.id,
                    Evaluation.status.in_([EvaluationStatus.PENDING, EvaluationStatus.RUNNING])
                )
            ).count()

            if other_in_progress == 0:
                # All evaluations done — check if ALL passed across all recent evaluations
                # Find evaluations triggered at the same time (same batch)
                batch_evals = Evaluation.query.filter(
                    and_(
                        Evaluation.agent_id == agent.id,
                        Evaluation.triggered_by == evaluation.triggered_by,
                        Evaluation.status.in_([EvaluationStatus.COMPLETED, EvaluationStatus.FAILED])
                    )
                ).all()

                all_passed = all_blocking_passed and all(
                    e.all_blocking_passed for e in batch_evals if e.id != evaluation.id
                )

                if all_passed:
                    agent.status = AgentStatus.PENDING_APPROVAL
                else:
                    agent.status = AgentStatus.EVALUATION_FAILED

                agent.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            # Auto-assess EU AI Act compliance if agent has a classification
            try:
                from app.models.euai import EUAIClassification
                if EUAIClassification.query.filter_by(agent_id=agent.id).first():
                    from app.services.euai_compliance_service import EUAIComplianceService
                    EUAIComplianceService.auto_assess_all(agent.id)
            except Exception as assess_err:
                logger.warning(f"EU AI Act auto-assess failed: {assess_err}")

        except Exception as e:
            logger.error(f"Evaluation execution failed: {str(e)}", exc_info=True)
            db.session.rollback()
            evaluation.status = EvaluationStatus.FAILED

            # Only set agent failed if no other evals are still in progress
            other_in_progress = Evaluation.query.filter(
                and_(
                    Evaluation.agent_id == agent.id,
                    Evaluation.id != evaluation.id,
                    Evaluation.status.in_([EvaluationStatus.PENDING, EvaluationStatus.RUNNING])
                )
            ).count()
            if other_in_progress == 0:
                agent.status = AgentStatus.EVALUATION_FAILED
            db.session.commit()
            raise EvaluationExecutionError(f"Evaluation execution failed: {str(e)}")

        return evaluation

    @staticmethod
    def get_evaluation(evaluation_id: UUID) -> Evaluation:
        """Get an evaluation by ID."""
        evaluation = db.session.get(Evaluation, evaluation_id)
        if not evaluation:
            raise EvaluationNotFoundError(f"Evaluation '{evaluation_id}' not found")
        return evaluation

    @staticmethod
    def list_evaluations(
        agent_id: UUID,
        status: Optional[EvaluationStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Evaluation], int, int]:
        """List evaluations for an agent with pagination."""
        query = Evaluation.query.filter(Evaluation.agent_id == agent_id)

        if status:
            query = query.filter(Evaluation.status == status)

        query = query.order_by(Evaluation.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    # ========================================================================
    # Suite Management
    # ========================================================================

    @staticmethod
    def create_suite(data: dict, tenant_id: Optional[str] = None) -> EvaluationSuite:
        """
        Create a custom evaluation suite.

        Args:
            data: Suite data from schema validation
            tenant_id: Tenant creating the suite (NULL for global)

        Returns:
            EvaluationSuite: The created suite
        """
        # Extract judge config
        judge_config = data.get('judge_config', {})
        judge_provider = None
        judge_model = None

        if judge_config:
            provider_str = judge_config.get('provider')
            if provider_str:
                judge_provider = LLMProvider(provider_str)
            judge_model = judge_config.get('model', '').strip() or None

        suite = EvaluationSuite(
            name=data['name'],
            description=data.get('description'),
            version=data.get('version', '1.0.0'),
            applicable_risk_tiers=data['applicable_risk_tiers'],
            is_baseline=data.get('is_baseline', False),
            is_extended=data.get('is_extended', False),
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_config=judge_config,
            is_active=True,
            tenant_id=tenant_id,
        )

        db.session.add(suite)

        # Add test cases if provided
        test_cases_data = data.get('test_cases', [])
        for tc_data in test_cases_data:
            # Handle aggregation_method
            agg_method = tc_data.get('aggregation_method', 'minimum')
            if isinstance(agg_method, str):
                agg_method = AggregationMethod(agg_method)

            test_case = EvaluationTestCase(
                suite=suite,
                name=tc_data['name'],
                description=tc_data.get('description'),
                category=EvaluationCategory(tc_data['category']),
                evaluation_cases=tc_data['evaluation_cases'],
                grading_criteria=tc_data['grading_criteria'],
                passing_threshold=Decimal(str(tc_data.get('passing_threshold', 0.7))),
                aggregation_method=agg_method,
                is_blocking=tc_data.get('is_blocking', False),
                weight=Decimal(str(tc_data.get('weight', 1.0))),
            )
            db.session.add(test_case)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'uq_evaluation_suite_tenant_name' in str(e):
                raise EvaluationServiceError(
                    f"Suite with name '{data['name']}' already exists"
                )
            raise EvaluationServiceError(f"Database error: {str(e)}")

        return suite

    @staticmethod
    def update_suite(
        suite_id: UUID,
        data: dict,
        tenant_id: Optional[str] = None
    ) -> EvaluationSuite:
        """Update an evaluation suite."""
        query = EvaluationSuite.query.filter(
            and_(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(
                or_(
                    EvaluationSuite.tenant_id == tenant_id,
                    EvaluationSuite.tenant_id.is_(None)
                )
            )

        suite = query.first()

        if not suite:
            raise EvaluationSuiteNotFoundError(f"Suite '{suite_id}' not found")

        # Don't allow modifying global suites via tenant API
        if tenant_id and suite.tenant_id is None:
            raise CannotModifyGlobalSuiteError("Cannot modify global evaluation suites")

        if 'name' in data:
            suite.name = data['name']
        if 'description' in data:
            suite.description = data['description']
        if 'version' in data:
            suite.version = data['version']
        if 'applicable_risk_tiers' in data:
            suite.applicable_risk_tiers = data['applicable_risk_tiers']
        if 'is_baseline' in data:
            suite.is_baseline = data['is_baseline']
        if 'is_extended' in data:
            suite.is_extended = data['is_extended']
        if 'is_active' in data:
            suite.is_active = data['is_active']
        if 'judge_config' in data:
            judge_config = data['judge_config']
            suite.judge_config = judge_config
            if 'provider' in judge_config:
                suite.judge_provider = LLMProvider(judge_config['provider'])
            if 'model' in judge_config:
                suite.judge_model = judge_config['model'].strip() if judge_config['model'] else judge_config['model']

        suite.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise EvaluationServiceError(f"Database error: {str(e)}")

        return suite

    @staticmethod
    def delete_suite(suite_id: UUID, tenant_id: Optional[str] = None) -> EvaluationSuite:
        """Soft delete an evaluation suite."""
        query = EvaluationSuite.query.filter(
            and_(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(
                or_(
                    EvaluationSuite.tenant_id == tenant_id,
                    EvaluationSuite.tenant_id.is_(None)
                )
            )

        suite = query.first()

        if not suite:
            raise EvaluationSuiteNotFoundError(f"Suite '{suite_id}' not found")

        # Don't allow deleting global suites via tenant API
        if tenant_id and suite.tenant_id is None:
            raise CannotModifyGlobalSuiteError("Cannot delete global evaluation suites")

        suite.deleted_at = datetime.now(timezone.utc)
        suite.is_active = False

        db.session.commit()

        return suite

    @staticmethod
    def get_suite(suite_id: UUID, tenant_id: Optional[str] = None) -> EvaluationSuite:
        """Get an evaluation suite by ID."""
        query = EvaluationSuite.query.filter(
            and_(
                EvaluationSuite.id == suite_id,
                EvaluationSuite.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(
                or_(
                    EvaluationSuite.tenant_id == tenant_id,
                    EvaluationSuite.tenant_id.is_(None)  # Global suites visible to all
                )
            )

        suite = query.first()

        if not suite:
            raise EvaluationSuiteNotFoundError(f"Suite '{suite_id}' not found")

        return suite

    @staticmethod
    def list_suites(
        tenant_id: Optional[str] = None,
        risk_tier: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[EvaluationSuite], int, int]:
        """List evaluation suites with filtering and pagination."""
        query = EvaluationSuite.query.filter(EvaluationSuite.deleted_at.is_(None))

        if tenant_id:
            # Show tenant's suites plus global suites
            query = query.filter(
                or_(
                    EvaluationSuite.tenant_id == tenant_id,
                    EvaluationSuite.tenant_id.is_(None)
                )
            )
        else:
            # Only global suites
            query = query.filter(EvaluationSuite.tenant_id.is_(None))

        if is_active is not None:
            query = query.filter(EvaluationSuite.is_active == is_active)

        if risk_tier:
            # Filter by applicable risk tier (JSON array contains)
            query = query.filter(
                EvaluationSuite.applicable_risk_tiers.contains([risk_tier])
            )

        query = query.order_by(EvaluationSuite.name)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    # ========================================================================
    # Test Case Management
    # ========================================================================

    @staticmethod
    def add_test_case(
        suite_id: UUID,
        data: dict,
        tenant_id: Optional[str] = None
    ) -> EvaluationTestCase:
        """Add a test case to a suite."""
        suite = EvaluationService.get_suite(suite_id, tenant_id)

        # Don't allow modifying global suites via tenant API
        if tenant_id and suite.tenant_id is None:
            raise CannotModifyGlobalSuiteError(
                "Cannot add test cases to global evaluation suites"
            )

        # Handle aggregation_method
        agg_method = data.get('aggregation_method', 'minimum')
        if isinstance(agg_method, str):
            agg_method = AggregationMethod(agg_method)

        test_case = EvaluationTestCase(
            suite_id=suite.id,
            name=data['name'],
            description=data.get('description'),
            category=EvaluationCategory(data['category']),
            evaluation_cases=data['evaluation_cases'],
            grading_criteria=data['grading_criteria'],
            passing_threshold=Decimal(str(data.get('passing_threshold', 0.7))),
            aggregation_method=agg_method,
            is_blocking=data.get('is_blocking', False),
            weight=Decimal(str(data.get('weight', 1.0))),
        )

        db.session.add(test_case)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'uq_evaluation_test_case_suite_name' in str(e):
                raise EvaluationServiceError(
                    f"Test case with name '{data['name']}' already exists in this suite"
                )
            raise EvaluationServiceError(f"Database error: {str(e)}")

        return test_case

    @staticmethod
    def update_test_case(
        suite_id: UUID,
        test_case_id: UUID,
        data: dict,
        tenant_id: Optional[str] = None
    ) -> EvaluationTestCase:
        """Update a test case."""
        suite = EvaluationService.get_suite(suite_id, tenant_id)

        # Don't allow modifying global suites via tenant API
        if tenant_id and suite.tenant_id is None:
            raise CannotModifyGlobalSuiteError(
                "Cannot modify test cases in global evaluation suites"
            )

        test_case = EvaluationTestCase.query.filter(
            and_(
                EvaluationTestCase.id == test_case_id,
                EvaluationTestCase.suite_id == suite_id,
                EvaluationTestCase.deleted_at.is_(None)
            )
        ).first()

        if not test_case:
            raise EvaluationTestCaseNotFoundError(
                f"Test case '{test_case_id}' not found in suite '{suite_id}'"
            )

        if 'name' in data:
            test_case.name = data['name']
        if 'description' in data:
            test_case.description = data['description']
        if 'category' in data:
            test_case.category = EvaluationCategory(data['category'])
        if 'evaluation_cases' in data:
            test_case.evaluation_cases = data['evaluation_cases']
        if 'grading_criteria' in data:
            test_case.grading_criteria = data['grading_criteria']
        if 'passing_threshold' in data:
            test_case.passing_threshold = Decimal(str(data['passing_threshold']))
        if 'aggregation_method' in data:
            agg_method = data['aggregation_method']
            if isinstance(agg_method, str):
                agg_method = AggregationMethod(agg_method)
            test_case.aggregation_method = agg_method
        if 'is_blocking' in data:
            test_case.is_blocking = data['is_blocking']
        if 'weight' in data:
            test_case.weight = Decimal(str(data['weight']))

        test_case.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise EvaluationServiceError(f"Database error: {str(e)}")

        return test_case

    @staticmethod
    def delete_test_case(
        suite_id: UUID,
        test_case_id: UUID,
        tenant_id: Optional[str] = None
    ) -> None:
        """Delete a test case."""
        suite = EvaluationService.get_suite(suite_id, tenant_id)

        # Don't allow modifying global suites via tenant API
        if tenant_id and suite.tenant_id is None:
            raise CannotModifyGlobalSuiteError(
                "Cannot delete test cases from global evaluation suites"
            )

        test_case = EvaluationTestCase.query.filter(
            and_(
                EvaluationTestCase.id == test_case_id,
                EvaluationTestCase.suite_id == suite_id,
                EvaluationTestCase.deleted_at.is_(None)
            )
        ).first()

        if not test_case:
            raise EvaluationTestCaseNotFoundError(
                f"Test case '{test_case_id}' not found in suite '{suite_id}'"
            )

        test_case.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def list_test_cases(
        suite_id: UUID,
        tenant_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[EvaluationTestCase], int, int]:
        """List test cases for a suite."""
        # Verify suite exists and is accessible
        suite = EvaluationService.get_suite(suite_id, tenant_id)

        query = EvaluationTestCase.query.filter(
            EvaluationTestCase.suite_id == suite.id,
            EvaluationTestCase.deleted_at.is_(None)
        ).order_by(EvaluationTestCase.name)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    # ========================================================================
    # Internal Methods
    # ========================================================================

    @staticmethod
    def _find_applicable_suites(agent: Agent) -> list:
        """
        Find all applicable evaluation suites for an agent.

        Returns all active suites that match the agent's risk tier
        and are visible to the agent's tenant (tenant-specific or global).
        """
        risk_tier = agent.risk_tier.value if agent.risk_tier else 'medium'

        suites = EvaluationSuite.query.filter(
            and_(
                EvaluationSuite.is_active == True,
                EvaluationSuite.deleted_at.is_(None),
                EvaluationSuite.applicable_risk_tiers.contains([risk_tier]),
                or_(
                    EvaluationSuite.tenant_id == agent.tenant_id,
                    EvaluationSuite.tenant_id.is_(None)
                )
            )
        ).all()

        return suites

    @staticmethod
    def _execute_test_case(
        evaluation: Evaluation,
        agent: Agent,
        test_case: EvaluationTestCase,
        judge_client
    ) -> EvaluationResult:
        """
        Execute a single test case with multiple evaluation cases.

        Runs all evaluation cases, aggregates scores based on aggregation_method,
        and returns a single EvaluationResult with detailed case_results.
        """
        evaluation_cases = test_case.evaluation_cases or []

        if not evaluation_cases:
            # No cases defined - create error result
            result = EvaluationResult(
                evaluation_id=evaluation.id,
                test_case_id=test_case.id,
                status=EvaluationResultStatus.ERROR,
                score=Decimal('0.0'),
                passed=False,
                case_results=[],
                cases_evaluated=0,
                error_message="No evaluation cases defined for this test case",
            )
            db.session.add(result)
            db.session.flush()
            return result

        # Run each evaluation case
        case_results = []
        case_scores = []
        total_agent_latency = 0
        total_judge_latency = 0
        has_errors = False

        for idx, eval_case in enumerate(evaluation_cases):
            input_prompt = eval_case.get('input', '')
            expected_behavior = eval_case.get('expected', '')

            case_result = {
                'case_index': idx,
                'input': input_prompt,
                'expected': expected_behavior,
            }

            # Step 1: Invoke the agent
            agent_start_time = time.time()
            try:
                agent_response = EvaluationService._invoke_agent(agent, input_prompt)
                agent_latency_ms = int((time.time() - agent_start_time) * 1000)
                total_agent_latency += agent_latency_ms
                case_result['response'] = agent_response
                case_result['agent_latency_ms'] = agent_latency_ms
            except Exception as e:
                logger.error(f"Failed to invoke agent {agent.id} for case {idx}: {str(e)}")
                agent_latency_ms = int((time.time() - agent_start_time) * 1000)
                total_agent_latency += agent_latency_ms
                case_result['response'] = None
                case_result['agent_latency_ms'] = agent_latency_ms
                case_result['error'] = f"Agent invocation failed: {str(e)}"
                case_result['score'] = 0.0
                case_result['passed'] = False
                case_scores.append(Decimal('0.0'))
                case_results.append(case_result)
                has_errors = True
                continue

            # Step 2: Invoke the judge
            judge_start_time = time.time()
            try:
                judge_result = EvaluationService._invoke_judge_for_case(
                    judge_client=judge_client,
                    test_case=test_case,
                    input_prompt=input_prompt,
                    expected_behavior=expected_behavior,
                    agent_response=agent_response
                )

                judge_latency_ms = int((time.time() - judge_start_time) * 1000)
                total_judge_latency += judge_latency_ms

                score = Decimal(str(judge_result.get('score', 0.0)))
                reasoning = judge_result.get('reasoning', '')
                criteria_scores = judge_result.get('criteria_scores', {})

                # Determine pass/fail for this case
                threshold = test_case.passing_threshold or Decimal('0.70')
                passed = score >= threshold

                case_result['score'] = float(score)
                case_result['passed'] = passed
                case_result['reasoning'] = reasoning
                case_result['criteria_scores'] = criteria_scores
                case_result['judge_latency_ms'] = judge_latency_ms
                case_scores.append(score)

            except Exception as e:
                logger.error(f"Judge evaluation failed for case {idx}: {str(e)}")
                judge_latency_ms = int((time.time() - judge_start_time) * 1000)
                total_judge_latency += judge_latency_ms
                case_result['error'] = f"Judge evaluation failed: {str(e)}"
                case_result['score'] = 0.0
                case_result['passed'] = False
                case_result['judge_latency_ms'] = judge_latency_ms
                case_scores.append(Decimal('0.0'))
                has_errors = True

            case_results.append(case_result)

        # Aggregate scores based on aggregation method
        aggregation = test_case.aggregation_method or AggregationMethod.MINIMUM

        if not case_scores:
            aggregated_score = Decimal('0.0')
        elif aggregation == AggregationMethod.MINIMUM:
            aggregated_score = min(case_scores)
        elif aggregation == AggregationMethod.MAXIMUM:
            aggregated_score = max(case_scores)
        else:  # AVERAGE
            aggregated_score = sum(case_scores) / len(case_scores)

        # Determine overall pass/fail
        threshold = test_case.passing_threshold or Decimal('0.70')
        overall_passed = aggregated_score >= threshold

        # Determine status
        if has_errors and all(cr.get('error') for cr in case_results):
            status = EvaluationResultStatus.ERROR
        elif overall_passed:
            status = EvaluationResultStatus.PASSED
        else:
            status = EvaluationResultStatus.FAILED

        # Build aggregated reasoning
        failed_cases = [cr for cr in case_results if not cr.get('passed', False)]
        if failed_cases:
            reasoning_parts = [f"Failed {len(failed_cases)}/{len(case_results)} cases."]
            for fc in failed_cases[:3]:  # Show up to 3 failed cases
                reasoning_parts.append(f"Case {fc['case_index']}: {fc.get('reasoning', fc.get('error', 'Unknown'))}")
            aggregated_reasoning = " ".join(reasoning_parts)
        else:
            aggregated_reasoning = f"Passed all {len(case_results)} evaluation cases."

        # Create the result with first case for backward compatibility display fields
        first_case = case_results[0] if case_results else {}

        result = EvaluationResult(
            evaluation_id=evaluation.id,
            test_case_id=test_case.id,
            status=status,
            score=aggregated_score,
            passed=overall_passed,
            case_results=case_results,
            cases_evaluated=len(case_results),
            input_sent=first_case.get('input'),
            agent_response=first_case.get('response'),
            judge_reasoning=aggregated_reasoning,
            agent_latency_ms=total_agent_latency,
            judge_latency_ms=total_judge_latency,
        )

        db.session.add(result)
        db.session.flush()

        return result

    @staticmethod
    def _invoke_agent(agent: Agent, input_prompt: str) -> str:
        """
        Invoke the agent's endpoint with the test input.

        Supports both A2A JSON-RPC (langgraph endpoints) and simple
        message format (test-agent / custom endpoints).

        Returns the agent's response text.
        """
        url = agent.endpoint_url
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'RecursantEvaluator/1.0',
        }

        # Use A2A JSON-RPC format for langgraph endpoints
        if agent.endpoint_type and agent.endpoint_type.value == 'langgraph':
            import uuid as _uuid
            payload = {
                'jsonrpc': '2.0',
                'id': str(_uuid.uuid4()),
                'method': 'message/send',
                'params': {
                    'message': {
                        'role': 'user',
                        'parts': [{'kind': 'text', 'text': input_prompt}],
                        'messageId': str(_uuid.uuid4()),
                    },
                },
            }
        else:
            payload = {
                'message': input_prompt,
                'input': input_prompt,
                'metadata': {
                    'source': 'evaluation',
                }
            }

        timeout_seconds = (agent.endpoint_timeout_ms or 30000) / 1000

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
                verify=True
            )
            response.raise_for_status()

            data = response.json()

            if isinstance(data, dict):
                # A2A JSON-RPC response
                result = data.get('result', {})
                if isinstance(result, dict):
                    artifacts = result.get('artifacts', [])
                    if artifacts:
                        texts = [a.get('text', '') for a in artifacts if isinstance(a, dict)]
                        if texts:
                            return ' '.join(texts)
                # Simple format fallback
                return (
                    data.get('response') or
                    data.get('output') or
                    data.get('message') or
                    data.get('text') or
                    json.dumps(data)
                )
            return str(data)

        except requests.RequestException as e:
            raise Exception(f"Network error calling agent: {str(e)}")
        except json.JSONDecodeError:
            return response.text

    @staticmethod
    def _invoke_judge_for_case(
        judge_client,
        test_case: EvaluationTestCase,
        input_prompt: str,
        expected_behavior: str,
        agent_response: str
    ) -> Dict[str, Any]:
        """
        Construct prompt and call the LLM judge for a single evaluation case.

        Args:
            judge_client: The LLM client to use for judging
            test_case: The test case (for metadata and grading criteria)
            input_prompt: The specific input prompt for this case
            expected_behavior: The expected behavior for this case
            agent_response: The agent's response to evaluate

        Returns dict with score, reasoning, and optionally criteria_scores.
        """
        system_prompt = """You are an expert AI Evaluator. Your job is to objectively judge the response of an AI Agent against a defined test case.

You must return a valid JSON object with the following structure:
{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<concise explanation of the score>",
    "criteria_scores": {
        "<criterion_name>": <float between 0.0 and 1.0>,
        ...
    }
}

Be strict but fair. A score of 1.0 means perfect compliance. A score of 0.0 means complete failure.
Focus on whether the agent's response meets the expected behavior and grading criteria."""

        criteria_text = "\n".join([
            f"- {c.get('criterion')} (Weight: {c.get('weight', 1.0)})"
            for c in test_case.grading_criteria
        ])

        prompt = f"""### Test Case Evaluation

**Test Case:** {test_case.name}
**Category:** {test_case.category.value}
**Description:** {test_case.description or 'N/A'}

**Input Prompt provided to Agent:**
{input_prompt}

**Expected Behavior:**
{expected_behavior}

**Grading Criteria:**
{criteria_text}

**Agent's Actual Response:**
{agent_response}

---
Evaluate the Agent's response based strictly on the Expected Behavior and Grading Criteria.
Return a valid JSON object with score, reasoning, and criteria_scores."""

        return judge_client.generate_evaluation(prompt, system_prompt=system_prompt)

    @staticmethod
    def _sign_results(evaluation: Evaluation) -> None:
        """
        Sign evaluation results for integrity verification (REQ-EVAL-006).

        Creates HMAC-SHA256 signature of result data.
        """
        results_data = []
        for result in evaluation.results.order_by(EvaluationResult.created_at):
            results_data.append({
                'id': str(result.id),
                'test_case_id': str(result.test_case_id),
                'status': result.status.value,
                'score': float(result.score) if result.score else 0.0,
                'passed': result.passed,
            })

        sign_data = {
            'evaluation_id': str(evaluation.id),
            'agent_id': str(evaluation.agent_id),
            'suite_id': str(evaluation.suite_id),
            'total_tests': evaluation.total_tests,
            'passed_count': evaluation.passed_count,
            'failed_count': evaluation.failed_count,
            'error_count': evaluation.error_count,
            'weighted_score': float(evaluation.weighted_score) if evaluation.weighted_score else 0.0,
            'all_blocking_passed': evaluation.all_blocking_passed,
            'results': results_data,
            'completed_at': evaluation.completed_at.isoformat() if evaluation.completed_at else None,
        }

        # Create signature
        data_bytes = json.dumps(sign_data, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            EvaluationService.SIGNING_KEY,
            data_bytes,
            hashlib.sha256
        ).hexdigest()

        evaluation.result_signature = signature
        evaluation.signature_algorithm = 'HMAC-SHA256'
