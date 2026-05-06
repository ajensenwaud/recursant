"""Fix agent unique constraint for soft deletes

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-09

Replace the absolute unique constraint on (tenant_id, name) with a partial
unique index that only applies to non-deleted agents. This allows soft-deleted
agents to share a name with new agents in the same tenant.
"""
from alembic import op

revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE agents DROP CONSTRAINT IF EXISTS uq_tenant_agent_name")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_agent_name_active "
        "ON agents (tenant_id, name) "
        "WHERE deleted_at IS NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_tenant_agent_name_active")
    op.create_unique_constraint('uq_tenant_agent_name', 'agents', ['tenant_id', 'name'])
