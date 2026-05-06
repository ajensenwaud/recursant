"""Add MCP server fields and revocation tracking to mesh_tools.

Revision ID: 20260220_140000
Revises: 20260220_120000
Create Date: 2026-02-20 14:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260220_140000'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mesh_tools', sa.Column('mcp_server_url', sa.String(512), nullable=True))
    op.add_column('mesh_tools', sa.Column('mcp_server_name', sa.String(255), nullable=True))
    op.add_column('mesh_tools', sa.Column('mcp_server_description', sa.Text(), nullable=True))
    op.add_column('mesh_tools', sa.Column('backend_services', sa.JSON(), nullable=True))
    op.add_column('mesh_tools', sa.Column('revoked_by', sa.String(255), nullable=True))
    op.add_column('mesh_tools', sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))

    # Rename status values: draft -> submitted, suspended -> revoked
    op.execute("UPDATE mesh_tools SET status='submitted' WHERE status='draft'")
    op.execute("UPDATE mesh_tools SET status='revoked' WHERE status='suspended'")


def downgrade():
    op.execute("UPDATE mesh_tools SET status='draft' WHERE status='submitted'")
    op.execute("UPDATE mesh_tools SET status='suspended' WHERE status='revoked'")

    op.drop_column('mesh_tools', 'revoked_at')
    op.drop_column('mesh_tools', 'revoked_by')
    op.drop_column('mesh_tools', 'backend_services')
    op.drop_column('mesh_tools', 'mcp_server_description')
    op.drop_column('mesh_tools', 'mcp_server_name')
    op.drop_column('mesh_tools', 'mcp_server_url')
