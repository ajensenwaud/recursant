"""Add network discovery tables

Revision ID: d5e6f7g8h9i0
Revises: 20260310_120000
Create Date: 2026-03-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'd5e6f7g8h9i0'
down_revision = '20260310_120000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists('discovery_scans'):
        return

    # discovery_scans
    op.create_table('discovery_scans',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('scan_type', sa.String(length=30), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # indexes
    op.create_index('ix_discovery_scans_tenant', 'discovery_scans', ['tenant_id'])
    op.create_index('ix_discovery_scans_status', 'discovery_scans', ['status'])
    op.create_index('ix_discovery_scans_created_at', 'discovery_scans', ['created_at'])

    # discovered_hosts
    op.create_table('discovered_hosts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('scan_id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('protocol', sa.String(length=10), nullable=False, server_default='http'),
        sa.Column('service_type', sa.String(length=30), nullable=False, server_default='unknown'),
        sa.Column('tls_info', sa.JSON(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='online'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['scan_id'], ['discovery_scans.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovered_hosts_tenant', 'discovered_hosts', ['tenant_id'])
    op.create_index('ix_discovered_hosts_scan', 'discovered_hosts', ['scan_id'])
    op.create_index('ix_discovered_hosts_address_port', 'discovered_hosts', ['tenant_id', 'address', 'port'])
    op.create_index('ix_discovered_hosts_status', 'discovered_hosts', ['status'])

    # discovered_agents
    op.create_table('discovered_agents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('host_id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('agent_card', sa.JSON(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('framework_type', sa.String(length=50), nullable=True),
        sa.Column('governance_status', sa.String(length=30), nullable=False, server_default='unknown'),
        sa.Column('registry_agent_id', sa.UUID(), nullable=True),
        sa.Column('mesh_registration_id', sa.UUID(), nullable=True),
        sa.Column('capabilities', sa.JSON(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('disappeared_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['host_id'], ['discovered_hosts.id']),
        sa.ForeignKeyConstraint(['registry_agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['mesh_registration_id'], ['mesh_registrations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovered_agents_tenant', 'discovered_agents', ['tenant_id'])
    op.create_index('ix_discovered_agents_governance', 'discovered_agents', ['governance_status'])
    op.create_index('ix_discovered_agents_registry', 'discovered_agents', ['registry_agent_id'])
    op.create_index('ix_discovered_agents_host', 'discovered_agents', ['host_id'])

    # discovered_tools
    op.create_table('discovered_tools',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('host_id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('tool_name', sa.String(length=255), nullable=False),
        sa.Column('tool_description', sa.Text(), nullable=True),
        sa.Column('input_schema', sa.JSON(), nullable=True),
        sa.Column('mcp_server_url', sa.String(length=2048), nullable=True),
        sa.Column('governance_status', sa.String(length=30), nullable=False, server_default='ungoverned'),
        sa.Column('mesh_tool_id', sa.UUID(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['host_id'], ['discovered_hosts.id']),
        sa.ForeignKeyConstraint(['mesh_tool_id'], ['mesh_tools.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovered_tools_tenant', 'discovered_tools', ['tenant_id'])
    op.create_index('ix_discovered_tools_governance', 'discovered_tools', ['governance_status'])
    op.create_index('ix_discovered_tools_host', 'discovered_tools', ['host_id'])

    # discovery_scan_schedules
    op.create_table('discovery_scan_schedules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('scan_type', sa.String(length=30), nullable=False, server_default='network'),
        sa.Column('scan_config', sa.JSON(), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discovery_schedules_tenant', 'discovery_scan_schedules', ['tenant_id'])
    op.create_index('ix_discovery_schedules_enabled', 'discovery_scan_schedules', ['enabled'])


def downgrade():
    op.drop_table('discovery_scan_schedules')
    op.drop_table('discovered_tools')
    op.drop_table('discovered_agents')
    op.drop_table('discovered_hosts')
    op.drop_table('discovery_scans')
