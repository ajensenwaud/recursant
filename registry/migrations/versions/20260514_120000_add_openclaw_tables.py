"""Add OpenClaw instance and enrollment-token tables, plus OPENCLAW endpoint type.

Revision ID: 20260514_120000
Revises: 20260502_180000
Create Date: 2026-05-14 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '20260514_120000'
down_revision = '20260502_180000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade():
    bind = op.get_bind()

    # Extend EndpointType enum with the new value. SQLAlchemy's
    # db.Enum(EndpointType) stores the Python enum *member name* in
    # Postgres, so the labels are uppercase (LANGCHAIN, CREWAI, ...). Find
    # the enum type by looking up any existing label, case-insensitively,
    # then add 'OPENCLAW' if missing. ALTER TYPE ... ADD VALUE must run
    # outside a transaction.
    enum_name_row = bind.execute(
        sa.text(
            "SELECT t.typname FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "WHERE lower(e.enumlabel) = 'langchain' "
            "LIMIT 1"
        )
    ).fetchone()
    if enum_name_row is not None:
        enum_name = enum_name_row[0]
        with op.get_context().autocommit_block():
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS 'OPENCLAW'")

    if not _table_exists('openclaw_instances'):
        op.create_table(
            'openclaw_instances',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('machine_id', sa.String(64), nullable=False),
            sa.Column('instance_fingerprint', JSONB, nullable=False, server_default='{}'),
            sa.Column('os', sa.String(64), nullable=True),
            sa.Column('openclaw_version', sa.String(64), nullable=True),
            sa.Column('plugin_version', sa.String(64), nullable=True),
            sa.Column(
                'status',
                sa.Enum(
                    'pending', 'active', 'suspended', 'revoked',
                    name='openclaw_instance_status',
                ),
                nullable=False,
                server_default='pending',
            ),
            sa.Column('enrolled_at', sa.DateTime(timezone=True),
                      server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint('tenant_id', 'machine_id',
                                name='uq_openclaw_instance_tenant_machine'),
        )
        op.create_index('ix_openclaw_instances_tenant_id', 'openclaw_instances', ['tenant_id'])
        op.create_index('ix_openclaw_instances_machine_id', 'openclaw_instances', ['machine_id'])

    if not _table_exists('openclaw_enrollment_tokens'):
        op.create_table(
            'openclaw_enrollment_tokens',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('token_hash', sa.String(128), nullable=False, unique=True),
            sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                'consumed_by_instance_id',
                UUID(as_uuid=True),
                sa.ForeignKey('openclaw_instances.id'),
                nullable=True,
            ),
        )
        op.create_index(
            'ix_openclaw_enrollment_tokens_tenant_id',
            'openclaw_enrollment_tokens',
            ['tenant_id'],
        )


def downgrade():
    if _table_exists('openclaw_enrollment_tokens'):
        op.drop_index('ix_openclaw_enrollment_tokens_tenant_id', table_name='openclaw_enrollment_tokens')
        op.drop_table('openclaw_enrollment_tokens')
    if _table_exists('openclaw_instances'):
        op.drop_index('ix_openclaw_instances_machine_id', table_name='openclaw_instances')
        op.drop_index('ix_openclaw_instances_tenant_id', table_name='openclaw_instances')
        op.drop_table('openclaw_instances')
    # Postgres does not support dropping individual enum values; leave the
    # 'openclaw' value in place on downgrade.
