"""Add stage-based guardrail configuration tables

Revision ID: 20260315_150000
Revises: 20260315_140000
Create Date: 2026-03-15 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


revision = '20260315_150000'
down_revision = '20260315_140000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade():
    if not _table_exists('guardrail_configs'):
        op.create_table(
            'guardrail_configs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('activated_by', sa.String(255), nullable=True),
            sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
        )
        op.create_index(
            'uq_tenant_config_name',
            'guardrail_configs',
            ['tenant_id', 'name'],
            unique=True,
        )

    if not _table_exists('guardrail_config_entries'):
        op.create_table(
            'guardrail_config_entries',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('config_id', UUID(as_uuid=True),
                       sa.ForeignKey('guardrail_configs.id'), nullable=False),
            sa.Column('guardrail_id', UUID(as_uuid=True),
                       sa.ForeignKey('guardrails.id'), nullable=False),
            sa.Column('enforcement_mode_override', sa.String(20), nullable=True),
            sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('priority_override', sa.Integer, nullable=True),
            sa.Column('config_override', sa.JSON, nullable=True),
        )
        op.create_unique_constraint(
            'uq_config_guardrail',
            'guardrail_config_entries',
            ['config_id', 'guardrail_id'],
        )


def downgrade():
    if _table_exists('guardrail_config_entries'):
        op.drop_table('guardrail_config_entries')
    if _table_exists('guardrail_configs'):
        op.drop_table('guardrail_configs')
