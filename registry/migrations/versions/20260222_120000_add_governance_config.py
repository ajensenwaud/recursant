"""Add governance_configs table for auto-approval settings.

Revision ID: 20260222_120000
Revises: 20260220_140000
Create Date: 2026-02-22 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = '20260222_120000'
down_revision = '20260220_140000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists('governance_configs'):
        return

    op.create_table(
        'governance_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.String(255), nullable=False, unique=True),
        sa.Column('auto_approve_enabled', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('auto_approve_risk_tiers', sa.JSON(), nullable=False,
                  server_default=sa.text("'[]'::json")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Seed default row
    op.execute(
        "INSERT INTO governance_configs (tenant_id, auto_approve_enabled, auto_approve_risk_tiers) "
        "VALUES ('default', false, '[]'::json)"
    )


def downgrade():
    op.drop_table('governance_configs')
