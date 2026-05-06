#!/usr/bin/env python3
"""Continuous traffic simulator for the observability dashboard.

Produces events via the registry REST API (which forwards to Kafka or
writes directly to PG), populating all observability tabs with live data.

Usage:
    python scripts/simulate_observability_demo.py
    python scripts/simulate_observability_demo.py --rps 5

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    REGISTRY_USERNAME / REGISTRY_PASSWORD: Admin credentials
    MESH_API_KEY: API key for mesh endpoints
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

DEFAULT_REGISTRY_URL = "http://localhost:5000"

AGENTS = [
    "Customer Agent",
    "Authentication Agent",
    "KYC Agent",
    "Credit Agent",
    "Core Banking Agent",
    "Compliance Crew",
    "Research Assistant",
    "Fact Checker Agent",
]

VALID_ROUTES = [
    ("Customer Agent", "Authentication Agent"),
    ("Customer Agent", "KYC Agent"),
    ("Customer Agent", "Credit Agent"),
    ("Customer Agent", "Core Banking Agent"),
    ("Customer Agent", "Compliance Crew"),
    ("Research Assistant", "Fact Checker Agent"),
]

# Intentionally cross-zone routes for policy violations
VIOLATION_ROUTES = [
    ("Credit Agent", "KYC Agent"),           # US -> EU
    ("Compliance Crew", "Research Assistant"), # US -> APAC
]

A2A_METHODS = ["tasks/send", "tasks/get", "tasks/sendSubscribe"]

MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "gpt-4o-mini",
]

COST_PER_TOKEN = {
    "claude-sonnet-4-5-20250929": (0.000003, 0.000015),
    "claude-haiku-4-5-20251001": (0.0000008, 0.000004),
    "gpt-4o-mini": (0.00000015, 0.0000006),
}

# Fallback guardrail pool (used if API fetch fails)
GUARDRAIL_POOL_FALLBACK = [
    {"name": "PII Detection", "type": "pre_processing", "mechanism": "regex"},
    {"name": "Prompt Injection Filter", "type": "pre_processing", "mechanism": "regex"},
    {"name": "Toxicity Check", "type": "post_processing", "mechanism": "vector_lookup"},
    {"name": "Hallucination Guard", "type": "post_processing", "mechanism": "llm_judge"},
    {"name": "Bias Detector", "type": "post_processing", "mechanism": "ml_classifier"},
    {"name": "Data Exfiltration Block", "type": "pre_processing", "mechanism": "regex"},
]

# Which agents have which guardrails assigned (mirrors seed script)
GUARDRAIL_AGENT_MAP = {
    "PII Detection": AGENTS,
    "Prompt Injection Filter": AGENTS,
    "Toxicity Check": ["Customer Agent", "Research Assistant", "Fact Checker Agent"],
    "Hallucination Guard": ["Customer Agent", "Credit Agent", "Compliance Crew", "Research Assistant"],
    "Bias Detector": ["Customer Agent", "KYC Agent", "Credit Agent"],
    "Data Exfiltration Block": AGENTS,
}

running = True


def signal_handler(sig, frame):
    global running
    running = False
    print("\nShutting down...")


def fetch_guardrail_ids(base_url: str, headers: dict) -> list[dict]:
    """Fetch real guardrail definitions from the registry API.

    Returns list of dicts with id, name, type, mechanism.
    Falls back to GUARDRAIL_POOL_FALLBACK if API is unavailable.
    """
    try:
        resp = httpx.get(
            f"{base_url}/v1/guardrails",
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            guardrails = data.get("guardrails", data) if isinstance(data, dict) else data
            pool = []
            for g in guardrails:
                gid = g.get("id")
                name = g.get("name")
                if gid and name:
                    pool.append({
                        "id": str(gid),
                        "name": name,
                        "type": g.get("type", g.get("guardrail_type", "pre_processing")),
                        "mechanism": g.get("mechanism", "regex"),
                    })
            if pool:
                print(f"  Fetched {len(pool)} guardrails from API")
                return pool
    except Exception as e:
        print(f"  Could not fetch guardrails from API: {e}")

    print("  Using fallback guardrail pool (no IDs)")
    return [{"name": g["name"], "type": g["type"], "mechanism": g["mechanism"]}
            for g in GUARDRAIL_POOL_FALLBACK]


def login(base_url: str, username: str, password: str) -> str:
    resp = httpx.post(
        f"{base_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["token"]


def generate_audit_batch(batch_size: int, traffic_mix: str = "normal") -> list[dict]:
    """Generate a batch of audit records."""
    records = []
    for _ in range(batch_size):
        now = datetime.now(timezone.utc)

        # Pick route based on traffic mix
        if traffic_mix == "violation" and random.random() < 0.5:
            src, dst = random.choice(VIOLATION_ROUTES)
            decision = "block"
            outcome = "blocked"
        elif traffic_mix == "error_burst" and random.random() < 0.6:
            src, dst = random.choice(VALID_ROUTES)
            decision = "allow"
            outcome = "error"
        else:
            src, dst = random.choice(VALID_ROUTES)
            r = random.random()
            if r < 0.03:
                decision = "block"
                outcome = "blocked"
            elif r < 0.08:
                decision = "allow"
                outcome = "error"
            else:
                decision = "allow"
                outcome = "success"

        model = random.choice(MODELS)
        input_tokens = random.randint(100, 3000)
        output_tokens = random.randint(50, 2000)
        cost_in, cost_out = COST_PER_TOKEN.get(model, (0.000003, 0.000015))

        records.append({
            "timestamp": now.isoformat(),
            "source_agent_name": src,
            "dest_agent_name": dst,
            "task_id": str(uuid.uuid4()),
            "a2a_method": random.choice(A2A_METHODS),
            "message_hash": hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:16],
            "direction": "outbound",
            "decision": decision,
            "outcome": outcome,
            "sidecar_id": f"sidecar-{src.lower().replace(' ', '-')}",
            "details": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model_name": model,
                "estimated_cost_usd": round(input_tokens * cost_in + output_tokens * cost_out, 8),
                "latency_ms": round(random.lognormvariate(4.5, 0.8), 1),
            },
        })

    return records


def generate_guardrail_events(
    batch_size: int, guardrail_pool: list[dict], is_attack: bool = False,
) -> list[dict]:
    """Generate guardrail events using real guardrail IDs when available."""
    events = []
    for _ in range(batch_size):
        g = random.choice(guardrail_pool)

        # Pick an agent that actually has this guardrail assigned
        assigned_agents = GUARDRAIL_AGENT_MAP.get(g["name"], AGENTS)
        agent = random.choice(assigned_agents)

        if is_attack:
            action = random.choice(["block", "block", "block", "warn", "pass"])
        else:
            action = random.choices(
                ["pass", "block", "warn", "redact"],
                weights=[70, 15, 10, 5],
                k=1,
            )[0]

        event = {
            "guardrail_name": g["name"],
            "guardrail_type": g["type"],
            "mechanism": g["mechanism"],
            "agent_name": agent,
            "sidecar_id": f"sidecar-{agent.lower().replace(' ', '-')}",
            "action": action,
            "reasoning": f"{'Attack pattern detected' if action == 'block' else 'Checks passed'}",
            "latency_ms": round(random.lognormvariate(
                {"regex": 1.5, "vector_lookup": 3.0, "llm_judge": 5.5, "ml_classifier": 2.5}.get(g["mechanism"], 2.0),
                0.5,
            ), 2),
            "matched_pattern": "Suspicious pattern" if action != "pass" else None,
            "input_hash": hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest(),
        }

        # Include guardrail_id if available (from API fetch)
        if "id" in g:
            event["guardrail_id"] = g["id"]

        events.append(event)

    return events


def main():
    parser = argparse.ArgumentParser(description="Simulate observability traffic")
    parser.add_argument("--registry-url", default=os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL))
    parser.add_argument("--username", default=os.environ.get("REGISTRY_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("REGISTRY_PASSWORD", "admin"))
    parser.add_argument("--mesh-api-key", default=os.environ.get("MESH_API_KEY", "mesh-dev-key"))
    parser.add_argument("--rps", type=float, default=2.0, help="Target events per second")
    args = parser.parse_args()

    base_url = args.registry_url.rstrip("/")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"Simulator starting — {base_url}, target {args.rps} events/sec")

    # Login
    print("Logging in...")
    token = login(base_url, args.username, args.password)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
    }
    mesh_headers = {
        "Content-Type": "application/json",
        "X-Mesh-API-Key": args.mesh_api_key,
        "X-Tenant-ID": "default",
    }

    interval = 1.0 / max(args.rps, 0.1)
    total_sent = 0
    start_time = time.monotonic()
    cycle = 0

    # Fetch real guardrail IDs from the registry
    print("Fetching guardrail definitions...")
    guardrail_pool = fetch_guardrail_ids(base_url, headers)

    print(f"Streaming events (interval={interval:.2f}s)... Press Ctrl+C to stop.")

    while running:
        cycle += 1

        # Traffic mix: 70% normal, 15% guardrail triggers, 10% policy violations, 5% error bursts
        r = random.random()
        if r < 0.05:
            mix = "error_burst"
        elif r < 0.15:
            mix = "violation"
        else:
            mix = "normal"

        # Attack burst every ~50 cycles
        is_attack = cycle % 50 == 0

        # Send audit batch
        batch_size = random.randint(1, 3)
        audit_records = generate_audit_batch(batch_size, traffic_mix=mix)
        try:
            resp = httpx.post(
                f"{base_url}/v1/mesh/audit",
                json={"records": audit_records},
                headers=mesh_headers,
                timeout=10.0,
            )
            if resp.status_code in (201, 202):
                total_sent += batch_size
            else:
                print(f"  Audit POST failed: {resp.status_code}")
        except Exception as e:
            print(f"  Audit error: {e}")

        # Guardrail events (every 2-3 cycles)
        if cycle % random.randint(2, 3) == 0:
            g_batch = random.randint(1, 2)
            events = generate_guardrail_events(g_batch, guardrail_pool, is_attack=is_attack)
            try:
                resp = httpx.post(
                    f"{base_url}/v1/mesh/guardrail-events",
                    json={"events": events},
                    headers=mesh_headers,
                    timeout=10.0,
                )
                if resp.status_code in (201, 202):
                    total_sent += g_batch
            except Exception as e:
                print(f"  Guardrail error: {e}")

        elapsed = time.monotonic() - start_time
        rate = total_sent / elapsed if elapsed > 0 else 0

        if cycle % 20 == 0:
            print(f"  [{cycle}] Sent {total_sent} events ({rate:.1f}/s) [{mix}]")

        time.sleep(interval)

    elapsed = time.monotonic() - start_time
    print(f"\nDone. Sent {total_sent} events in {elapsed:.0f}s ({total_sent / elapsed:.1f}/s)")


if __name__ == "__main__":
    main()
