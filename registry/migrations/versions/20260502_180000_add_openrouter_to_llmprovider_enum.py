"""Add OPENROUTER to llmprovider enum

Revision ID: 20260502_180000
Revises: 20260315_150000
Create Date: 2026-05-02

The Python LLMProvider enum gained an OPENROUTER member when OpenRouter
was added as a first-class provider, but the corresponding PostgreSQL
enum type (`llmprovider`) was not updated. New evaluation suites that
try to use provider=OPENROUTER hit `invalid input value for enum`.
"""
from alembic import op


revision = '20260502_180000'
down_revision = '20260315_150000'
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in Postgres
    # before 12; use IF NOT EXISTS so this is safe to re-run.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE llmprovider ADD VALUE IF NOT EXISTS 'OPENROUTER'")


def downgrade():
    # Removing an enum value in Postgres requires recreating the type.
    # Skip — leaving an unused enum value is harmless.
    pass
