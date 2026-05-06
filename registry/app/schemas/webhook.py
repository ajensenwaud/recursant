"""Marshmallow schemas for webhook endpoints and subscriptions."""

from marshmallow import Schema, fields, validate


class WebhookEndpointCreateSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    url = fields.String(required=True, validate=validate.Length(min=1, max=2048))
    type = fields.String(
        load_default='generic',
        validate=validate.OneOf(['slack', 'pagerduty', 'teams', 'generic']),
    )
    secret = fields.String(allow_none=True, validate=validate.Length(max=500))
    headers = fields.Dict(allow_none=True)
    enabled = fields.Boolean(load_default=True)


class WebhookEndpointUpdateSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=255))
    url = fields.String(validate=validate.Length(min=1, max=2048))
    type = fields.String(validate=validate.OneOf(['slack', 'pagerduty', 'teams', 'generic']))
    secret = fields.String(allow_none=True, validate=validate.Length(max=500))
    headers = fields.Dict(allow_none=True)
    enabled = fields.Boolean()


class WebhookEndpointSchema(Schema):
    id = fields.UUID(dump_only=True)
    name = fields.String()
    url = fields.String()
    type = fields.String()
    secret = fields.String(load_default=None)
    headers = fields.Dict()
    enabled = fields.Boolean()
    tenant_id = fields.String()
    created_by = fields.String()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class WebhookSubscriptionCreateSchema(Schema):
    webhook_id = fields.UUID(required=True)
    guardrail_id = fields.UUID(allow_none=True)
    metric_id = fields.UUID(allow_none=True)
    trigger_on_actions = fields.List(
        fields.String(validate=validate.OneOf(['block', 'warn', 'redact'])),
        load_default=['block', 'warn', 'redact'],
    )
    cooldown_seconds = fields.Integer(load_default=60, validate=validate.Range(min=0, max=86400))
    include_input_text = fields.Boolean(load_default=False)
    enabled = fields.Boolean(load_default=True)


class WebhookSubscriptionSchema(Schema):
    id = fields.UUID(dump_only=True)
    webhook_id = fields.UUID()
    guardrail_id = fields.UUID(allow_none=True)
    metric_id = fields.UUID(allow_none=True)
    trigger_on_actions = fields.List(fields.String())
    cooldown_seconds = fields.Integer()
    include_input_text = fields.Boolean()
    enabled = fields.Boolean()
    tenant_id = fields.String()
    created_at = fields.DateTime()
    last_fired_at = fields.DateTime(allow_none=True)


class WebhookDeliveryLogSchema(Schema):
    id = fields.UUID(dump_only=True)
    subscription_id = fields.UUID()
    event_id = fields.UUID(allow_none=True)
    status = fields.String()
    response_status = fields.Integer(allow_none=True)
    response_body = fields.String(allow_none=True)
    error_message = fields.String(allow_none=True)
    attempt = fields.Integer()
    sent_at = fields.DateTime()
