"""Add webhook notification tables

Revision ID: 20260315_140000
Revises: 20260315_120000
Create Date: 2026-03-15 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


revision = '20260315_140000'
down_revision = '20260315_120000'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade():
    if not _table_exists('webhook_endpoints'):
        op.create_table(
            'webhook_endpoints',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('url', sa.String(2048), nullable=False),
            sa.Column('type', sa.String(50), nullable=False, server_default='generic'),
            sa.Column('secret', sa.String(500), nullable=True),
            sa.Column('headers', sa.JSON, nullable=True),
            sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
        )

    if not _table_exists('webhook_subscriptions'):
        op.create_table(
            'webhook_subscriptions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('webhook_id', UUID(as_uuid=True),
                       sa.ForeignKey('webhook_endpoints.id'), nullable=False),
            sa.Column('guardrail_id', UUID(as_uuid=True), nullable=True),
            sa.Column('metric_id', UUID(as_uuid=True), nullable=True),
            sa.Column('trigger_on_actions', sa.JSON, nullable=False,
                       server_default='["block","warn","redact"]'),
            sa.Column('cooldown_seconds', sa.Integer, nullable=False, server_default='60'),
            sa.Column('include_input_text', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('tenant_id', sa.String(255), nullable=False, server_default='default'),
            sa.Column('created_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
            sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists('webhook_delivery_log'):
        op.create_table(
            'webhook_delivery_log',
            sa.Column('id', UUID(as_uuid=True), primary_key=True,
                       server_default=sa.text('gen_random_uuid()')),
            sa.Column('subscription_id', UUID(as_uuid=True),
                       sa.ForeignKey('webhook_subscriptions.id'), nullable=False),
            sa.Column('event_id', UUID(as_uuid=True), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('response_status', sa.Integer, nullable=True),
            sa.Column('response_body', sa.Text, nullable=True),
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column('attempt', sa.Integer, nullable=False, server_default='1'),
            sa.Column('sent_at', sa.DateTime(timezone=True),
                       server_default=sa.text('now()')),
        )
        op.create_index(
            'ix_delivery_log_subscription',
            'webhook_delivery_log',
            ['subscription_id', 'sent_at'],
        )


def downgrade():
    if _table_exists('webhook_delivery_log'):
        op.drop_table('webhook_delivery_log')
    if _table_exists('webhook_subscriptions'):
        op.drop_table('webhook_subscriptions')
    if _table_exists('webhook_endpoints'):
        op.drop_table('webhook_endpoints')
