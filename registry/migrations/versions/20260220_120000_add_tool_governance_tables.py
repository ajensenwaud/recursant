"""Add tool governance tables (mesh_tools, mesh_tool_assignments, mesh_egress_rules).

Supports registry-controlled tool authorization, audit, and egress control.
Additive only — no existing tables modified.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f7
Create Date: 2026-02-20 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    # mesh_tools — registered tools that agents call through the sidecar
    op.create_table(
        'mesh_tools',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('tool_type', sa.String(20), nullable=False, server_default='http'),
        sa.Column('endpoint_url', sa.String(2048), nullable=False),
        sa.Column('http_method', sa.String(10), nullable=False, server_default='POST'),
        sa.Column('parameters_schema', sa.JSON, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_mesh_tools_tenant_name'),
    )
    op.create_index('ix_mesh_tools_tenant', 'mesh_tools', ['tenant_id'])
    op.create_index('ix_mesh_tools_status', 'mesh_tools', ['status'])

    # mesh_tool_assignments — maps tools to agents
    op.create_table(
        'mesh_tool_assignments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default'),
        sa.Column('tool_id', UUID(as_uuid=True), sa.ForeignKey('mesh_tools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('tenant_id', 'tool_id', 'agent_name', name='uq_mesh_tool_assignments_tenant_tool_agent'),
    )
    op.create_index('ix_mesh_tool_assignments_tenant', 'mesh_tool_assignments', ['tenant_id'])
    op.create_index('ix_mesh_tool_assignments_agent', 'mesh_tool_assignments', ['agent_name'])

    # mesh_egress_rules — URL allowlist/denylist for non-tool HTTP calls
    op.create_table(
        'mesh_egress_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default'),
        sa.Column('agent_name', sa.String(255), nullable=False, server_default='*'),
        sa.Column('url_pattern', sa.String(2048), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('priority', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_mesh_egress_rules_tenant', 'mesh_egress_rules', ['tenant_id'])
    op.create_index('ix_mesh_egress_rules_priority', 'mesh_egress_rules', ['tenant_id', 'priority'])


def downgrade():
    op.drop_table('mesh_egress_rules')
    op.drop_table('mesh_tool_assignments')
    op.drop_table('mesh_tools')
