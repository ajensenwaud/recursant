"""Webhook models for outbound notifications on guardrail events."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app import db


class WebhookEndpoint(db.Model):
    """A configured webhook destination."""
    __tablename__ = 'webhook_endpoints'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    type = db.Column(db.String(50), nullable=False, default='generic')  # slack/pagerduty/teams/generic
    secret = db.Column(db.String(500), nullable=True)
    headers = db.Column(JSON, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_by = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    subscriptions = db.relationship(
        'WebhookSubscription', backref='endpoint', lazy='dynamic', cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<WebhookEndpoint {self.name} ({self.type})>'


class WebhookSubscription(db.Model):
    """Links a webhook endpoint to guardrail/metric triggers."""
    __tablename__ = 'webhook_subscriptions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = db.Column(UUID(as_uuid=True), db.ForeignKey('webhook_endpoints.id'), nullable=False)
    guardrail_id = db.Column(UUID(as_uuid=True), nullable=True)
    metric_id = db.Column(UUID(as_uuid=True), nullable=True)
    trigger_on_actions = db.Column(JSON, nullable=False, default=lambda: ['block', 'warn', 'redact'])
    cooldown_seconds = db.Column(db.Integer, nullable=False, default=60)
    include_input_text = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Track last fired for cooldown
    last_fired_at = db.Column(db.DateTime(timezone=True), nullable=True)

    delivery_logs = db.relationship(
        'WebhookDeliveryLog', backref='subscription', lazy='dynamic', cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<WebhookSubscription webhook={self.webhook_id} guardrail={self.guardrail_id}>'


class WebhookDeliveryLog(db.Model):
    """Log of webhook delivery attempts."""
    __tablename__ = 'webhook_delivery_log'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = db.Column(UUID(as_uuid=True), db.ForeignKey('webhook_subscriptions.id'), nullable=False)
    event_id = db.Column(UUID(as_uuid=True), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending/success/failed
    response_status = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    attempt = db.Column(db.Integer, nullable=False, default=1)
    sent_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_delivery_log_subscription', 'subscription_id', 'sent_at'),
    )

    def __repr__(self):
        return f'<WebhookDeliveryLog {self.id} status={self.status}>'
