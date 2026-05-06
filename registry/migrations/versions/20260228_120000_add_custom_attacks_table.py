"""Add custom_attacks table for user-defined adversarial attack entries.

Revision ID: 20260228_120000
Revises: 20260227_120000
Create Date: 2026-02-28 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = '20260228_120000'
down_revision = '20260227_120000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists('custom_attacks'):
        op.create_table(
            'custom_attacks',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('attack_type', sa.String(50), nullable=False),
            sa.Column('variant_name', sa.String(255), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
            sa.Column('source', sa.String(255), nullable=True),
            sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_custom_attacks_tenant', 'custom_attacks', ['tenant_id'])
        op.create_index('ix_custom_attacks_type', 'custom_attacks', ['tenant_id', 'attack_type'])
        op.create_unique_constraint(
            'uq_custom_attack_variant',
            'custom_attacks',
            ['tenant_id', 'attack_type', 'variant_name'],
        )


def downgrade():
    op.drop_table('custom_attacks')
