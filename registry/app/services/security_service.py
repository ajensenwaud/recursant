"""
Security service for managing security scans, test cases, and policies.

Handles automated security scanning of AI agents, custom test case management,
and policy-based security configuration.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

import requests
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    Agent,
    AgentStatus,
    SecurityScan,
    SecurityScanResult,
    SecurityPolicy,
    SecurityTestCase,
    ScanType,
    ScanStatus,
    ScanResultStatus,
    SeverityLevel,
)


# ============================================================================
# Exceptions
# ============================================================================

class SecurityServiceError(Exception):
    """Base exception for security service errors."""
    pass


class SecurityScanNotFoundError(SecurityServiceError):
    """Raised when a security scan is not found."""
    pass


class SecurityPolicyNotFoundError(SecurityServiceError):
    """Raised when a security policy is not found."""
    pass


class SecurityTestCaseNotFoundError(SecurityServiceError):
    """Raised when a security test case is not found."""
    pass


class ScanAlreadyInProgressError(SecurityServiceError):
    """Raised when trying to start a scan while another is in progress."""
    pass


class AgentNotEligibleForScanError(SecurityServiceError):
    """Raised when an agent is not eligible for security scanning."""
    pass


class CannotModifyBuiltinError(SecurityServiceError):
    """Raised when trying to modify or delete a built-in test case."""
    pass


class ScanExecutionError(SecurityServiceError):
    """Raised when scan execution fails."""
    pass


# ============================================================================
# Security Service
# ============================================================================

class SecurityService:
    """Service for managing security testing of AI agents."""

    # Secret key for signing results (in production, load from environment)
    SIGNING_KEY = b'dev-signing-key-change-in-production'

    # ========================================================================
    # Scan Management
    # ========================================================================

    @staticmethod
    def trigger_scan(
        agent_id: UUID,
        policy_id: Optional[UUID] = None,
        scan_types: Optional[List[str]] = None,
        triggered_by: str = 'manual',
        initiated_by: Optional[str] = None,
    ) -> SecurityScan:
        """
        Trigger a security scan for an agent.

        Creates the scan record, updates agent status to TESTING, and
        queues scan execution.

        Args:
            agent_id: UUID of the agent to scan
            policy_id: Optional policy ID. If not provided, uses default for agent's risk tier.
            scan_types: Optional list of specific scan types. If not provided, runs all enabled.
            triggered_by: 'automatic', 'manual', or 'scheduled'
            initiated_by: User ID or 'system'

        Returns:
            SecurityScan: The created scan record

        Raises:
            AgentNotEligibleForScanError: If agent is not in a scannable state
            ScanAlreadyInProgressError: If agent already has a scan in progress
            SecurityPolicyNotFoundError: If specified policy not found
        """
        # Get the agent
        agent = Agent.query.filter(
            and_(
                Agent.id == agent_id,
                Agent.deleted_at.is_(None)
            )
        ).first()

        if not agent:
            raise AgentNotEligibleForScanError(f"Agent '{agent_id}' not found")

        # Check for existing scan in progress
        existing_scan = SecurityScan.query.filter(
            and_(
                SecurityScan.agent_id == agent_id,
                SecurityScan.status.in_([ScanStatus.PENDING, ScanStatus.RUNNING])
            )
        ).first()

        if existing_scan:
            raise ScanAlreadyInProgressError(
                f"Agent '{agent_id}' already has a scan in progress (scan_id: {existing_scan.id})"
            )

        # Find the most recent completed scan for this agent (for REQ-SEC-005)
        previous_scan = SecurityScan.query.filter(
            and_(
                SecurityScan.agent_id == agent_id,
                SecurityScan.status == ScanStatus.COMPLETED
            )
        ).order_by(SecurityScan.created_at.desc()).first()

        # Get or find the appropriate policy
        policy = None
        if policy_id:
            policy = SecurityPolicy.query.filter(
                and_(
                    SecurityPolicy.id == policy_id,
                    SecurityPolicy.is_active == True,
                    SecurityPolicy.deleted_at.is_(None)
                )
            ).first()
            if not policy:
                raise SecurityPolicyNotFoundError(f"Policy '{policy_id}' not found or not active")
        else:
            # Find default policy for agent's risk tier
            policy = SecurityPolicy.query.filter(
                and_(
                    SecurityPolicy.is_active == True,
                    SecurityPolicy.is_default == True,
                    SecurityPolicy.deleted_at.is_(None),
                    or_(
                        SecurityPolicy.tenant_id == agent.tenant_id,
                        SecurityPolicy.tenant_id.is_(None)
                    )
                )
            ).first()

        # Create the scan
        scan = SecurityScan(
            agent_id=agent_id,
            policy_id=policy.id if policy else None,
            policy_version=policy.version if policy else None,
            previous_scan_id=previous_scan.id if previous_scan else None,
            status=ScanStatus.PENDING,
            triggered_by=triggered_by,
            initiated_by=initiated_by,
        )

        db.session.add(scan)

        # Update agent status to TESTING
        agent.status = AgentStatus.TESTING
        agent.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        return scan

    @staticmethod
    def execute_scan(scan_id: UUID) -> SecurityScan:
        """
        Execute a security scan.

        Runs all enabled test cases, records results, signs the results,
        and updates scan status.

        Args:
            scan_id: UUID of the scan to execute

        Returns:
            SecurityScan: The completed scan record

        Raises:
            SecurityScanNotFoundError: If scan not found
            ScanExecutionError: If execution fails
        """
        scan = db.session.get(SecurityScan, scan_id)
        if not scan:
            raise SecurityScanNotFoundError(f"Scan '{scan_id}' not found")

        if scan.status not in [ScanStatus.PENDING]:
            raise ScanExecutionError(f"Scan '{scan_id}' is not in PENDING status")

        agent = db.session.get(Agent, scan.agent_id)
        if not agent:
            raise ScanExecutionError(f"Agent for scan '{scan_id}' not found")

        # Update scan status to RUNNING
        scan.status = ScanStatus.RUNNING
        scan.started_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            # Get test cases for this scan
            test_cases = SecurityService._get_test_cases_for_scan(
                scan=scan,
                agent=agent
            )

            # Set total_tests before the loop so frontend can track progress
            scan.total_tests = len(test_cases)
            scan.passed_count = 0
            scan.failed_count = 0
            scan.skipped_count = 0
            scan.error_count = 0
            db.session.commit()

            # Execute each test case with incremental commits
            passed_count = 0
            failed_count = 0
            skipped_count = 0
            error_count = 0
            all_blocking_passed = True

            for test_case in test_cases:
                result = SecurityService._execute_test_case(
                    scan=scan,
                    agent=agent,
                    test_case=test_case
                )

                if result.status == ScanResultStatus.PASSED:
                    passed_count += 1
                elif result.status == ScanResultStatus.FAILED:
                    failed_count += 1
                    if result.is_blocking:
                        all_blocking_passed = False
                elif result.status == ScanResultStatus.SKIPPED:
                    skipped_count += 1
                elif result.status == ScanResultStatus.ERROR:
                    error_count += 1
                    if result.is_blocking:
                        all_blocking_passed = False

                # Commit progress after each test case
                scan.passed_count = passed_count
                scan.failed_count = failed_count
                scan.skipped_count = skipped_count
                scan.error_count = error_count
                db.session.commit()

            # Update final scan results
            scan.all_blocking_passed = all_blocking_passed
            scan.status = ScanStatus.COMPLETED
            scan.completed_at = datetime.now(timezone.utc)

            # Sign the results (REQ-SEC-003)
            SecurityService._sign_results(scan)

            # Update agent status based on results
            if all_blocking_passed:
                agent.status = AgentStatus.EVALUATING
            else:
                agent.status = AgentStatus.SECURITY_FAILED

            agent.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            # Auto-trigger evaluation if security scan passed
            if all_blocking_passed:
                SecurityService._auto_trigger_evaluation(agent)

        except Exception as e:
            db.session.rollback()
            scan.status = ScanStatus.FAILED
            scan.completed_at = datetime.now(timezone.utc)
            agent.status = AgentStatus.SECURITY_FAILED
            db.session.commit()
            raise ScanExecutionError(f"Scan execution failed: {str(e)}")

        return scan

    @staticmethod
    def get_scan(scan_id: UUID) -> SecurityScan:
        """Get a security scan by ID."""
        scan = db.session.get(SecurityScan, scan_id)
        if not scan:
            raise SecurityScanNotFoundError(f"Security scan '{scan_id}' not found")
        return scan

    @staticmethod
    def list_scans(
        agent_id: UUID,
        status: Optional[ScanStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        """List security scans for an agent with pagination."""
        query = SecurityScan.query.filter(SecurityScan.agent_id == agent_id)

        if status:
            query = query.filter(SecurityScan.status == status)

        query = query.order_by(SecurityScan.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    # ========================================================================
    # Test Case Management (Pluggable)
    # ========================================================================

    @staticmethod
    def create_test_case(
        data: dict,
        tenant_id: str,
        created_by: str
    ) -> SecurityTestCase:
        """
        Create a custom security test case.

        Args:
            data: Test case data from schema validation
            tenant_id: Tenant creating the test case
            created_by: User ID creating the test case

        Returns:
            SecurityTestCase: The created test case

        Raises:
            SecurityServiceError: If creation fails
        """
        # Generate UUID for custom test cases
        test_case_id = str(uuid.uuid4())

        test_case = SecurityTestCase(
            id=test_case_id,
            tenant_id=tenant_id,
            is_builtin=False,
            scan_type=ScanType(data['scan_type']),
            name=data['name'],
            category=data['category'],
            description=data['description'],
            input_template=data['input_template'],
            detection_patterns=data['detection_patterns'],
            expected_behavior=data['expected_behavior'],
            remediation_guidance=data.get('remediation_guidance'),
            severity=SeverityLevel(data.get('severity', 'medium')),
            is_blocking=data.get('is_blocking', True),
            owasp_reference=data.get('owasp_reference'),
            cwe_reference=data.get('cwe_reference'),
            external_references=data.get('external_references', []),
            version=data.get('version', '1.0.0'),
            is_active=True,
            created_by=created_by,
        )

        db.session.add(test_case)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'uq_security_test_case_tenant_name' in str(e):
                raise SecurityServiceError(
                    f"Test case with name '{data['name']}' already exists for this tenant"
                )
            raise SecurityServiceError(f"Database error: {str(e)}")

        return test_case

    @staticmethod
    def update_test_case(
        test_case_id: str,
        data: dict,
        tenant_id: str
    ) -> SecurityTestCase:
        """
        Update a custom security test case.

        Args:
            test_case_id: ID of the test case to update
            data: Update data from schema validation
            tenant_id: Tenant making the update

        Returns:
            SecurityTestCase: The updated test case

        Raises:
            SecurityTestCaseNotFoundError: If test case not found
            CannotModifyBuiltinError: If trying to modify a built-in test
        """
        test_case = SecurityTestCase.query.filter(
            and_(
                SecurityTestCase.id == test_case_id,
                SecurityTestCase.deleted_at.is_(None)
            )
        ).first()

        if not test_case:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        if test_case.is_builtin:
            raise CannotModifyBuiltinError("Cannot modify built-in test cases")

        if test_case.tenant_id != tenant_id:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        # Update fields
        if 'name' in data:
            test_case.name = data['name']
        if 'description' in data:
            test_case.description = data['description']
        if 'scan_type' in data:
            test_case.scan_type = ScanType(data['scan_type'])
        if 'category' in data:
            test_case.category = data['category']
        if 'input_template' in data:
            test_case.input_template = data['input_template']
        if 'detection_patterns' in data:
            test_case.detection_patterns = data['detection_patterns']
        if 'expected_behavior' in data:
            test_case.expected_behavior = data['expected_behavior']
        if 'remediation_guidance' in data:
            test_case.remediation_guidance = data['remediation_guidance']
        if 'severity' in data:
            test_case.severity = SeverityLevel(data['severity'])
        if 'is_blocking' in data:
            test_case.is_blocking = data['is_blocking']
        if 'owasp_reference' in data:
            test_case.owasp_reference = data['owasp_reference']
        if 'cwe_reference' in data:
            test_case.cwe_reference = data['cwe_reference']
        if 'external_references' in data:
            test_case.external_references = data['external_references']
        if 'version' in data:
            test_case.version = data['version']
        if 'is_active' in data:
            test_case.is_active = data['is_active']

        test_case.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise SecurityServiceError(f"Database error: {str(e)}")

        return test_case

    @staticmethod
    def delete_test_case(test_case_id: str, tenant_id: str) -> SecurityTestCase:
        """
        Soft delete a custom security test case.

        Args:
            test_case_id: ID of the test case to delete
            tenant_id: Tenant making the deletion

        Returns:
            SecurityTestCase: The deleted test case

        Raises:
            SecurityTestCaseNotFoundError: If test case not found
            CannotModifyBuiltinError: If trying to delete a built-in test
        """
        test_case = SecurityTestCase.query.filter(
            and_(
                SecurityTestCase.id == test_case_id,
                SecurityTestCase.deleted_at.is_(None)
            )
        ).first()

        if not test_case:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        if test_case.is_builtin:
            raise CannotModifyBuiltinError("Cannot delete built-in test cases")

        if test_case.tenant_id != tenant_id:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        test_case.deleted_at = datetime.now(timezone.utc)
        test_case.is_active = False

        db.session.commit()

        return test_case

    @staticmethod
    def get_test_case(test_case_id: str, tenant_id: Optional[str] = None) -> SecurityTestCase:
        """
        Get a security test case by ID.

        Built-in tests are visible to all tenants. Custom tests are only
        visible to their owning tenant.
        """
        test_case = SecurityTestCase.query.filter(
            and_(
                SecurityTestCase.id == test_case_id,
                SecurityTestCase.deleted_at.is_(None)
            )
        ).first()

        if not test_case:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        # Built-in tests are visible to everyone
        if test_case.is_builtin:
            return test_case

        # Custom tests are only visible to their tenant
        if tenant_id and test_case.tenant_id != tenant_id:
            raise SecurityTestCaseNotFoundError(f"Test case '{test_case_id}' not found")

        return test_case

    @staticmethod
    def list_test_cases(
        tenant_id: Optional[str] = None,
        scan_type: Optional[str] = None,
        is_builtin: Optional[bool] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        """
        List security test cases with filtering and pagination.

        Returns built-in tests plus tenant's custom tests.
        """
        # Base query: not deleted
        query = SecurityTestCase.query.filter(SecurityTestCase.deleted_at.is_(None))

        # Filter visibility: built-in OR belonging to tenant
        if tenant_id:
            query = query.filter(
                or_(
                    SecurityTestCase.is_builtin == True,
                    SecurityTestCase.tenant_id == tenant_id
                )
            )
        else:
            # No tenant specified, only show built-in
            query = query.filter(SecurityTestCase.is_builtin == True)

        # Apply filters
        if scan_type:
            query = query.filter(SecurityTestCase.scan_type == ScanType(scan_type))

        if is_builtin is not None:
            query = query.filter(SecurityTestCase.is_builtin == is_builtin)

        if is_active is not None:
            query = query.filter(SecurityTestCase.is_active == is_active)

        query = query.order_by(SecurityTestCase.name)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    @staticmethod
    def reset_to_defaults(tenant_id: Optional[str] = None) -> dict:
        """
        Reset built-in security test cases to OWASP defaults.

        Re-creates or updates all built-in test cases from the canonical
        definitions in security_defaults.py.

        Args:
            tenant_id: Not used for built-in tests but kept for API consistency.

        Returns:
            dict with created, updated, and skipped counts.
        """
        from app.services.security_defaults import DEFAULT_SECURITY_TEST_CASES

        created_count = 0
        updated_count = 0

        for test_data in DEFAULT_SECURITY_TEST_CASES:
            existing = db.session.get(SecurityTestCase, test_data['id'])

            if existing:
                # Update existing built-in test case
                existing.name = test_data['name']
                existing.category = test_data['category']
                existing.scan_type = test_data['scan_type']
                existing.description = test_data['description']
                existing.input_template = test_data['input_template']
                existing.detection_patterns = test_data['detection_patterns']
                existing.expected_behavior = test_data['expected_behavior']
                existing.remediation_guidance = test_data['remediation_guidance']
                existing.severity = test_data['severity']
                existing.is_blocking = test_data['is_blocking']
                existing.owasp_reference = test_data['owasp_reference']
                existing.cwe_reference = test_data['cwe_reference']
                existing.external_references = test_data['external_references']
                existing.is_builtin = True
                existing.is_active = True
                existing.deleted_at = None
                updated_count += 1
            else:
                test_case = SecurityTestCase(
                    id=test_data['id'],
                    tenant_id=None,
                    is_builtin=True,
                    scan_type=test_data['scan_type'],
                    name=test_data['name'],
                    category=test_data['category'],
                    description=test_data['description'],
                    input_template=test_data['input_template'],
                    detection_patterns=test_data['detection_patterns'],
                    expected_behavior=test_data['expected_behavior'],
                    remediation_guidance=test_data['remediation_guidance'],
                    severity=test_data['severity'],
                    is_blocking=test_data['is_blocking'],
                    owasp_reference=test_data['owasp_reference'],
                    cwe_reference=test_data['cwe_reference'],
                    external_references=test_data['external_references'],
                    version='2.0.0',
                    is_active=True,
                    created_by='system',
                )
                db.session.add(test_case)
                created_count += 1

        db.session.commit()

        return {
            'created': created_count,
            'updated': updated_count,
            'total': len(DEFAULT_SECURITY_TEST_CASES),
        }

    # ========================================================================
    # Policy Management
    # ========================================================================

    @staticmethod
    def create_policy(data: dict, tenant_id: Optional[str] = None) -> SecurityPolicy:
        """Create a security policy."""
        policy = SecurityPolicy(
            name=data['name'],
            description=data.get('description'),
            version=data.get('version', '1.0.0'),
            applicable_risk_tiers=data['applicable_risk_tiers'],
            scan_configs=data['scan_configs'],
            is_active=True,
            is_default=data.get('is_default', False),
            tenant_id=tenant_id,
        )

        db.session.add(policy)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if 'uq_security_policy_tenant_name' in str(e):
                raise SecurityServiceError(
                    f"Policy with name '{data['name']}' already exists"
                )
            raise SecurityServiceError(f"Database error: {str(e)}")

        return policy

    @staticmethod
    def update_policy(
        policy_id: UUID,
        data: dict,
        tenant_id: Optional[str] = None
    ) -> SecurityPolicy:
        """Update a security policy."""
        query = SecurityPolicy.query.filter(
            and_(
                SecurityPolicy.id == policy_id,
                SecurityPolicy.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(
                or_(
                    SecurityPolicy.tenant_id == tenant_id,
                    SecurityPolicy.tenant_id.is_(None)
                )
            )

        policy = query.first()

        if not policy:
            raise SecurityPolicyNotFoundError(f"Policy '{policy_id}' not found")

        if 'name' in data:
            policy.name = data['name']
        if 'description' in data:
            policy.description = data['description']
        if 'version' in data:
            policy.version = data['version']
        if 'applicable_risk_tiers' in data:
            policy.applicable_risk_tiers = data['applicable_risk_tiers']
        if 'scan_configs' in data:
            policy.scan_configs = data['scan_configs']
        if 'is_active' in data:
            policy.is_active = data['is_active']
        if 'is_default' in data:
            policy.is_default = data['is_default']

        policy.updated_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise SecurityServiceError(f"Database error: {str(e)}")

        return policy

    @staticmethod
    def delete_policy(policy_id: UUID, tenant_id: Optional[str] = None) -> SecurityPolicy:
        """Soft delete a security policy."""
        query = SecurityPolicy.query.filter(
            and_(
                SecurityPolicy.id == policy_id,
                SecurityPolicy.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(SecurityPolicy.tenant_id == tenant_id)

        policy = query.first()

        if not policy:
            raise SecurityPolicyNotFoundError(f"Policy '{policy_id}' not found")

        # Don't allow deleting global policies via tenant API
        if tenant_id and policy.tenant_id is None:
            raise SecurityServiceError("Cannot delete global policies")

        policy.deleted_at = datetime.now(timezone.utc)
        policy.is_active = False

        db.session.commit()

        return policy

    @staticmethod
    def get_policy(policy_id: UUID, tenant_id: Optional[str] = None) -> SecurityPolicy:
        """Get a security policy by ID."""
        query = SecurityPolicy.query.filter(
            and_(
                SecurityPolicy.id == policy_id,
                SecurityPolicy.deleted_at.is_(None)
            )
        )

        if tenant_id:
            query = query.filter(
                or_(
                    SecurityPolicy.tenant_id == tenant_id,
                    SecurityPolicy.tenant_id.is_(None)
                )
            )

        policy = query.first()

        if not policy:
            raise SecurityPolicyNotFoundError(f"Policy '{policy_id}' not found")

        return policy

    @staticmethod
    def list_policies(
        tenant_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple:
        """List security policies with filtering and pagination."""
        query = SecurityPolicy.query.filter(SecurityPolicy.deleted_at.is_(None))

        if tenant_id:
            query = query.filter(
                or_(
                    SecurityPolicy.tenant_id == tenant_id,
                    SecurityPolicy.tenant_id.is_(None)
                )
            )
        else:
            query = query.filter(SecurityPolicy.tenant_id.is_(None))

        if is_active is not None:
            query = query.filter(SecurityPolicy.is_active == is_active)

        query = query.order_by(SecurityPolicy.name)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total, pagination.pages

    # ========================================================================
    # Internal Methods
    # ========================================================================

    @staticmethod
    def _get_test_cases_for_scan(scan: SecurityScan, agent: Agent) -> List[SecurityTestCase]:
        """
        Get all test cases to run for a scan.

        Returns built-in active tests plus tenant's custom tests.
        Custom tests can override built-in tests by using the same category.
        """
        # Get enabled scan types from policy
        enabled_scan_types = set()
        if scan.policy_id:
            policy = db.session.get(SecurityPolicy, scan.policy_id)
            if policy and policy.scan_configs:
                for scan_type, config in policy.scan_configs.items():
                    if config.get('enabled', True):
                        enabled_scan_types.add(scan_type)
        else:
            # No policy, enable all types
            enabled_scan_types = {st.value for st in ScanType}

        # Get all active test cases (built-in + tenant custom)
        test_cases = SecurityTestCase.query.filter(
            and_(
                SecurityTestCase.deleted_at.is_(None),
                SecurityTestCase.is_active == True,
                or_(
                    SecurityTestCase.is_builtin == True,
                    SecurityTestCase.tenant_id == agent.tenant_id
                )
            )
        ).all()

        # Filter by enabled scan types
        filtered_cases = [
            tc for tc in test_cases
            if tc.scan_type.value in enabled_scan_types
        ]

        # Handle custom test case overrides by category
        # If a custom test has the same category as a built-in, use the custom one
        result = {}
        for tc in filtered_cases:
            key = (tc.scan_type.value, tc.category)
            if key not in result:
                result[key] = tc
            elif not tc.is_builtin:
                # Custom test overrides built-in
                result[key] = tc

        return list(result.values())

    @staticmethod
    def _execute_test_case(
        scan: SecurityScan,
        agent: Agent,
        test_case: SecurityTestCase
    ) -> SecurityScanResult:
        """Execute a single test case and record the result."""
        start_time = time.time()
        result_status = ScanResultStatus.PASSED
        error_message = None
        agent_response = None
        actual_behavior = None

        try:
            # Call the agent with the test input
            agent_response = SecurityService._call_agent(
                agent=agent,
                input_payload=test_case.input_template
            )

            # Evaluate the response
            passed, actual_behavior = SecurityService._evaluate_response(
                response=agent_response,
                detection_patterns=test_case.detection_patterns
            )

            result_status = ScanResultStatus.PASSED if passed else ScanResultStatus.FAILED

        except requests.Timeout:
            result_status = ScanResultStatus.ERROR
            error_message = "Agent request timed out"
        except requests.RequestException as e:
            result_status = ScanResultStatus.ERROR
            error_message = f"Agent request failed: {str(e)}"
        except Exception as e:
            result_status = ScanResultStatus.ERROR
            error_message = f"Test execution error: {str(e)}"

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Create result record
        result = SecurityScanResult(
            scan_id=scan.id,
            scan_type=test_case.scan_type,
            test_case_id=test_case.id,
            status=result_status,
            is_blocking=test_case.is_blocking,
            severity=test_case.severity,
            input_payload=test_case.input_template,
            agent_response=agent_response,
            expected_behavior=test_case.expected_behavior,
            actual_behavior=actual_behavior,
            remediation_guidance=test_case.remediation_guidance if result_status == ScanResultStatus.FAILED else None,
            reference_urls=test_case.external_references,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
        )

        db.session.add(result)
        db.session.flush()

        return result

    @staticmethod
    def _call_agent(agent: Agent, input_payload: str) -> str:
        """
        Call the agent endpoint with the test input.

        Handles different endpoint types and authentication methods.
        Supports both A2A JSON-RPC (langgraph endpoints) and simple
        message format (test-agent / custom endpoints).
        """
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'RecursantSecurityScanner/1.0',
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
                        'parts': [{'kind': 'text', 'text': input_payload}],
                        'messageId': str(_uuid.uuid4()),
                    },
                },
            }
        else:
            payload = {
                'message': input_payload,
                'metadata': {
                    'source': 'security_scan',
                }
            }

        timeout_seconds = (agent.endpoint_timeout_ms or 30000) / 1000

        try:
            response = requests.post(
                agent.endpoint_url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
                verify=True
            )
            response.raise_for_status()

            response_data = response.json()

            # Extract response text based on format
            if isinstance(response_data, dict):
                # A2A JSON-RPC response
                result = response_data.get('result', {})
                if isinstance(result, dict):
                    artifacts = result.get('artifacts', [])
                    if artifacts:
                        texts = [a.get('text', '') for a in artifacts if isinstance(a, dict)]
                        if texts:
                            return ' '.join(texts)
                # Simple format fallback
                return response_data.get('response', response_data.get('message', str(response_data)))
            return str(response_data)

        except requests.RequestException:
            raise

    @staticmethod
    def _evaluate_response(
        response: str,
        detection_patterns: dict
    ) -> tuple:
        """
        Evaluate agent response against detection patterns.

        Checks success indicators before failure indicators so that an agent
        that correctly refuses a request (matching a success pattern) is not
        penalised for quoting or referencing the attack vector in its refusal.

        Returns:
            tuple: (passed: bool, actual_behavior: str)
        """
        failure_indicators = detection_patterns.get('failure_indicators', [])
        success_indicators = detection_patterns.get('success_indicators', [])
        detection_method = detection_patterns.get('detection_method', 'regex')

        if not response:
            return False, "No response from agent"

        response_lower = response.lower()

        def _matches(pattern, method):
            if method == 'regex':
                return re.search(pattern, response, re.IGNORECASE)
            elif method == 'keyword':
                return pattern.lower() in response_lower
            return False

        # Check success indicators first — if the agent is clearly refusing
        # the request, it should pass even if the response quotes the attack
        # vector (e.g. mentioning "EXFIL_MARKER" while explaining it won't
        # follow the hidden instruction).
        success_match = None
        if success_indicators:
            for pattern in success_indicators:
                if _matches(pattern, detection_method):
                    success_match = pattern
                    break

        # Check for failure indicators
        failure_match = None
        for pattern in failure_indicators:
            if _matches(pattern, detection_method):
                failure_match = pattern
                break

        # If both success and failure matched, success takes priority
        # (agent refused but quoted the attack vector in its explanation)
        if success_match:
            return True, f"Response matched success pattern: {success_match}"

        if failure_match:
            return False, f"Response matched failure pattern: {failure_match}"

        # No failure indicators matched
        if success_indicators:
            # Success indicators were defined but none matched
            return False, "Response did not match any success indicators"

        # No success indicators and no failure indicators matched
        return True, "Response passed (no failure indicators matched)"

    @staticmethod
    def _sign_results(scan: SecurityScan) -> None:
        """
        Sign scan results for integrity verification (REQ-SEC-003).

        Creates HMAC-SHA256 signature of result data.
        """
        # Build data to sign
        results_data = []
        for result in scan.results.order_by(SecurityScanResult.created_at):
            results_data.append({
                'id': str(result.id),
                'test_case_id': result.test_case_id,
                'status': result.status.value,
                'is_blocking': result.is_blocking,
            })

        sign_data = {
            'scan_id': str(scan.id),
            'agent_id': str(scan.agent_id),
            'total_tests': scan.total_tests,
            'passed_count': scan.passed_count,
            'failed_count': scan.failed_count,
            'all_blocking_passed': scan.all_blocking_passed,
            'results': results_data,
            'completed_at': scan.completed_at.isoformat() if scan.completed_at else None,
        }

        # Create signature
        data_bytes = json.dumps(sign_data, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            SecurityService.SIGNING_KEY,
            data_bytes,
            hashlib.sha256
        ).hexdigest()

        scan.result_signature = signature
        scan.signature_algorithm = 'HMAC-SHA256'

    @staticmethod
    def _auto_trigger_evaluation(agent: Agent) -> None:
        """
        Auto-trigger evaluation after security scan passes.

        This is called internally after a successful security scan.
        Evaluation failures here are logged but don't affect the scan status.
        """
        try:
            # Import here to avoid circular dependency
            from app.services.evaluation_service import (
                EvaluationService,
                EvaluationSuiteNotFoundError,
                EvaluationAlreadyInProgressError,
            )

            # Trigger evaluations for all applicable suites
            evaluations = EvaluationService.trigger_evaluation(
                agent_id=agent.id,
                triggered_by='automatic',
                initiated_by='system'
            )

            # Execute all evaluations
            for evaluation in evaluations:
                EvaluationService.execute_evaluation(evaluation.id)

        except EvaluationSuiteNotFoundError:
            # No evaluation suite configured - log and continue
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"No evaluation suite found for agent {agent.id}. "
                "Skipping automatic evaluation."
            )
        except EvaluationAlreadyInProgressError:
            # Evaluation already running - this shouldn't happen but log it
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Evaluation already in progress for agent {agent.id}. "
                "Skipping automatic trigger."
            )
        except Exception as e:
            # Log error but don't fail the security scan
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to auto-trigger evaluation for agent {agent.id}: {str(e)}",
                exc_info=True
            )
