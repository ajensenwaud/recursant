"""Add cluster_id column to mesh tables for multi-cluster HA.

Adds cluster_id (with server_default 'default') to mesh_registrations,
mesh_policies, mesh_audit_logs, and mesh_compliance_rules. Also adds
updated_at to mesh_registrations for LWW conflict resolution.

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-02-19 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # mesh_registrations: cluster_id + updated_at
    op.add_column(
        'mesh_registrations',
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
    )
    op.add_column(
        'mesh_registrations',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index('ix_mesh_registrations_cluster', 'mesh_registrations', ['cluster_id'])

    # mesh_policies: cluster_id
    op.add_column(
        'mesh_policies',
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
    )

    # mesh_audit_logs: cluster_id
    op.add_column(
        'mesh_audit_logs',
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
    )

    # mesh_compliance_rules: cluster_id
    op.add_column(
        'mesh_compliance_rules',
        sa.Column('cluster_id', sa.String(50), nullable=False, server_default='default'),
    )


def downgrade():
    op.drop_column('mesh_compliance_rules', 'cluster_id')
    op.drop_column('mesh_audit_logs', 'cluster_id')
    op.drop_column('mesh_policies', 'cluster_id')
    op.drop_index('ix_mesh_registrations_cluster', table_name='mesh_registrations')
    op.drop_column('mesh_registrations', 'updated_at')
    op.drop_column('mesh_registrations', 'cluster_id')
