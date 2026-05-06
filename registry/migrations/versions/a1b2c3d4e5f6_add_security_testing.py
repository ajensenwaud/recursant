"""Add security testing tables

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-01-24

Adds tables for:
- security_policies: Configurable security policies per risk tier
- security_test_cases: Pluggable test case definitions (built-in + custom)
- security_scans: Main scan entity tracking execution
- security_scan_results: Individual test results
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name):
    """Check if an index exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in inspector.get_table_names():
        indexes = inspector.get_indexes(table)
        if any(idx['name'] == index_name for idx in indexes):
            return True
    return False


def upgrade():
    # Create enum types if they don't exist
    bind = op.get_bind()

    # Check and create enums
    result = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'scantype'"))
    if not result.fetchone():
        op.execute("CREATE TYPE scantype AS ENUM ('prompt_injection', 'data_exfiltration', 'tool_abuse', 'egress_validation', 'credential_handling', 'input_validation', 'custom')")

    result = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'scanstatus'"))
    if not result.fetchone():
        op.execute("CREATE TYPE scanstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")

    result = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'scanresultstatus'"))
    if not result.fetchone():
        op.execute("CREATE TYPE scanresultstatus AS ENUM ('passed', 'failed', 'skipped', 'error')")

    result = bind.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'severitylevel'"))
    if not result.fetchone():
        op.execute("CREATE TYPE severitylevel AS ENUM ('info', 'low', 'medium', 'high', 'critical')")

    # Create security_policies table
    if not table_exists('security_policies'):
        op.create_table(
            'security_policies',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('version', sa.String(50), nullable=False, server_default='1.0.0'),
            sa.Column('applicable_risk_tiers', postgresql.JSONB, nullable=False, server_default='[]'),
            sa.Column('scan_configs', postgresql.JSONB, nullable=False, server_default='{}'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('tenant_id', sa.String(255), nullable=True, index=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint('tenant_id', 'name', name='uq_security_policy_tenant_name'),
        )

    # Create security_test_cases table
    if not table_exists('security_test_cases'):
        op.create_table(
            'security_test_cases',
            sa.Column('id', sa.String(100), primary_key=True),
            sa.Column('tenant_id', sa.String(255), nullable=True, index=True),
            sa.Column('is_builtin', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('scan_type', postgresql.ENUM('prompt_injection', 'data_exfiltration', 'tool_abuse', 'egress_validation', 'credential_handling', 'input_validation', 'custom', name='scantype', create_type=False), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('description', sa.Text, nullable=False),
            sa.Column('input_template', sa.Text, nullable=False),
            sa.Column('detection_patterns', postgresql.JSONB, nullable=False),
            sa.Column('expected_behavior', sa.Text, nullable=False),
            sa.Column('remediation_guidance', sa.Text, nullable=True),
            sa.Column('severity', postgresql.ENUM('info', 'low', 'medium', 'high', 'critical', name='severitylevel', create_type=False), nullable=False, server_default='medium'),
            sa.Column('is_blocking', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('owasp_reference', sa.String(50), nullable=True),
            sa.Column('cwe_reference', sa.String(50), nullable=True),
            sa.Column('external_references', postgresql.JSONB, nullable=True),
            sa.Column('version', sa.String(50), nullable=False, server_default='1.0.0'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint('tenant_id', 'name', name='uq_security_test_case_tenant_name'),
        )

    # Create security_scans table
    if not table_exists('security_scans'):
        op.create_table(
            'security_scans',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=False, index=True),
            sa.Column('policy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('security_policies.id'), nullable=True),
            sa.Column('policy_version', sa.String(50), nullable=True),
            sa.Column('previous_scan_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('security_scans.id'), nullable=True),
            sa.Column('status', postgresql.ENUM('pending', 'running', 'completed', 'failed', 'cancelled', name='scanstatus', create_type=False), nullable=False, server_default='pending'),
            sa.Column('total_tests', sa.Integer, nullable=False, server_default='0'),
            sa.Column('passed_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('failed_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('skipped_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('error_count', sa.Integer, nullable=False, server_default='0'),
            sa.Column('all_blocking_passed', sa.Boolean, nullable=True),
            sa.Column('result_signature', sa.String(512), nullable=True),
            sa.Column('signature_algorithm', sa.String(50), nullable=True, server_default='HMAC-SHA256'),
            sa.Column('triggered_by', sa.String(50), nullable=False, server_default='manual'),
            sa.Column('initiated_by', sa.String(255), nullable=True),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # Create security_scan_results table
    if not table_exists('security_scan_results'):
        op.create_table(
            'security_scan_results',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('scan_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('security_scans.id'), nullable=False, index=True),
            sa.Column('scan_type', postgresql.ENUM('prompt_injection', 'data_exfiltration', 'tool_abuse', 'egress_validation', 'credential_handling', 'input_validation', 'custom', name='scantype', create_type=False), nullable=False),
            sa.Column('test_case_id', sa.String(100), sa.ForeignKey('security_test_cases.id'), nullable=True),
            sa.Column('status', postgresql.ENUM('passed', 'failed', 'skipped', 'error', name='scanresultstatus', create_type=False), nullable=False),
            sa.Column('is_blocking', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('severity', postgresql.ENUM('info', 'low', 'medium', 'high', 'critical', name='severitylevel', create_type=False), nullable=False),
            sa.Column('input_payload', sa.Text, nullable=True),
            sa.Column('agent_response', sa.Text, nullable=True),
            sa.Column('expected_behavior', sa.Text, nullable=True),
            sa.Column('actual_behavior', sa.Text, nullable=True),
            sa.Column('remediation_guidance', sa.Text, nullable=True),
            sa.Column('reference_urls', postgresql.JSONB, nullable=True),
            sa.Column('execution_time_ms', sa.Integer, nullable=True),
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # Create indexes if they don't exist
    if not index_exists('ix_security_scans_agent_status'):
        op.create_index('ix_security_scans_agent_status', 'security_scans', ['agent_id', 'status'])
    if not index_exists('ix_security_test_cases_scan_type'):
        op.create_index('ix_security_test_cases_scan_type', 'security_test_cases', ['scan_type'])
    if not index_exists('ix_security_test_cases_builtin'):
        op.create_index('ix_security_test_cases_builtin', 'security_test_cases', ['is_builtin'])


def downgrade():
    # Drop indexes
    if index_exists('ix_security_test_cases_builtin'):
        op.drop_index('ix_security_test_cases_builtin', table_name='security_test_cases')
    if index_exists('ix_security_test_cases_scan_type'):
        op.drop_index('ix_security_test_cases_scan_type', table_name='security_test_cases')
    if index_exists('ix_security_scans_agent_status'):
        op.drop_index('ix_security_scans_agent_status', table_name='security_scans')

    # Drop tables in reverse order
    if table_exists('security_scan_results'):
        op.drop_table('security_scan_results')
    if table_exists('security_scans'):
        op.drop_table('security_scans')
    if table_exists('security_test_cases'):
        op.drop_table('security_test_cases')
    if table_exists('security_policies'):
        op.drop_table('security_policies')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS severitylevel")
    op.execute("DROP TYPE IF EXISTS scanresultstatus")
    op.execute("DROP TYPE IF EXISTS scanstatus")
    op.execute("DROP TYPE IF EXISTS scantype")
