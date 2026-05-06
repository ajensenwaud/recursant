"""Update evaluation tables with new columns

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-24

Updates evaluation tables with:
- New columns for EvaluationSuite: version, is_baseline, is_extended, judge_provider, judge_model, tenant_id, deleted_at
- New columns for EvaluationTestCase: is_blocking, weight
- New columns for Evaluation: error_count, weighted_score, all_blocking_passed, judge_provider, result_signature, signature_algorithm, triggered_by, initiated_by, started_at
- New columns for EvaluationResult: passed, input_sent, criteria_scores, agent_latency_ms, judge_latency_ms, agent_tokens_used, judge_tokens_used, error_message
- Rename columns where needed
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def constraint_exists(constraint_name):
    """Check if a constraint exists."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
        {"name": constraint_name}
    )
    return result.fetchone() is not None


def upgrade():
    bind = op.get_bind()

    # ========================================================================
    # evaluation_suites updates
    # ========================================================================

    # Add version column
    if not column_exists('evaluation_suites', 'version'):
        op.add_column('evaluation_suites',
            sa.Column('version', sa.String(50), server_default='1.0.0'))

    # Add is_baseline column
    if not column_exists('evaluation_suites', 'is_baseline'):
        op.add_column('evaluation_suites',
            sa.Column('is_baseline', sa.Boolean, server_default='false'))

    # Add is_extended column
    if not column_exists('evaluation_suites', 'is_extended'):
        op.add_column('evaluation_suites',
            sa.Column('is_extended', sa.Boolean, server_default='false'))

    # Add judge_provider column (enum)
    if not column_exists('evaluation_suites', 'judge_provider'):
        op.add_column('evaluation_suites',
            sa.Column('judge_provider', postgresql.ENUM(
                'openai', 'anthropic', 'google', 'custom',
                name='llmprovider', create_type=False
            ), nullable=True))

    # Add judge_model column
    if not column_exists('evaluation_suites', 'judge_model'):
        op.add_column('evaluation_suites',
            sa.Column('judge_model', sa.String(100), nullable=True))

    # Add tenant_id column
    if not column_exists('evaluation_suites', 'tenant_id'):
        op.add_column('evaluation_suites',
            sa.Column('tenant_id', sa.String(255), nullable=True))

    # Add deleted_at column
    if not column_exists('evaluation_suites', 'deleted_at'):
        op.add_column('evaluation_suites',
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    # Add unique constraint on (tenant_id, name)
    if not constraint_exists('uq_evaluation_suite_tenant_name'):
        op.create_unique_constraint(
            'uq_evaluation_suite_tenant_name',
            'evaluation_suites',
            ['tenant_id', 'name']
        )

    # ========================================================================
    # evaluation_test_cases updates
    # ========================================================================

    # Add is_blocking column
    if not column_exists('evaluation_test_cases', 'is_blocking'):
        op.add_column('evaluation_test_cases',
            sa.Column('is_blocking', sa.Boolean, server_default='false'))

    # Add weight column
    if not column_exists('evaluation_test_cases', 'weight'):
        op.add_column('evaluation_test_cases',
            sa.Column('weight', sa.Numeric(3, 2), server_default='1.00'))

    # Add unique constraint on (suite_id, name)
    if not constraint_exists('uq_evaluation_test_case_suite_name'):
        op.create_unique_constraint(
            'uq_evaluation_test_case_suite_name',
            'evaluation_test_cases',
            ['suite_id', 'name']
        )

    # ========================================================================
    # evaluations updates
    # ========================================================================

    # Add error_count column
    if not column_exists('evaluations', 'error_count'):
        op.add_column('evaluations',
            sa.Column('error_count', sa.Integer, server_default='0'))

    # Add weighted_score column (may already have average_score, we'll add weighted_score separately)
    if not column_exists('evaluations', 'weighted_score'):
        op.add_column('evaluations',
            sa.Column('weighted_score', sa.Numeric(5, 4), server_default='0.0000'))

    # Add all_blocking_passed column
    if not column_exists('evaluations', 'all_blocking_passed'):
        op.add_column('evaluations',
            sa.Column('all_blocking_passed', sa.Boolean, server_default='true'))

    # Add judge_provider column
    if not column_exists('evaluations', 'judge_provider'):
        op.add_column('evaluations',
            sa.Column('judge_provider', sa.String(50), nullable=True))

    # Rename judge_model_used to judge_model if needed
    if column_exists('evaluations', 'judge_model_used') and not column_exists('evaluations', 'judge_model'):
        op.alter_column('evaluations', 'judge_model_used', new_column_name='judge_model')
    elif not column_exists('evaluations', 'judge_model'):
        op.add_column('evaluations',
            sa.Column('judge_model', sa.String(100), nullable=True))

    # Add result_signature column
    if not column_exists('evaluations', 'result_signature'):
        op.add_column('evaluations',
            sa.Column('result_signature', sa.String(512), nullable=True))

    # Add signature_algorithm column
    if not column_exists('evaluations', 'signature_algorithm'):
        op.add_column('evaluations',
            sa.Column('signature_algorithm', sa.String(50), nullable=True))

    # Add triggered_by column
    if not column_exists('evaluations', 'triggered_by'):
        op.add_column('evaluations',
            sa.Column('triggered_by', sa.String(50), server_default='manual'))

    # Add initiated_by column
    if not column_exists('evaluations', 'initiated_by'):
        op.add_column('evaluations',
            sa.Column('initiated_by', sa.String(255), nullable=True))

    # Add started_at column
    if not column_exists('evaluations', 'started_at'):
        op.add_column('evaluations',
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))

    # ========================================================================
    # evaluation_results updates
    # ========================================================================

    # Add passed column
    if not column_exists('evaluation_results', 'passed'):
        op.add_column('evaluation_results',
            sa.Column('passed', sa.Boolean, nullable=True))

    # Rename input_prompt to input_sent if needed
    if column_exists('evaluation_results', 'input_prompt') and not column_exists('evaluation_results', 'input_sent'):
        op.alter_column('evaluation_results', 'input_prompt', new_column_name='input_sent')
    elif not column_exists('evaluation_results', 'input_sent'):
        op.add_column('evaluation_results',
            sa.Column('input_sent', sa.Text, nullable=True))

    # Rename reasoning to judge_reasoning if needed
    if column_exists('evaluation_results', 'reasoning') and not column_exists('evaluation_results', 'judge_reasoning'):
        op.alter_column('evaluation_results', 'reasoning', new_column_name='judge_reasoning')
    elif not column_exists('evaluation_results', 'judge_reasoning'):
        op.add_column('evaluation_results',
            sa.Column('judge_reasoning', sa.Text, nullable=True))

    # Add criteria_scores column
    if not column_exists('evaluation_results', 'criteria_scores'):
        op.add_column('evaluation_results',
            sa.Column('criteria_scores', postgresql.JSONB, nullable=True))

    # Add agent_latency_ms column
    if not column_exists('evaluation_results', 'agent_latency_ms'):
        op.add_column('evaluation_results',
            sa.Column('agent_latency_ms', sa.Integer, nullable=True))

    # Add judge_latency_ms column
    if not column_exists('evaluation_results', 'judge_latency_ms'):
        op.add_column('evaluation_results',
            sa.Column('judge_latency_ms', sa.Integer, nullable=True))

    # Rename tokens_used to judge_tokens_used if needed
    if column_exists('evaluation_results', 'tokens_used') and not column_exists('evaluation_results', 'judge_tokens_used'):
        op.alter_column('evaluation_results', 'tokens_used', new_column_name='judge_tokens_used')
    elif not column_exists('evaluation_results', 'judge_tokens_used'):
        op.add_column('evaluation_results',
            sa.Column('judge_tokens_used', sa.Integer, nullable=True))

    # Add agent_tokens_used column
    if not column_exists('evaluation_results', 'agent_tokens_used'):
        op.add_column('evaluation_results',
            sa.Column('agent_tokens_used', sa.Integer, nullable=True))

    # Add error_message column
    if not column_exists('evaluation_results', 'error_message'):
        op.add_column('evaluation_results',
            sa.Column('error_message', sa.Text, nullable=True))

    # Change score column type from Float to Numeric(5,4) if needed
    # This requires dropping and recreating or using ALTER with USING clause
    # For simplicity, we'll keep it as-is since Float is compatible


def downgrade():
    # ========================================================================
    # evaluation_results - revert
    # ========================================================================
    if column_exists('evaluation_results', 'error_message'):
        op.drop_column('evaluation_results', 'error_message')
    if column_exists('evaluation_results', 'agent_tokens_used'):
        op.drop_column('evaluation_results', 'agent_tokens_used')
    if column_exists('evaluation_results', 'judge_latency_ms'):
        op.drop_column('evaluation_results', 'judge_latency_ms')
    if column_exists('evaluation_results', 'agent_latency_ms'):
        op.drop_column('evaluation_results', 'agent_latency_ms')
    if column_exists('evaluation_results', 'criteria_scores'):
        op.drop_column('evaluation_results', 'criteria_scores')
    if column_exists('evaluation_results', 'passed'):
        op.drop_column('evaluation_results', 'passed')

    # Rename back judge_reasoning to reasoning
    if column_exists('evaluation_results', 'judge_reasoning'):
        op.alter_column('evaluation_results', 'judge_reasoning', new_column_name='reasoning')

    # Rename back input_sent to input_prompt
    if column_exists('evaluation_results', 'input_sent'):
        op.alter_column('evaluation_results', 'input_sent', new_column_name='input_prompt')

    # Rename back judge_tokens_used to tokens_used
    if column_exists('evaluation_results', 'judge_tokens_used'):
        op.alter_column('evaluation_results', 'judge_tokens_used', new_column_name='tokens_used')

    # ========================================================================
    # evaluations - revert
    # ========================================================================
    if column_exists('evaluations', 'started_at'):
        op.drop_column('evaluations', 'started_at')
    if column_exists('evaluations', 'initiated_by'):
        op.drop_column('evaluations', 'initiated_by')
    if column_exists('evaluations', 'triggered_by'):
        op.drop_column('evaluations', 'triggered_by')
    if column_exists('evaluations', 'signature_algorithm'):
        op.drop_column('evaluations', 'signature_algorithm')
    if column_exists('evaluations', 'result_signature'):
        op.drop_column('evaluations', 'result_signature')
    if column_exists('evaluations', 'judge_provider'):
        op.drop_column('evaluations', 'judge_provider')
    if column_exists('evaluations', 'all_blocking_passed'):
        op.drop_column('evaluations', 'all_blocking_passed')
    if column_exists('evaluations', 'weighted_score'):
        op.drop_column('evaluations', 'weighted_score')
    if column_exists('evaluations', 'error_count'):
        op.drop_column('evaluations', 'error_count')

    # Rename back judge_model to judge_model_used
    if column_exists('evaluations', 'judge_model'):
        op.alter_column('evaluations', 'judge_model', new_column_name='judge_model_used')

    # ========================================================================
    # evaluation_test_cases - revert
    # ========================================================================
    if constraint_exists('uq_evaluation_test_case_suite_name'):
        op.drop_constraint('uq_evaluation_test_case_suite_name', 'evaluation_test_cases')
    if column_exists('evaluation_test_cases', 'weight'):
        op.drop_column('evaluation_test_cases', 'weight')
    if column_exists('evaluation_test_cases', 'is_blocking'):
        op.drop_column('evaluation_test_cases', 'is_blocking')

    # ========================================================================
    # evaluation_suites - revert
    # ========================================================================
    if constraint_exists('uq_evaluation_suite_tenant_name'):
        op.drop_constraint('uq_evaluation_suite_tenant_name', 'evaluation_suites')
    if column_exists('evaluation_suites', 'deleted_at'):
        op.drop_column('evaluation_suites', 'deleted_at')
    if column_exists('evaluation_suites', 'tenant_id'):
        op.drop_column('evaluation_suites', 'tenant_id')
    if column_exists('evaluation_suites', 'judge_model'):
        op.drop_column('evaluation_suites', 'judge_model')
    if column_exists('evaluation_suites', 'judge_provider'):
        op.drop_column('evaluation_suites', 'judge_provider')
    if column_exists('evaluation_suites', 'is_extended'):
        op.drop_column('evaluation_suites', 'is_extended')
    if column_exists('evaluation_suites', 'is_baseline'):
        op.drop_column('evaluation_suites', 'is_baseline')
    if column_exists('evaluation_suites', 'version'):
        op.drop_column('evaluation_suites', 'version')
