"""Add observability tables (MeshAnomaly, GuardrailEvent.is_false_positive).

Revision ID: obs001
Revises: None (auto-detect)
Create Date: 2026-02-27 15:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'obs001'
down_revision = '20260228_120000'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # MeshAnomaly table
    if 'mesh_anomalies' not in existing_tables:
        op.create_table(
            'mesh_anomalies',
            sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
            sa.Column('tenant_id', sa.String(100), nullable=False, server_default='default'),
            sa.Column('anomaly_type', sa.String(100), nullable=False),
            sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
            sa.Column('agent_name', sa.String(255), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('details', postgresql.JSON(), nullable=True),
            sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_acknowledged', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_mesh_anomalies_tenant_detected', 'mesh_anomalies', ['tenant_id', 'detected_at'])
        op.create_index('ix_mesh_anomalies_agent', 'mesh_anomalies', ['agent_name'])
        op.create_index('ix_mesh_anomalies_severity', 'mesh_anomalies', ['severity'])

    # Add is_false_positive to guardrail_events
    columns = [c['name'] for c in inspector.get_columns('guardrail_events')]
    if 'is_false_positive' not in columns:
        op.add_column('guardrail_events', sa.Column('is_false_positive', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('guardrail_events', 'is_false_positive')
    op.drop_index('ix_mesh_anomalies_severity', table_name='mesh_anomalies')
    op.drop_index('ix_mesh_anomalies_agent', table_name='mesh_anomalies')
    op.drop_index('ix_mesh_anomalies_tenant_detected', table_name='mesh_anomalies')
    op.drop_table('mesh_anomalies')
