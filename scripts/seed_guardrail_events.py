#!/usr/bin/env python3
"""Seed the guardrail_events table with realistic historical data.

Generates ~2000 events spread over the last 30 days with realistic
distributions for the observability dashboard.

Usage:
    python scripts/seed_guardrail_events.py
    # or from Docker:
    docker exec -it registry-api python scripts/seed_guardrail_events.py
"""

import os
import sys
import uuid
import random
import hashlib
from datetime import datetime, timedelta, timezone

# Add the registry directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'registry'))

from app import create_app, db
from app.models.guardrail import GuardrailEvent, Guardrail


def generate_events(tenant_id='default', num_events=2000, days_back=30):
    """Generate realistic guardrail events."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    # Try to use real guardrails from DB
    guardrails = Guardrail.query.filter_by(tenant_id=tenant_id).filter(
        Guardrail.deleted_at.is_(None)
    ).all()

    if guardrails:
        guardrail_pool = [
            {
                'id': str(g.id),
                'name': g.name,
                'type': g.type.value,
                'mechanism': g.mechanism.value,
            }
            for g in guardrails
        ]
    else:
        # Synthetic guardrails if none exist
        guardrail_pool = [
            {'id': str(uuid.uuid4()), 'name': 'PII Detection', 'type': 'pre_processing', 'mechanism': 'regex'},
            {'id': str(uuid.uuid4()), 'name': 'Prompt Injection Filter', 'type': 'pre_processing', 'mechanism': 'regex'},
            {'id': str(uuid.uuid4()), 'name': 'Toxicity Check', 'type': 'post_processing', 'mechanism': 'vector_lookup'},
            {'id': str(uuid.uuid4()), 'name': 'Hallucination Guard', 'type': 'post_processing', 'mechanism': 'llm_judge'},
            {'id': str(uuid.uuid4()), 'name': 'Bias Detector', 'type': 'post_processing', 'mechanism': 'ml_classifier'},
            {'id': str(uuid.uuid4()), 'name': 'Data Exfiltration Block', 'type': 'pre_processing', 'mechanism': 'regex'},
        ]

    agent_names = [
        'customer-lookup-agent', 'invoice-generator', 'support-chatbot',
        'document-analyzer', 'mortgage-advisor', 'kyc-verification-agent',
    ]
    sidecar_ids = [f'sidecar-{name}' for name in agent_names]

    # Action distribution: 70% pass, 15% block, 10% warn, 5% redact
    action_weights = {'pass': 70, 'block': 15, 'warn': 10, 'redact': 5}
    actions = []
    for action, weight in action_weights.items():
        actions.extend([action] * weight)

    patterns = [
        'SSN pattern detected', 'Credit card number', 'Email address',
        'Phone number', 'Prompt injection attempt', 'Ignore previous instructions',
        'System prompt extraction', 'Jailbreak attempt', 'PII: name + address',
        'Toxic language detected', 'Biased content', 'Data exfiltration URL',
    ]

    # Latency distributions by mechanism (log-normal)
    latency_params = {
        'regex': (1.5, 0.5),       # ~5-20ms
        'vector_lookup': (3.0, 0.6),  # ~15-80ms
        'llm_judge': (5.5, 0.7),    # ~150-600ms
        'ml_classifier': (2.5, 0.5),  # ~10-40ms
    }

    events = []
    for i in range(num_events):
        # Random timestamp spread over the period, with some daily patterns
        seconds_offset = random.uniform(0, days_back * 86400)
        ts = start + timedelta(seconds=seconds_offset)

        # Add business-hours weighting (more events during 8am-6pm UTC)
        hour = ts.hour
        if hour < 8 or hour > 18:
            if random.random() > 0.3:
                ts = ts.replace(hour=random.randint(8, 17))

        guardrail = random.choice(guardrail_pool)
        agent_idx = random.randint(0, len(agent_names) - 1)
        action = random.choice(actions)

        # Mechanism-specific latency
        mechanism = guardrail['mechanism']
        mu, sigma = latency_params.get(mechanism, (2.0, 0.5))
        latency = random.lognormvariate(mu, sigma)

        # Matched pattern only for non-pass actions
        matched_pattern = None
        if action != 'pass':
            matched_pattern = random.choice(patterns)

        # Small error rate (2%)
        is_error = random.random() < 0.02
        error_message = 'Evaluation timeout' if is_error else None

        # Input hash
        input_text = f'sample-input-{i}-{random.randint(0, 10000)}'
        input_hash = hashlib.sha256(input_text.encode()).hexdigest()

        event = GuardrailEvent(
            tenant_id=tenant_id,
            guardrail_id=guardrail['id'],
            guardrail_name=guardrail['name'],
            guardrail_type=guardrail['type'],
            mechanism=mechanism,
            agent_name=agent_names[agent_idx],
            sidecar_id=sidecar_ids[agent_idx],
            action=action,
            reasoning=f'{"Error: " + error_message if is_error else ("Matched: " + matched_pattern if matched_pattern else "No match")}',
            latency_ms=round(latency, 2),
            matched_pattern=matched_pattern,
            input_hash=input_hash,
            is_error=is_error,
            error_message=error_message,
            timestamp=ts,
        )
        events.append(event)

    return events


def main():
    app = create_app(os.environ.get('FLASK_ENV', 'development'))
    with app.app_context():
        tenant_id = os.environ.get('TENANT_ID', 'default')
        num_events = int(os.environ.get('NUM_EVENTS', '2000'))
        days_back = int(os.environ.get('DAYS_BACK', '30'))

        # Check if events already exist
        existing = GuardrailEvent.query.filter_by(tenant_id=tenant_id).count()
        if existing > 0:
            print(f"Found {existing} existing events for tenant '{tenant_id}'.")
            resp = input("Clear and re-seed? [y/N] ").strip().lower()
            if resp != 'y':
                print("Aborted.")
                return
            GuardrailEvent.query.filter_by(tenant_id=tenant_id).delete()
            db.session.commit()
            print(f"Cleared {existing} events.")

        print(f"Generating {num_events} guardrail events over {days_back} days...")
        events = generate_events(tenant_id, num_events, days_back)

        # Bulk insert in batches
        batch_size = 500
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            db.session.add_all(batch)
            db.session.commit()
            print(f"  Inserted {min(i + batch_size, len(events))}/{len(events)}")

        print(f"Done! Seeded {len(events)} guardrail events.")


if __name__ == '__main__':
    main()
