"""Add mesh_reasoning_spans table for per-agent reasoning traceability.

Revision ID: 20260228_180000
Revises: obs001
Create Date: 2026-02-28 18:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = '20260228_180000'
down_revision = 'obs001'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists('mesh_reasoning_spans'):
        return

    op.create_table(
        'mesh_reasoning_spans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default'),
        sa.Column('task_id', sa.String(255), nullable=False),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('agent_name', sa.String(255), nullable=False),
        sa.Column('span_type', sa.String(50), nullable=False),
        sa.Column('span_name', sa.String(255), nullable=False),
        sa.Column('input_data', sa.JSON, nullable=True),
        sa.Column('output_data', sa.JSON, nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Float, nullable=True),
        sa.Column('parent_span_id', UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_index(
        'ix_mesh_reasoning_spans_tenant_task',
        'mesh_reasoning_spans',
        ['tenant_id', 'task_id'],
    )
    op.create_index(
        'ix_mesh_reasoning_spans_agent',
        'mesh_reasoning_spans',
        ['agent_name'],
    )
    op.create_index(
        'ix_mesh_reasoning_spans_type',
        'mesh_reasoning_spans',
        ['span_type'],
    )


def downgrade():
    op.drop_index('ix_mesh_reasoning_spans_type')
    op.drop_index('ix_mesh_reasoning_spans_agent')
    op.drop_index('ix_mesh_reasoning_spans_tenant_task')
    op.drop_table('mesh_reasoning_spans')
