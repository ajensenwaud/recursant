"""Add guardrail phase 2 tables: guardrail_events, adversarial_test_suites,
adversarial_test_runs, and CoT columns on mesh_audit_logs.

Revision ID: 20260227_120000
Revises: 20260226_120000
Create Date: 2026-02-27 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = '20260227_120000'
down_revision = '20260226_120000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # --- guardrail_events: high-volume evaluation events from sidecars ---
    if not _table_exists('guardrail_events'):
        op.create_table(
            'guardrail_events',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('guardrail_id', UUID(as_uuid=True), nullable=True),
            sa.Column('guardrail_name', sa.String(255), nullable=True),
            sa.Column('guardrail_type', sa.String(50), nullable=True),
            sa.Column('mechanism', sa.String(50), nullable=True),
            sa.Column('agent_name', sa.String(255), nullable=True),
            sa.Column('sidecar_id', sa.String(255), nullable=True),
            sa.Column('action', sa.String(20), nullable=False),
            sa.Column('reasoning', sa.Text(), nullable=True),
            sa.Column('latency_ms', sa.Float(), nullable=True),
            sa.Column('matched_pattern', sa.String(500), nullable=True),
            sa.Column('input_hash', sa.String(64), nullable=True),
            sa.Column('is_error', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index('ix_guardrail_events_tenant_ts',
                        'guardrail_events', ['tenant_id', 'timestamp'])
        op.create_index('ix_guardrail_events_guardrail_ts',
                        'guardrail_events', ['guardrail_id', 'timestamp'])
        op.create_index('ix_guardrail_events_agent_ts',
                        'guardrail_events', ['agent_name', 'timestamp'])
        op.create_index('ix_guardrail_events_action',
                        'guardrail_events', ['action'])

    # --- adversarial_test_suites ---
    if not _table_exists('adversarial_test_suites'):
        op.create_table(
            'adversarial_test_suites',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('attack_types', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('target_guardrail_ids', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('target_agent_names', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('schedule_enabled', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('schedule_interval_minutes', sa.Integer(), nullable=True),
            sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('evasion_rate_threshold', sa.Float(), nullable=False, server_default='0.1'),
            sa.Column('alert_on_threshold_breach', sa.Boolean(), nullable=False,
                      server_default='true'),
            sa.Column('generation_config', sa.JSON(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='active'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_adversarial_suites_tenant',
                        'adversarial_test_suites', ['tenant_id'])
        op.create_index('ix_adversarial_suites_schedule',
                        'adversarial_test_suites', ['schedule_enabled', 'next_run_at'])

    # --- adversarial_test_runs ---
    if not _table_exists('adversarial_test_runs'):
        op.create_table(
            'adversarial_test_runs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('suite_id', UUID(as_uuid=True),
                      sa.ForeignKey('adversarial_test_suites.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('triggered_by', sa.String(255), nullable=True),
            sa.Column('total_inputs', sa.Integer(), server_default='0'),
            sa.Column('blocked_count', sa.Integer(), server_default='0'),
            sa.Column('evaded_count', sa.Integer(), server_default='0'),
            sa.Column('error_count', sa.Integer(), server_default='0'),
            sa.Column('evasion_rate', sa.Float(), nullable=True),
            sa.Column('generated_inputs', sa.JSON(), nullable=True),
            sa.Column('results', sa.JSON(), nullable=True),
            sa.Column('threshold_breached', sa.Boolean(), nullable=False,
                      server_default='false'),
            sa.Column('alert_sent', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('result_signature', sa.String(128), nullable=True),
            sa.Column('signature_algorithm', sa.String(20), nullable=True),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_adversarial_runs_suite',
                        'adversarial_test_runs', ['suite_id'])
        op.create_index('ix_adversarial_runs_status',
                        'adversarial_test_runs', ['status'])
        op.create_index('ix_adversarial_runs_breached',
                        'adversarial_test_runs', ['threshold_breached'])

    # --- CoT columns on mesh_audit_logs ---
    if _table_exists('mesh_audit_logs'):
        if not _column_exists('mesh_audit_logs', 'cot_analysis'):
            op.add_column('mesh_audit_logs',
                          sa.Column('cot_analysis', sa.JSON(), nullable=True))
        if not _column_exists('mesh_audit_logs', 'cot_risk_level'):
            op.add_column('mesh_audit_logs',
                          sa.Column('cot_risk_level', sa.String(20), nullable=True))
        if not _column_exists('mesh_audit_logs', 'cot_flags'):
            op.add_column('mesh_audit_logs',
                          sa.Column('cot_flags', sa.JSON(), nullable=True))


def downgrade():
    # Drop CoT columns
    op.drop_column('mesh_audit_logs', 'cot_flags')
    op.drop_column('mesh_audit_logs', 'cot_risk_level')
    op.drop_column('mesh_audit_logs', 'cot_analysis')

    # Drop adversarial tables
    op.drop_table('adversarial_test_runs')
    op.drop_table('adversarial_test_suites')

    # Drop guardrail events
    op.drop_table('guardrail_events')
