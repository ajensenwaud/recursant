"""Add soft delete to evaluation_test_cases

Revision ID: c5d6e7f8g9h0
Revises: b4c5d6e7f8g9
Create Date: 2026-02-13 22:00:00.000000

Adds deleted_at column and replaces the hard unique constraint with a
partial unique index that only applies to non-deleted rows.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c5d6e7f8g9h0'
down_revision = 'b4c5d6e7f8g9'
branch_labels = None
depends_on = None


def upgrade():
    # Add deleted_at column
    op.add_column('evaluation_test_cases',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    # Replace hard unique constraint with partial index (active rows only)
    op.drop_constraint('uq_evaluation_test_case_suite_name', 'evaluation_test_cases', type_='unique')
    op.execute(
        "CREATE UNIQUE INDEX uq_evaluation_test_case_suite_name_active "
        "ON evaluation_test_cases (suite_id, name) "
        "WHERE deleted_at IS NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_evaluation_test_case_suite_name_active")
    op.create_unique_constraint(
        'uq_evaluation_test_case_suite_name',
        'evaluation_test_cases',
        ['suite_id', 'name']
    )
    op.drop_column('evaluation_test_cases', 'deleted_at')
