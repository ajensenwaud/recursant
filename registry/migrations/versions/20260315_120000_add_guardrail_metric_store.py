"""Add guardrail metric store tables

Revision ID: 20260315_120000
Revises: d5e6f7g8h9i0
Create Date: 2026-03-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


revision = '20260315_120000'
down_revision = 'd5e6f7g8h9i0'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # --- guardrail_metrics ---
    if not _table_exists('guardrail_metrics'):
        op.create_table(
            'guardrail_metrics',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('display_name', sa.String(255), nullable=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('category', sa.String(50), nullable=False, server_default='custom'),
            sa.Column('mechanism', sa.String(50), nullable=False),
            sa.Column('config', sa.JSON, nullable=False, server_default='{}'),
            sa.Column('version', sa.String(50), nullable=True),
            sa.Column('is_builtin', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('scoring_rubric', sa.JSON, nullable=True),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            'uq_tenant_metric_name_active',
            'guardrail_metrics',
            ['tenant_id', 'name'],
            unique=True,
            postgresql_where=sa.text('deleted_at IS NULL'),
        )

    # --- guardrail_metric_scores ---
    if not _table_exists('guardrail_metric_scores'):
        op.create_table(
            'guardrail_metric_scores',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('metric_id', UUID(as_uuid=True),
                       sa.ForeignKey('guardrail_metrics.id'), nullable=False),
            sa.Column('agent_name', sa.String(255), nullable=True),
            sa.Column('score', sa.Float, nullable=True),
            sa.Column('details', sa.JSON, nullable=True),
            sa.Column('source', sa.String(50), nullable=False, server_default='evaluation'),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('timestamp', sa.DateTime(timezone=True),
                       server_default=sa.text('now()'), nullable=False),
        )
        op.create_index(
            'ix_metric_scores_metric_ts',
            'guardrail_metric_scores',
            ['metric_id', 'timestamp'],
        )
        op.create_index(
            'ix_metric_scores_agent',
            'guardrail_metric_scores',
            ['agent_name', 'timestamp'],
        )

    # --- Alter guardrails: add metric_id ---
    if _table_exists('guardrails') and not _column_exists('guardrails', 'metric_id'):
        op.add_column(
            'guardrails',
            sa.Column('metric_id', UUID(as_uuid=True),
                       sa.ForeignKey('guardrail_metrics.id'), nullable=True),
        )

    # --- Alter guardrail_events: add metric_id and triggered_spans ---
    if _table_exists('guardrail_events'):
        if not _column_exists('guardrail_events', 'metric_id'):
            op.add_column(
                'guardrail_events',
                sa.Column('metric_id', UUID(as_uuid=True), nullable=True),
            )
        if not _column_exists('guardrail_events', 'triggered_spans'):
            op.add_column(
                'guardrail_events',
                sa.Column('triggered_spans', sa.JSON, nullable=True),
            )


def downgrade():
    if _table_exists('guardrail_events'):
        if _column_exists('guardrail_events', 'triggered_spans'):
            op.drop_column('guardrail_events', 'triggered_spans')
        if _column_exists('guardrail_events', 'metric_id'):
            op.drop_column('guardrail_events', 'metric_id')

    if _table_exists('guardrails') and _column_exists('guardrails', 'metric_id'):
        op.drop_column('guardrails', 'metric_id')

    if _table_exists('guardrail_metric_scores'):
        op.drop_table('guardrail_metric_scores')

    if _table_exists('guardrail_metrics'):
        op.drop_table('guardrail_metrics')
