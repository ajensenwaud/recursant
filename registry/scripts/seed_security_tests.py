#!/usr/bin/env python3
"""
Seed built-in OWASP LLM Top 10 (2025) security test cases.

Run with: python scripts/seed_security_tests.py

These test cases are marked as is_builtin=True and tenant_id=NULL,
making them available to all tenants.

Reference: https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
"""

import sys
import os

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import SecurityTestCase, ScanType, SeverityLevel
from app.services.security_defaults import DEFAULT_SECURITY_TEST_CASES


# Alias for backward compatibility
BUILTIN_TEST_CASES = DEFAULT_SECURITY_TEST_CASES


def seed_test_cases():
    """Seed the built-in security test cases."""
    app = create_app()

    with app.app_context():
        print("Seeding OWASP LLM Top 10 (2025) security test cases...")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for test_data in BUILTIN_TEST_CASES:
            existing = db.session.get(SecurityTestCase, test_data['id'])

            if existing:
                if existing.is_builtin:
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
                    updated_count += 1
                    print(f"  Updated: {test_data['id']} - {test_data['name']}")
                else:
                    # Don't overwrite custom test cases
                    skipped_count += 1
                    print(f"  Skipped (custom): {test_data['id']} - {test_data['name']}")
            else:
                # Create new test case
                test_case = SecurityTestCase(
                    id=test_data['id'],
                    tenant_id=None,  # Built-in tests have no tenant
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
                print(f"  Created: {test_data['id']} - {test_data['name']}")

        db.session.commit()

        print(f"\nSeed complete: {created_count} created, {updated_count} updated, {skipped_count} skipped")
        print(f"Total built-in test cases: {len(BUILTIN_TEST_CASES)}")


def seed_default_policy():
    """Seed a default security policy."""
    from app.models import SecurityPolicy

    app = create_app()

    with app.app_context():
        print("\nSeeding default security policy...")

        existing = SecurityPolicy.query.filter_by(name='Default Security Policy', tenant_id=None).first()

        if existing:
            print("  Default policy already exists, skipping.")
            return

        policy = SecurityPolicy(
            name='Default Security Policy',
            description='Default security policy for all risk tiers. Runs all blocking security tests based on OWASP LLM Top 10 (2025).',
            version='2.0.0',
            applicable_risk_tiers=['low', 'medium', 'high', 'critical'],
            scan_configs={
                'prompt_injection': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'data_exfiltration': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'tool_abuse': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'egress_validation': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'credential_handling': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'input_validation': {'enabled': True, 'blocking': True, 'timeout_ms': 30000},
                'custom': {'enabled': True, 'blocking': False, 'timeout_ms': 30000},
            },
            is_active=True,
            is_default=True,
            tenant_id=None,  # Global policy
        )

        db.session.add(policy)
        db.session.commit()

        print(f"  Created: Default Security Policy (id: {policy.id})")


if __name__ == '__main__':
    seed_test_cases()
    seed_default_policy()
    print("\nDone!")
