"""Add mesh control plane tables

Revision ID: b4c5d6e7f8g9
Revises: a3b4c5d6e7f8
Create Date: 2026-02-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8g9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    # mesh_registrations
    op.create_table('mesh_registrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('sidecar_url', sa.String(length=2048), nullable=False),
        sa.Column('agent_card', sa.JSON(), nullable=False),
        sa.Column('sovereignty_zone', sa.String(length=50), nullable=True),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id'),
    )
    with op.batch_alter_table('mesh_registrations', schema=None) as batch_op:
        batch_op.create_index('ix_mesh_registrations_tenant', ['tenant_id'], unique=False)
        batch_op.create_index('ix_mesh_registrations_status', ['status'], unique=False)

    # mesh_policies
    op.create_table('mesh_policies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('source_agent_name', sa.String(length=255), nullable=False),
        sa.Column('dest_agent_name', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mesh_policies', schema=None) as batch_op:
        batch_op.create_index('ix_mesh_policies_tenant', ['tenant_id'], unique=False)
        batch_op.create_index('ix_mesh_policies_priority', ['tenant_id', 'priority'], unique=False)

    # mesh_audit_logs
    op.create_table('mesh_audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_agent_id', sa.String(length=255), nullable=True),
        sa.Column('source_agent_name', sa.String(length=255), nullable=True),
        sa.Column('dest_agent_id', sa.String(length=255), nullable=True),
        sa.Column('dest_agent_name', sa.String(length=255), nullable=True),
        sa.Column('task_id', sa.String(length=255), nullable=True),
        sa.Column('a2a_method', sa.String(length=100), nullable=False),
        sa.Column('message_hash', sa.String(length=64), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('sidecar_id', sa.String(length=255), nullable=True),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mesh_audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_mesh_audit_logs_tenant_timestamp', ['tenant_id', 'timestamp'], unique=False)
        batch_op.create_index('ix_mesh_audit_logs_task_id', ['task_id'], unique=False)
        batch_op.create_index('ix_mesh_audit_logs_source', ['source_agent_name'], unique=False)


def downgrade():
    with op.batch_alter_table('mesh_audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_mesh_audit_logs_source')
        batch_op.drop_index('ix_mesh_audit_logs_task_id')
        batch_op.drop_index('ix_mesh_audit_logs_tenant_timestamp')
    op.drop_table('mesh_audit_logs')

    with op.batch_alter_table('mesh_policies', schema=None) as batch_op:
        batch_op.drop_index('ix_mesh_policies_priority')
        batch_op.drop_index('ix_mesh_policies_tenant')
    op.drop_table('mesh_policies')

    with op.batch_alter_table('mesh_registrations', schema=None) as batch_op:
        batch_op.drop_index('ix_mesh_registrations_status')
        batch_op.drop_index('ix_mesh_registrations_tenant')
    op.drop_table('mesh_registrations')
