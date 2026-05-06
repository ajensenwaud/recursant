"""Add Phase 3 production hardening tables and columns

Revision ID: d6e7f8g9h0i1
Revises: c5d6e7f8g9h0
Create Date: 2026-02-16 12:00:00.000000

Adds:
- Hash-chain columns to mesh_audit_logs (record_hash, previous_record_hash, sequence_number)
- data_subject_consents table (GDPR consent tracking)
- issued_certificates table (certificate auto-rotation audit)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e7f8g9h0i1'
down_revision = 'c5d6e7f8g9h0'
branch_labels = None
depends_on = None


def upgrade():
    # -- Hash-chain columns on mesh_audit_logs --
    with op.batch_alter_table('mesh_audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('record_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('previous_record_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('sequence_number', sa.Integer(), nullable=True))
        batch_op.create_index('ix_mesh_audit_logs_chain', ['sidecar_id', 'sequence_number'], unique=False)

    # -- GDPR consent tracking --
    op.create_table('data_subject_consents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('data_subject_id', sa.String(length=255), nullable=False),
        sa.Column('consent_type', sa.String(length=50), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('legal_basis', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('data_subject_consents', schema=None) as batch_op:
        batch_op.create_index('ix_consent_tenant_subject', ['tenant_id', 'data_subject_id'], unique=False)
        batch_op.create_index('ix_consent_type', ['tenant_id', 'data_subject_id', 'consent_type'], unique=False)

    # -- Certificate tracking --
    op.create_table('issued_certificates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.String(length=255), nullable=False),
        sa.Column('serial_number', sa.String(length=100), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('serial_number'),
    )
    with op.batch_alter_table('issued_certificates', schema=None) as batch_op:
        batch_op.create_index('ix_issued_certs_agent', ['agent_id'], unique=False)
        batch_op.create_index('ix_issued_certs_status', ['status'], unique=False)


def downgrade():
    # -- Drop certificate tracking --
    with op.batch_alter_table('issued_certificates', schema=None) as batch_op:
        batch_op.drop_index('ix_issued_certs_status')
        batch_op.drop_index('ix_issued_certs_agent')
    op.drop_table('issued_certificates')

    # -- Drop consent tracking --
    with op.batch_alter_table('data_subject_consents', schema=None) as batch_op:
        batch_op.drop_index('ix_consent_type')
        batch_op.drop_index('ix_consent_tenant_subject')
    op.drop_table('data_subject_consents')

    # -- Drop hash-chain columns --
    with op.batch_alter_table('mesh_audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_mesh_audit_logs_chain')
        batch_op.drop_column('sequence_number')
        batch_op.drop_column('previous_record_hash')
        batch_op.drop_column('record_hash')
