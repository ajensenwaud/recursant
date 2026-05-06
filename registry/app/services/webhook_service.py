"""Webhook delivery service for guardrail event notifications."""

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import requests as http_requests

from app import db
from app.models.webhook import (
    WebhookDeliveryLog,
    WebhookEndpoint,
    WebhookSubscription,
)

logger = logging.getLogger(__name__)


class WebhookServiceError(Exception):
    pass


class WebhookNotFoundError(WebhookServiceError):
    pass


class WebhookService:
    """Service for webhook endpoint management and event delivery."""

    # --- Endpoint CRUD ---

    @staticmethod
    def create_endpoint(data: dict, created_by: str, tenant_id: str = 'default') -> WebhookEndpoint:
        endpoint = WebhookEndpoint(
            name=data['name'],
            url=data['url'],
            type=data.get('type', 'generic'),
            secret=data.get('secret'),
            headers=data.get('headers'),
            enabled=data.get('enabled', True),
            created_by=created_by,
            tenant_id=tenant_id,
        )
        db.session.add(endpoint)
        db.session.commit()
        logger.info("webhook_endpoint_created id=%s name=%s", endpoint.id, endpoint.name)
        return endpoint

    @staticmethod
    def update_endpoint(endpoint_id: UUID, data: dict, tenant_id: str = 'default') -> WebhookEndpoint:
        endpoint = WebhookService._get_endpoint_or_404(endpoint_id, tenant_id)
        for field in ('name', 'url', 'type', 'secret', 'headers', 'enabled'):
            if field in data:
                setattr(endpoint, field, data[field])
        endpoint.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return endpoint

    @staticmethod
    def delete_endpoint(endpoint_id: UUID, tenant_id: str = 'default'):
        endpoint = WebhookService._get_endpoint_or_404(endpoint_id, tenant_id)
        db.session.delete(endpoint)
        db.session.commit()

    @staticmethod
    def get_endpoint(endpoint_id: UUID, tenant_id: str = 'default') -> WebhookEndpoint:
        return WebhookService._get_endpoint_or_404(endpoint_id, tenant_id)

    @staticmethod
    def list_endpoints(tenant_id: str = 'default', page: int = 1, per_page: int = 50):
        return WebhookEndpoint.query.filter_by(
            tenant_id=tenant_id,
        ).order_by(WebhookEndpoint.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False,
        )

    # --- Subscription CRUD ---

    @staticmethod
    def create_subscription(data: dict, tenant_id: str = 'default') -> WebhookSubscription:
        sub = WebhookSubscription(
            webhook_id=data['webhook_id'],
            guardrail_id=data.get('guardrail_id'),
            metric_id=data.get('metric_id'),
            trigger_on_actions=data.get('trigger_on_actions', ['block', 'warn', 'redact']),
            cooldown_seconds=data.get('cooldown_seconds', 60),
            include_input_text=data.get('include_input_text', False),
            enabled=data.get('enabled', True),
            tenant_id=tenant_id,
        )
        db.session.add(sub)
        db.session.commit()
        return sub

    @staticmethod
    def delete_subscription(subscription_id: UUID, tenant_id: str = 'default'):
        sub = WebhookSubscription.query.filter_by(
            id=subscription_id, tenant_id=tenant_id,
        ).first()
        if not sub:
            raise WebhookNotFoundError('Subscription not found')
        db.session.delete(sub)
        db.session.commit()

    @staticmethod
    def list_subscriptions(
        tenant_id: str = 'default',
        webhook_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ):
        query = WebhookSubscription.query.filter_by(tenant_id=tenant_id)
        if webhook_id:
            query = query.filter_by(webhook_id=webhook_id)
        return query.order_by(WebhookSubscription.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False,
        )

    # --- Delivery log ---

    @staticmethod
    def list_delivery_logs(
        tenant_id: str = 'default',
        subscription_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ):
        query = WebhookDeliveryLog.query
        if subscription_id:
            query = query.filter_by(subscription_id=subscription_id)
        else:
            # Filter by tenant via subscription join
            query = query.join(WebhookSubscription).filter(
                WebhookSubscription.tenant_id == tenant_id,
            )
        return query.order_by(WebhookDeliveryLog.sent_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False,
        )

    # --- Event processing ---

    @staticmethod
    def process_guardrail_event(event_record, tenant_id: str = 'default'):
        """Match subscriptions and deliver webhooks for a guardrail event.

        Called in a background thread after DB insert.
        """
        action = getattr(event_record, 'action', None) or 'pass'
        if action == 'pass':
            return  # No notification for pass events

        guardrail_id = getattr(event_record, 'guardrail_id', None)
        metric_id = getattr(event_record, 'metric_id', None)

        # Find matching subscriptions
        subs = WebhookSubscription.query.join(WebhookEndpoint).filter(
            WebhookSubscription.tenant_id == tenant_id,
            WebhookSubscription.enabled.is_(True),
            WebhookEndpoint.enabled.is_(True),
        ).all()

        now = datetime.now(timezone.utc)

        for sub in subs:
            # Check action filter
            trigger_actions = sub.trigger_on_actions or ['block', 'warn', 'redact']
            if action not in trigger_actions:
                continue

            # Check guardrail/metric filter
            if sub.guardrail_id and str(sub.guardrail_id) != str(guardrail_id or ''):
                continue
            if sub.metric_id and str(sub.metric_id) != str(metric_id or ''):
                continue

            # Check cooldown
            if sub.last_fired_at:
                cooldown_end = sub.last_fired_at + timedelta(seconds=sub.cooldown_seconds)
                if now < cooldown_end:
                    continue

            # Build payload
            endpoint = sub.endpoint
            payload = WebhookService._format_payload(
                endpoint.type, event_record, sub.include_input_text,
            )

            # Deliver
            WebhookService._deliver(endpoint, sub, event_record, payload)

    @staticmethod
    def _format_payload(webhook_type: str, event, include_input: bool) -> dict:
        """Format event payload for the webhook type."""
        base = {
            'event_type': 'guardrail_trigger',
            'guardrail_name': getattr(event, 'guardrail_name', ''),
            'agent_name': getattr(event, 'agent_name', ''),
            'action': getattr(event, 'action', ''),
            'mechanism': getattr(event, 'mechanism', ''),
            'reasoning': getattr(event, 'reasoning', ''),
            'timestamp': str(getattr(event, 'timestamp', '')),
            'triggered_spans': getattr(event, 'triggered_spans', None),
        }

        if webhook_type == 'slack':
            action_emoji = {'block': ':no_entry:', 'warn': ':warning:', 'redact': ':scissors:'}.get(
                base['action'], ':bell:'
            )
            return {
                'text': (
                    f"{action_emoji} Guardrail *{base['guardrail_name']}* triggered "
                    f"({base['action']}) on agent *{base['agent_name']}*"
                ),
                'blocks': [
                    {
                        'type': 'section',
                        'text': {
                            'type': 'mrkdwn',
                            'text': (
                                f"{action_emoji} *Guardrail Alert*\n"
                                f"*Guardrail:* {base['guardrail_name']}\n"
                                f"*Agent:* {base['agent_name']}\n"
                                f"*Action:* {base['action']}\n"
                                f"*Mechanism:* {base['mechanism']}\n"
                                f"*Reasoning:* {base['reasoning'][:200]}"
                            ),
                        },
                    },
                ],
            }

        elif webhook_type == 'pagerduty':
            severity = 'critical' if base['action'] == 'block' else 'warning'
            return {
                'routing_key': '',  # Filled from endpoint secret
                'event_action': 'trigger',
                'payload': {
                    'summary': (
                        f"Guardrail {base['guardrail_name']} {base['action']} "
                        f"on agent {base['agent_name']}"
                    ),
                    'severity': severity,
                    'source': 'recursant-registry',
                    'component': base['agent_name'],
                    'custom_details': base,
                },
            }

        elif webhook_type == 'teams':
            color = {'block': 'FF0000', 'warn': 'FFA500', 'redact': '800080'}.get(
                base['action'], '808080'
            )
            return {
                '@type': 'MessageCard',
                'themeColor': color,
                'summary': f"Guardrail {base['guardrail_name']} triggered",
                'sections': [{
                    'activityTitle': f"Guardrail Alert: {base['guardrail_name']}",
                    'facts': [
                        {'name': 'Agent', 'value': base['agent_name']},
                        {'name': 'Action', 'value': base['action']},
                        {'name': 'Mechanism', 'value': base['mechanism']},
                        {'name': 'Reasoning', 'value': base['reasoning'][:200]},
                    ],
                }],
            }

        # generic
        return base

    @staticmethod
    def _deliver(endpoint: WebhookEndpoint, sub: WebhookSubscription, event, payload: dict):
        """Deliver webhook with retries and logging."""
        max_attempts = 3
        event_id = getattr(event, 'id', None)

        for attempt in range(1, max_attempts + 1):
            log = WebhookDeliveryLog(
                subscription_id=sub.id,
                event_id=event_id,
                attempt=attempt,
                status='pending',
            )

            try:
                headers = {'Content-Type': 'application/json'}
                if endpoint.headers:
                    headers.update(endpoint.headers)

                # Sign payload if secret configured
                if endpoint.secret:
                    body_bytes = json.dumps(payload).encode()
                    sig = hmac.new(
                        endpoint.secret.encode(), body_bytes, hashlib.sha256,
                    ).hexdigest()
                    headers['X-Webhook-Signature'] = f'sha256={sig}'

                # For PagerDuty, set routing key from secret
                if endpoint.type == 'pagerduty' and endpoint.secret:
                    payload['routing_key'] = endpoint.secret

                resp = http_requests.post(
                    endpoint.url,
                    json=payload,
                    headers=headers,
                    timeout=10,
                )

                log.response_status = resp.status_code
                log.response_body = resp.text[:1000] if resp.text else None

                if resp.ok:
                    log.status = 'success'
                    sub.last_fired_at = datetime.now(timezone.utc)
                    db.session.add(log)
                    db.session.commit()
                    return
                else:
                    log.status = 'failed'
                    log.error_message = f'HTTP {resp.status_code}'

            except Exception as e:
                log.status = 'failed'
                log.error_message = str(e)[:500]
                logger.warning("webhook_delivery_failed attempt=%d error=%s", attempt, e)

            db.session.add(log)
            db.session.commit()

        logger.error(
            "webhook_delivery_exhausted endpoint=%s subscription=%s",
            endpoint.id, sub.id,
        )

    @staticmethod
    def test_endpoint(endpoint_id: UUID, tenant_id: str = 'default') -> dict:
        """Send a test payload to verify connectivity."""
        endpoint = WebhookService._get_endpoint_or_404(endpoint_id, tenant_id)

        test_payload = WebhookService._format_payload(
            endpoint.type,
            type('MockEvent', (), {
                'guardrail_name': 'test-guardrail',
                'agent_name': 'test-agent',
                'action': 'block',
                'mechanism': 'llm_judge',
                'reasoning': 'This is a test webhook delivery',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'triggered_spans': None,
                'id': None,
            })(),
            include_input=False,
        )

        try:
            headers = {'Content-Type': 'application/json'}
            if endpoint.headers:
                headers.update(endpoint.headers)

            resp = http_requests.post(
                endpoint.url, json=test_payload, headers=headers, timeout=10,
            )
            return {
                'success': resp.ok,
                'status_code': resp.status_code,
                'response': resp.text[:500] if resp.text else None,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # --- Helpers ---

    @staticmethod
    def _get_endpoint_or_404(endpoint_id: UUID, tenant_id: str) -> WebhookEndpoint:
        endpoint = WebhookEndpoint.query.filter_by(
            id=endpoint_id, tenant_id=tenant_id,
        ).first()
        if not endpoint:
            raise WebhookNotFoundError(f'Webhook endpoint {endpoint_id} not found')
        return endpoint
