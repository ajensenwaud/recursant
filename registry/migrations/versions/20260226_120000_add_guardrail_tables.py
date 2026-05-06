"""Add guardrails, guardrail_assignments, guardrail_test_runs tables.

Revision ID: 20260226_120000
Revises: 20260222_120000
Create Date: 2026-02-26 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = '20260226_120000'
down_revision = '20260222_120000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists('guardrails'):
        op.create_table(
            'guardrails',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('type', sa.Enum('pre_processing', 'post_processing', 'structural',
                                      name='guardrailtype'), nullable=False),
            sa.Column('status', sa.Enum('draft', 'active', 'disabled',
                                        name='guardrailstatus'), nullable=False,
                      server_default='draft'),
            sa.Column('enforcement_mode', sa.Enum('block', 'warn', 'redact',
                                                   name='enforcementmode'), nullable=False,
                      server_default='block'),
            sa.Column('mechanism', sa.Enum('llm_judge', 'regex', 'vector_lookup', 'ml_classifier',
                                           name='guardrailmechanism'), nullable=False),
            sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('scope', sa.Enum('all_agents', 'specific_agents',
                                       name='guardrailscope'), nullable=False,
                      server_default='all_agents'),
            sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('version', sa.String(50), nullable=True),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('approved_by', sa.String(255), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            'uq_tenant_guardrail_name_active',
            'guardrails',
            ['tenant_id', 'name'],
            unique=True,
            postgresql_where=sa.text('deleted_at IS NULL'),
        )

    if not _table_exists('guardrail_assignments'):
        op.create_table(
            'guardrail_assignments',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('guardrail_id', UUID(as_uuid=True),
                      sa.ForeignKey('guardrails.id'), nullable=False),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('agent_name', sa.String(255), nullable=True),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint('guardrail_id', 'agent_id', name='uq_guardrail_agent'),
        )

    if not _table_exists('guardrail_test_runs'):
        op.create_table(
            'guardrail_test_runs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('guardrail_id', UUID(as_uuid=True),
                      sa.ForeignKey('guardrails.id'), nullable=False),
            sa.Column('agent_id', UUID(as_uuid=True),
                      sa.ForeignKey('agents.id'), nullable=True),
            sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed',
                                        name='testrunstatus'), nullable=False,
                      server_default='pending'),
            sa.Column('test_inputs', sa.JSON(), nullable=True),
            sa.Column('test_results', sa.JSON(), nullable=True),
            sa.Column('passed_count', sa.Integer(), server_default='0'),
            sa.Column('failed_count', sa.Integer(), server_default='0'),
            sa.Column('initiated_by', sa.String(255), nullable=True),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.drop_table('guardrail_test_runs')
    op.drop_table('guardrail_assignments')
    op.drop_index('uq_tenant_guardrail_name_active', table_name='guardrails')
    op.drop_table('guardrails')
    sa.Enum(name='testrunstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='guardrailscope').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='guardrailmechanism').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='enforcementmode').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='guardrailstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='guardrailtype').drop(op.get_bind(), checkfirst=True)
