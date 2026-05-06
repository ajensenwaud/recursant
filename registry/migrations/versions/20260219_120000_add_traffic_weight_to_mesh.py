"""Add traffic_weight to mesh_registrations.

Revision ID: f1a2b3c4d5e6
Revises: None
Create Date: 2026-02-19 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'd6e7f8g9h0i1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'mesh_registrations',
        sa.Column('traffic_weight', sa.Integer(), nullable=False, server_default='100'),
    )


def downgrade():
    op.drop_column('mesh_registrations', 'traffic_weight')
