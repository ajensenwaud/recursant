#!/usr/bin/env python3
"""Continuously stream guardrail events to the registry for live demo.

POSTs events to the same endpoint sidecars use (POST /v1/mesh/guardrail-events),
which triggers WebSocket notifications so the dashboard updates in real time.

Usage:
    python scripts/demo_guardrail_stream.py
    # With custom settings:
    REGISTRY_URL=http://localhost:8050 MESH_API_KEY=changeme python scripts/demo_guardrail_stream.py

Environment variables:
    REGISTRY_URL - Registry base URL (default: http://localhost:5000)
    MESH_API_KEY - Mesh API key (default: from .env or 'changeme')
    TENANT_ID    - Tenant ID (default: 'default')
    RATE_MIN     - Min seconds between batches (default: 2)
    RATE_MAX     - Max seconds between batches (default: 5)
    BATCH_MIN    - Min events per batch (default: 1)
    BATCH_MAX    - Max events per batch (default: 3)
"""

import os
import sys
import json
import time
import uuid
import random
import hashlib
import signal
from datetime import datetime, timezone

import requests

# Try to load .env
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

REGISTRY_URL = os.environ.get('REGISTRY_URL', 'http://localhost:5000')
MESH_API_KEY = os.environ.get('MESH_API_KEY', 'changeme')
TENANT_ID = os.environ.get('TENANT_ID', 'default')
RATE_MIN = float(os.environ.get('RATE_MIN', '2'))
RATE_MAX = float(os.environ.get('RATE_MAX', '5'))
BATCH_MIN = int(os.environ.get('BATCH_MIN', '1'))
BATCH_MAX = int(os.environ.get('BATCH_MAX', '3'))

# Synthetic data pools
GUARDRAILS = [
    {'id': str(uuid.uuid4()), 'name': 'PII Detection', 'type': 'pre_processing', 'mechanism': 'regex'},
    {'id': str(uuid.uuid4()), 'name': 'Prompt Injection Filter', 'type': 'pre_processing', 'mechanism': 'regex'},
    {'id': str(uuid.uuid4()), 'name': 'Toxicity Check', 'type': 'post_processing', 'mechanism': 'vector_lookup'},
    {'id': str(uuid.uuid4()), 'name': 'Hallucination Guard', 'type': 'post_processing', 'mechanism': 'llm_judge'},
    {'id': str(uuid.uuid4()), 'name': 'Bias Detector', 'type': 'post_processing', 'mechanism': 'ml_classifier'},
    {'id': str(uuid.uuid4()), 'name': 'Data Exfiltration Block', 'type': 'pre_processing', 'mechanism': 'regex'},
]

AGENTS = ['customer-lookup-agent', 'invoice-generator', 'support-chatbot',
          'document-analyzer', 'mortgage-advisor', 'kyc-verification-agent']

PATTERNS = [
    'SSN pattern detected', 'Credit card number', 'Email address',
    'Prompt injection attempt', 'Jailbreak attempt', 'Toxic language',
    'PII: name + address', 'System prompt extraction', 'Data exfiltration URL',
]

LATENCY_PARAMS = {
    'regex': (1.5, 0.5),
    'vector_lookup': (3.0, 0.6),
    'llm_judge': (5.5, 0.7),
    'ml_classifier': (2.5, 0.5),
}

# Simulate attack bursts: 10% of the time, emit mostly blocks
attack_mode = False
attack_counter = 0

running = True


def signal_handler(sig, frame):
    global running
    print("\nStopping stream...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def generate_event():
    """Generate a single realistic guardrail event."""
    global attack_mode, attack_counter

    guardrail = random.choice(GUARDRAILS)
    agent = random.choice(AGENTS)
    mechanism = guardrail['mechanism']

    # Attack burst mode
    if attack_mode:
        action = random.choices(['block', 'warn', 'pass'], weights=[70, 20, 10])[0]
        attack_counter -= 1
        if attack_counter <= 0:
            attack_mode = False
    else:
        action = random.choices(['pass', 'block', 'warn', 'redact'], weights=[70, 15, 10, 5])[0]
        # Random chance to start attack burst
        if random.random() < 0.05:
            attack_mode = True
            attack_counter = random.randint(5, 15)

    mu, sigma = LATENCY_PARAMS.get(mechanism, (2.0, 0.5))
    latency = round(random.lognormvariate(mu, sigma), 2)

    matched_pattern = None
    if action != 'pass':
        matched_pattern = random.choice(PATTERNS)

    is_error = random.random() < 0.02
    input_text = f'live-input-{uuid.uuid4().hex[:8]}'

    return {
        'guardrail_id': guardrail['id'],
        'guardrail_name': guardrail['name'],
        'guardrail_type': guardrail['type'],
        'mechanism': mechanism,
        'agent_name': agent,
        'sidecar_id': f'sidecar-{agent}',
        'action': action,
        'reasoning': f'{"Error: timeout" if is_error else ("Matched: " + matched_pattern if matched_pattern else "No match")}',
        'latency_ms': latency,
        'matched_pattern': matched_pattern,
        'input_hash': hashlib.sha256(input_text.encode()).hexdigest(),
        'is_error': is_error,
        'error_message': 'Evaluation timeout' if is_error else None,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def ship_events(events):
    """POST events to the registry."""
    url = f'{REGISTRY_URL}/v1/mesh/guardrail-events'
    headers = {
        'Content-Type': 'application/json',
        'X-Mesh-API-Key': MESH_API_KEY,
        'X-Tenant-ID': TENANT_ID,
    }
    try:
        resp = requests.post(url, json={'events': events}, headers=headers, timeout=10)
        return resp.status_code == 201
    except requests.RequestException as e:
        print(f"  Error shipping events: {e}")
        return False


def main():
    print(f"Guardrail Event Demo Stream")
    print(f"  Registry: {REGISTRY_URL}")
    print(f"  Tenant:   {TENANT_ID}")
    print(f"  Rate:     {RATE_MIN}-{RATE_MAX}s, {BATCH_MIN}-{BATCH_MAX} events/batch")
    print(f"  Press Ctrl+C to stop\n")

    total_shipped = 0
    start_time = time.time()

    while running:
        batch_size = random.randint(BATCH_MIN, BATCH_MAX)
        events = [generate_event() for _ in range(batch_size)]

        actions = [e['action'] for e in events]
        action_summary = ', '.join(f'{a}' for a in actions)

        if ship_events(events):
            total_shipped += batch_size
            elapsed = time.time() - start_time
            rate = total_shipped / elapsed if elapsed > 0 else 0
            mode = " [ATTACK BURST]" if attack_mode else ""
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                  f"Shipped {batch_size} events ({action_summary}) "
                  f"| Total: {total_shipped} ({rate:.1f}/s){mode}")
        else:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Failed to ship batch")

        delay = random.uniform(RATE_MIN, RATE_MAX)
        # Sleep in small increments so Ctrl+C is responsive
        slept = 0
        while running and slept < delay:
            time.sleep(min(0.5, delay - slept))
            slept += 0.5

    elapsed = time.time() - start_time
    print(f"\nDone. Shipped {total_shipped} events in {elapsed:.0f}s")


if __name__ == '__main__':
    main()
