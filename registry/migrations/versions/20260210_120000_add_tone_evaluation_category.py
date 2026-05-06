"""Add tone to evaluationcategory enum

Revision ID: a3b4c5d6e7f8
Revises: 95a7bb26be69
Create Date: 2026-02-10 12:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = '95a7bb26be69'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE evaluationcategory ADD VALUE IF NOT EXISTS 'TONE'")


def downgrade():
    # PostgreSQL doesn't support removing enum values; no-op
    pass
