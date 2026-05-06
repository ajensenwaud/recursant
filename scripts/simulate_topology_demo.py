#!/usr/bin/env python3
"""Continuous topology demo simulator.

Seeds 10 agents (2 new + 8 existing) and 10 tools (2 new + 8 existing),
then continuously generates multi-hop traces with agent-to-agent calls,
agent-to-tool calls, CoT analysis data, and varied outcomes.

Usage:
    # Run inside the registry pod:
    kubectl exec -n recursant deploy/recursant-registry -- \
        python scripts/simulate_topology_demo.py

    # Or with custom settings:
    python scripts/simulate_topology_demo.py --rps 3 --registry-url http://localhost:5000

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    ADMIN_PASSWORD: Admin password
    MESH_API_KEY: Mesh API key (default: mesh-dev-key)
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

# ── Agent definitions ────────────────────────────────────────────────────────

EXISTING_AGENTS = [
    "Customer Agent",
    "Authentication Agent",
    "KYC Agent",
    "Credit Agent",
    "Core Banking Agent",
    "Compliance Crew",
    "Research Assistant",
    "Fact Checker Agent",
]

NEW_AGENTS = [
    {
        "name": "Fraud Detection Agent",
        "description": "Real-time fraud detection using ML models and rule engines",
        "zone": "US",
        "capabilities": [
            {"name": "transaction-screening", "description": "Screen transactions for fraud patterns"},
        ],
    },
    {
        "name": "Document Processing Agent",
        "description": "Extracts and validates information from uploaded documents",
        "zone": "EU",
        "capabilities": [
            {"name": "document-extraction", "description": "Extract structured data from documents"},
        ],
    },
]

ALL_AGENTS = EXISTING_AGENTS + [a["name"] for a in NEW_AGENTS]

AGENT_ZONES = {
    "Customer Agent": "EU",
    "Authentication Agent": "EU",
    "KYC Agent": "EU",
    "Credit Agent": "US",
    "Core Banking Agent": "US",
    "Compliance Crew": "US",
    "Research Assistant": "APAC",
    "Fact Checker Agent": "APAC",
    "Fraud Detection Agent": "US",
    "Document Processing Agent": "EU",
}

# ── Tool definitions ─────────────────────────────────────────────────────────

NEW_TOOLS = [
    {
        "name": "screen_transaction",
        "description": "Screen a financial transaction against fraud rules",
        "endpoint_url": "http://fraud-engine:8080/v1/screen",
        "mcp_server_name": "Fraud Engine",
        "mcp_server_url": "http://fraud-engine:8080",
        "mcp_server_description": "Real-time transaction fraud screening service",
        "assign_to": "Fraud Detection Agent",
    },
    {
        "name": "extract_document_data",
        "description": "Extract structured fields from scanned documents",
        "endpoint_url": "http://doc-processor:8080/v1/extract",
        "mcp_server_name": "Document Processor",
        "mcp_server_url": "http://doc-processor:8080",
        "mcp_server_description": "OCR and NLP document extraction service",
        "assign_to": "Document Processing Agent",
    },
]

# Existing tools with their assigned agents (for tool call simulation)
TOOL_AGENT_MAP = {
    "verify_customer": "Authentication Agent",
    "make_credit_decision": "Credit Agent",
    "disburse_loan": "Core Banking Agent",
    "verify_identity": "KYC Agent",
    "assess_credit_capacity": "Credit Agent",
    "check_lending_regulations": "Compliance Crew",
    "verify_document_completeness": "Compliance Crew",
    "calculate_compliance_score": "Compliance Crew",
    "screen_transaction": "Fraud Detection Agent",
    "extract_document_data": "Document Processing Agent",
}

# ── Traffic routes ────────────────────────────────────────────────────────────

# Multi-hop trace templates: each is a sequence of (source, dest) hops
TRACE_TEMPLATES = [
    # Mortgage application flow
    [
        ("Customer Agent", "Authentication Agent"),
        ("Customer Agent", "KYC Agent"),
        ("Customer Agent", "Credit Agent"),
        ("Credit Agent", "Compliance Crew"),
        ("Customer Agent", "Core Banking Agent"),
    ],
    # Quick credit check
    [
        ("Customer Agent", "Credit Agent"),
        ("Credit Agent", "Compliance Crew"),
    ],
    # Research flow
    [
        ("Research Assistant", "Fact Checker Agent"),
    ],
    # Fraud check flow
    [
        ("Customer Agent", "Fraud Detection Agent"),
        ("Fraud Detection Agent", "KYC Agent"),
    ],
    # Document submission flow
    [
        ("Customer Agent", "Document Processing Agent"),
        ("Document Processing Agent", "KYC Agent"),
        ("Document Processing Agent", "Compliance Crew"),
    ],
    # Full onboarding
    [
        ("Customer Agent", "Authentication Agent"),
        ("Customer Agent", "Document Processing Agent"),
        ("Document Processing Agent", "KYC Agent"),
        ("Customer Agent", "Fraud Detection Agent"),
        ("Customer Agent", "Credit Agent"),
        ("Customer Agent", "Core Banking Agent"),
    ],
]

# Tool call probabilities per agent (agent -> list of tools it might call)
AGENT_TOOL_CALLS = {
    "Authentication Agent": ["verify_customer"],
    "KYC Agent": ["verify_identity"],
    "Credit Agent": ["make_credit_decision", "assess_credit_capacity"],
    "Core Banking Agent": ["disburse_loan"],
    "Compliance Crew": ["check_lending_regulations", "verify_document_completeness", "calculate_compliance_score"],
    "Fraud Detection Agent": ["screen_transaction"],
    "Document Processing Agent": ["extract_document_data"],
}

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

COT_RISK_LEVELS = ["low", "medium", "high"]

COT_FLAGS = [
    "prompt_injection_attempt",
    "data_exfiltration_risk",
    "goal_hijacking_detected",
    "unexpected_tool_invocation",
    "sensitive_data_in_context",
    "retrieval_manipulation",
    "instruction_override_attempt",
]

COT_REASONING_TEMPLATES = [
    {
        "reasoning_steps": [
            "Validated user input against schema",
            "No injection patterns detected",
            "Output conforms to expected format",
        ],
        "risk_level": "low",
        "confidence": 0.98,
    },
    {
        "reasoning_steps": [
            "Input contains encoded payload - decoding for inspection",
            "Payload appears benign after decoding",
            "Proceeding with caution - elevated monitoring",
        ],
        "risk_level": "medium",
        "confidence": 0.72,
    },
    {
        "reasoning_steps": [
            "Detected attempt to override system instructions",
            "Agent attempted to access unauthorized tool",
            "Blocking request and flagging for review",
        ],
        "risk_level": "high",
        "confidence": 0.95,
    },
    {
        "reasoning_steps": [
            "Retrieved documents verified against source",
            "No hallucination indicators in response",
            "Response consistent with retrieved context",
        ],
        "risk_level": "low",
        "confidence": 0.91,
    },
    {
        "reasoning_steps": [
            "Tool call sequence deviates from normal pattern",
            "Intermediate result contains PII that wasn't in input",
            "Possible data leakage via retrieval augmentation",
        ],
        "risk_level": "medium",
        "confidence": 0.65,
    },
]

running = True


def signal_handler(sig, frame):
    global running
    running = False
    print("\nShutting down...")


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


def ensure_agents(base_url: str, headers: dict, mesh_headers: dict):
    """Create and register the 2 new agents if they don't exist."""
    for agent_def in NEW_AGENTS:
        name = agent_def["name"]

        # Check if agent already exists
        resp = httpx.post(
            f"{base_url}/v1/agents/search",
            json={"query": name, "filters": {}},
            headers=headers,
            timeout=10.0,
        )
        existing = None
        if resp.status_code == 200:
            results = resp.json().get("results", resp.json().get("agents", []))
            for r in results:
                if r.get("name") == name:
                    existing = r
                    break

        if existing:
            agent_id = existing["id"]
            status = existing.get("status", "")
            print(f"  Agent '{name}' exists (id={agent_id}, status={status})")
            if status in ("ACTIVE", "active"):
                _ensure_registration(base_url, mesh_headers, agent_id, name, agent_def)
                continue
        else:
            # Create agent
            resp = httpx.post(
                f"{base_url}/v1/agents",
                json={
                    "name": name,
                    "description": agent_def["description"],
                    "version": "1.0.0",
                    "classification": "internal",
                    "risk_tier": "medium",
                    "data_sensitivity": "pii",
                    "endpoint": {
                        "type": "langgraph",
                        "url": f"http://{name.lower().replace(' ', '-')}:5010",
                        "auth_method": "mtls",
                        "timeout_ms": 30000,
                    },
                    "capabilities": agent_def["capabilities"],
                },
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                print(f"  Failed to create agent '{name}': {resp.status_code} {resp.text}")
                continue
            agent_id = resp.json()["id"]
            print(f"  Created agent '{name}' (id={agent_id})")

        # Fast-track to ACTIVE via direct DB (no governance bypass API)
        _activate_agent_direct(base_url, headers, agent_id, name)
        _ensure_registration(base_url, mesh_headers, agent_id, name, agent_def)


def _activate_agent_direct(base_url: str, headers: dict, agent_id: str, name: str):
    """Activate agent by running it through the pipeline steps via direct DB update."""
    # We'll use a script approach since there's no bypass API
    # Submit, then do direct DB status update inside the pod
    pass  # Will be handled in the seed step


def _ensure_registration(base_url: str, mesh_headers: dict, agent_id: str, name: str, agent_def: dict):
    """Register the agent's sidecar in the mesh."""
    zone = AGENT_ZONES.get(name, "US")
    resp = httpx.post(
        f"{base_url}/v1/mesh/register",
        json={
            "agent_id": agent_id,
            "sidecar_url": f"http://sidecar-{name.lower().replace(' ', '-')}:9000",
            "agent_card": {
                "name": name,
                "description": agent_def.get("description", ""),
                "version": "1.0.0",
                "skills": [{"id": "default", "name": "default"}],
                "default_input_modes": ["text"],
                "default_output_modes": ["text"],
                "capabilities": {"streaming": False},
                "endpoint": {"type": "langgraph", "url": f"http://{name.lower().replace(' ', '-')}:5010"},
                "zone": zone,
            },
            "sovereignty_zone": zone,
        },
        headers=mesh_headers,
        timeout=10.0,
    )
    if resp.status_code in (200, 201):
        print(f"  Registered sidecar for '{name}'")
    else:
        print(f"  Registration for '{name}': {resp.status_code} (may already exist)")


def ensure_tools(base_url: str, headers: dict):
    """Create and approve the 2 new tools with assignments."""
    for tool_def in NEW_TOOLS:
        name = tool_def["name"]

        # Check if tool already exists
        resp = httpx.get(
            f"{base_url}/v1/mesh/tools?name={name}",
            headers=headers,
            timeout=10.0,
        )
        existing = None
        if resp.status_code == 200:
            tools = resp.json().get("tools", [])
            for t in tools:
                if t.get("name") == name:
                    existing = t
                    break

        if existing:
            tool_id = existing["id"]
            print(f"  Tool '{name}' exists (id={tool_id}, status={existing['status']})")
            if existing["status"] != "approved":
                # Approve it
                resp = httpx.post(
                    f"{base_url}/v1/mesh/tools/{tool_id}/approve",
                    json={"justification": "Demo tool auto-approved"},
                    headers=headers,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    print(f"  Approved tool '{name}'")
        else:
            # Create tool
            resp = httpx.post(
                f"{base_url}/v1/mesh/tools",
                json={
                    "name": name,
                    "description": tool_def["description"],
                    "endpoint_url": tool_def["endpoint_url"],
                    "mcp_server_name": tool_def.get("mcp_server_name"),
                    "mcp_server_url": tool_def.get("mcp_server_url"),
                    "mcp_server_description": tool_def.get("mcp_server_description"),
                },
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                print(f"  Failed to create tool '{name}': {resp.status_code} {resp.text}")
                continue
            tool_id = resp.json()["id"]
            print(f"  Created tool '{name}' (id={tool_id})")

            # Approve
            resp = httpx.post(
                f"{base_url}/v1/mesh/tools/{tool_id}/approve",
                json={"justification": "Demo tool auto-approved"},
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 200:
                print(f"  Approved tool '{name}'")

        # Ensure assignment
        agent_name = tool_def["assign_to"]
        resp = httpx.post(
            f"{base_url}/v1/mesh/tool-assignments",
            json={"tool_id": tool_id if not existing else existing["id"], "agent_name": agent_name},
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            print(f"  Assigned '{name}' -> '{agent_name}'")
        elif resp.status_code == 409:
            print(f"  Assignment '{name}' -> '{agent_name}' already exists")
        else:
            print(f"  Assignment failed: {resp.status_code} {resp.text[:100]}")


def generate_trace(traffic_mix: str = "normal") -> list[dict]:
    """Generate a multi-hop trace (list of related audit records sharing a task_id)."""
    template = random.choice(TRACE_TEMPLATES)
    task_id = str(uuid.uuid4())
    records = []
    now = datetime.now(timezone.utc)
    prev_hash = None
    seq = 0

    for i, (src, dst) in enumerate(template):
        # Determine outcome
        if traffic_mix == "error_burst" and random.random() < 0.4:
            decision, outcome = "allow", "error"
        elif traffic_mix == "violation" and random.random() < 0.3:
            decision, outcome = "block", "blocked"
        else:
            r = random.random()
            if r < 0.02:
                decision, outcome = "block", "blocked"
            elif r < 0.06:
                decision, outcome = "allow", "error"
            else:
                decision, outcome = "allow", "success"

        model = random.choice(MODELS)
        input_tokens = random.randint(100, 3000)
        output_tokens = random.randint(50, 2000)
        cost_in, cost_out = COST_PER_TOKEN.get(model, (0.000003, 0.000015))
        latency = round(random.lognormvariate(4.5, 0.8), 1)

        msg_hash = hashlib.sha256(f"{task_id}-{i}-{uuid.uuid4()}".encode()).hexdigest()[:16]

        details = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model_name": model,
            "estimated_cost_usd": round(input_tokens * cost_in + output_tokens * cost_out, 8),
            "latency_ms": latency,
        }

        # Add CoT analysis to ~30% of hops
        if random.random() < 0.3:
            cot = random.choice(COT_REASONING_TEMPLATES).copy()
            # Occasionally add flags
            if cot["risk_level"] in ("medium", "high"):
                cot["flags"] = random.sample(COT_FLAGS, k=random.randint(1, 3))
            else:
                cot["flags"] = []
            details["cot_analysis"] = cot

        record = {
            "timestamp": (now + __import__("datetime").timedelta(milliseconds=i * int(latency))).isoformat(),
            "source_agent_name": src,
            "dest_agent_name": dst,
            "task_id": task_id,
            "a2a_method": random.choice(A2A_METHODS),
            "message_hash": msg_hash,
            "direction": "outbound",
            "decision": decision,
            "outcome": outcome,
            "sidecar_id": f"sidecar-{src.lower().replace(' ', '-')}",
            "details": details,
        }

        # Hash chain
        record_content = json.dumps({"msg": msg_hash, "prev": prev_hash}, sort_keys=True)
        record_hash = hashlib.sha256(record_content.encode()).hexdigest()[:16]
        record["record_hash"] = record_hash
        if prev_hash:
            record["previous_record_hash"] = prev_hash
        record["sequence_number"] = seq
        prev_hash = record_hash
        seq += 1

        records.append(record)

        # After each A2A hop, maybe add a tool call from the destination agent
        if dst in AGENT_TOOL_CALLS and random.random() < 0.6:
            tool_name = random.choice(AGENT_TOOL_CALLS[dst])
            tool_latency = round(random.lognormvariate(3.5, 0.6), 1)
            tool_outcome = "success" if random.random() < 0.92 else "error"

            tool_hash = hashlib.sha256(f"{task_id}-tool-{i}-{uuid.uuid4()}".encode()).hexdigest()[:16]
            tool_record = {
                "timestamp": (now + __import__("datetime").timedelta(milliseconds=i * int(latency) + int(tool_latency))).isoformat(),
                "source_agent_name": dst,
                "dest_agent_name": tool_name,
                "task_id": task_id,
                "a2a_method": "tools/call",
                "message_hash": tool_hash,
                "direction": "outbound",
                "decision": "allow",
                "outcome": tool_outcome,
                "sidecar_id": f"sidecar-{dst.lower().replace(' ', '-')}",
                "details": {
                    "tool_name": tool_name,
                    "latency_ms": tool_latency,
                    "input_tokens": random.randint(50, 500),
                    "output_tokens": random.randint(20, 300),
                },
            }

            tool_content = json.dumps({"msg": tool_hash, "prev": prev_hash}, sort_keys=True)
            tool_rec_hash = hashlib.sha256(tool_content.encode()).hexdigest()[:16]
            tool_record["record_hash"] = tool_rec_hash
            tool_record["previous_record_hash"] = prev_hash
            tool_record["sequence_number"] = seq
            prev_hash = tool_rec_hash
            seq += 1

            records.append(tool_record)

    return records


def generate_guardrail_events(guardrail_pool: list[dict], is_attack: bool = False) -> list[dict]:
    """Generate guardrail events."""
    events = []
    count = random.randint(1, 3)
    for _ in range(count):
        g = random.choice(guardrail_pool)
        agent = random.choice(ALL_AGENTS)

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
            "guardrail_type": g.get("type", "pre_processing"),
            "mechanism": g.get("mechanism", "regex"),
            "agent_name": agent,
            "sidecar_id": f"sidecar-{agent.lower().replace(' ', '-')}",
            "action": action,
            "reasoning": "Attack pattern detected" if action == "block" else "Checks passed",
            "latency_ms": round(random.lognormvariate(
                {"regex": 1.5, "vector_lookup": 3.0, "llm_judge": 5.5, "ml_classifier": 2.5}.get(
                    g.get("mechanism", "regex"), 2.0
                ), 0.5,
            ), 2),
            "matched_pattern": "Suspicious pattern" if action != "pass" else None,
            "input_hash": hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest(),
        }
        if "id" in g:
            event["guardrail_id"] = g["id"]
        events.append(event)
    return events


def fetch_guardrail_pool(base_url: str, headers: dict) -> list[dict]:
    """Fetch guardrail definitions from the API."""
    try:
        resp = httpx.get(f"{base_url}/v1/guardrails", headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            guardrails = data.get("guardrails", data) if isinstance(data, dict) else data
            pool = []
            for g in guardrails:
                if g.get("id"):
                    pool.append({
                        "id": str(g["id"]),
                        "name": g["name"],
                        "type": g.get("type", g.get("guardrail_type", "pre_processing")),
                        "mechanism": g.get("mechanism", "regex"),
                    })
            if pool:
                print(f"  Fetched {len(pool)} guardrails")
                return pool
    except Exception as e:
        print(f"  Could not fetch guardrails: {e}")

    return [
        {"name": "PII Detection", "type": "pre_processing", "mechanism": "regex"},
        {"name": "Prompt Injection Filter", "type": "pre_processing", "mechanism": "regex"},
        {"name": "Toxicity Check", "type": "post_processing", "mechanism": "vector_lookup"},
    ]


def main():
    parser = argparse.ArgumentParser(description="Topology demo traffic simulator")
    parser.add_argument("--registry-url", default=os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL))
    parser.add_argument("--username", default=os.environ.get("REGISTRY_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("REGISTRY_PASSWORD"))
    parser.add_argument("--mesh-api-key", default=os.environ.get("MESH_API_KEY", "mesh-dev-key"))
    parser.add_argument("--rps", type=float, default=2.0, help="Target traces per second")
    args = parser.parse_args()

    # Password fallback
    if not args.password:
        args.password = os.environ.get("ADMIN_PASSWORD", "admin")

    base_url = args.registry_url.rstrip("/")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"=== Topology Demo Simulator ===")
    print(f"Registry: {base_url}")
    print(f"Target: {args.rps} traces/sec\n")

    # Login
    print("1. Logging in...")
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

    # Seed agents and tools
    print("\n2. Ensuring agents exist...")
    ensure_agents(base_url, headers, mesh_headers)

    print("\n3. Ensuring tools exist...")
    ensure_tools(base_url, headers)

    print("\n4. Fetching guardrails...")
    guardrail_pool = fetch_guardrail_pool(base_url, headers)

    # Start traffic
    interval = 1.0 / max(args.rps, 0.1)
    total_records = 0
    total_traces = 0
    start_time = time.monotonic()
    cycle = 0

    print(f"\n5. Streaming traffic (interval={interval:.2f}s)... Press Ctrl+C to stop.\n")

    while running:
        cycle += 1

        # Traffic mix
        r = random.random()
        if r < 0.05:
            mix = "error_burst"
        elif r < 0.12:
            mix = "violation"
        else:
            mix = "normal"

        is_attack = cycle % 40 == 0

        # Generate and send a multi-hop trace
        trace_records = generate_trace(traffic_mix=mix)
        try:
            resp = httpx.post(
                f"{base_url}/v1/mesh/audit",
                json={"records": trace_records},
                headers=mesh_headers,
                timeout=15.0,
            )
            if resp.status_code in (201, 202):
                total_records += len(trace_records)
                total_traces += 1
            else:
                print(f"  Audit POST failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"  Audit error: {e}")

        # Guardrail events (every 3 cycles)
        if cycle % 3 == 0:
            events = generate_guardrail_events(guardrail_pool, is_attack=is_attack)
            try:
                resp = httpx.post(
                    f"{base_url}/v1/mesh/guardrail-events",
                    json={"events": events},
                    headers=mesh_headers,
                    timeout=10.0,
                )
                if resp.status_code in (201, 202):
                    total_records += len(events)
            except Exception as e:
                print(f"  Guardrail error: {e}")

        elapsed = time.monotonic() - start_time
        rate = total_records / elapsed if elapsed > 0 else 0

        if cycle % 20 == 0:
            print(f"  [{cycle}] {total_traces} traces, {total_records} records ({rate:.1f}/s) [{mix}]")

        time.sleep(interval)

    elapsed = time.monotonic() - start_time
    print(f"\nDone. {total_traces} traces, {total_records} records in {elapsed:.0f}s ({total_records / elapsed:.1f}/s)")


if __name__ == "__main__":
    main()
