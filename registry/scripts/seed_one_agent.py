#!/usr/bin/env python3
"""
Seed script to create and submit a single agent via the API.

Cheaper alternative to seed_agents.py (which creates 10). Useful for
testing the full pipeline: DRAFT -> SUBMITTED -> TESTING -> EVALUATING
-> PENDING_APPROVAL without burning through many LLM calls.

Usage:
    python scripts/seed_one_agent.py
    python scripts/seed_one_agent.py --api-url http://localhost:5000
    python scripts/seed_one_agent.py --agent-url http://test-agent:5001/invoke
"""

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_auth_headers

AGENT = {
    "name": "knowledge-base-search-agent",
    "version": "1.2.0",
    "description": "Semantic search over the company knowledge base for internal support and onboarding.",
    "owner_id": "svc-knowledge",
    "team_id": "engineering-platform",
    "contact_email": "platform@recursant.io",
    "classification": "internal",
    "data_sensitivity": "none",
    "risk_tier": "low",
    "capabilities": [
        {"name": "kb-search", "description": "Search the knowledge base using natural language queries"},
        {"name": "article-summary", "description": "Summarise a knowledge base article"},
    ],
}


def seed_one_agent(api_url: str, agent_url: str) -> None:
    headers = get_auth_headers(api_url)

    payload = {
        **AGENT,
        "endpoint": {
            "type": "langgraph",
            "url": agent_url,
            "auth_method": "api_key",
            "timeout_ms": 60000,
            "agent_protocol": "A2A",
        },
    }

    # Create
    resp = requests.post(f"{api_url}/v1/agents", headers=headers, json=payload)
    if resp.status_code != 201:
        print(f"FAILED to create agent: {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    agent = resp.json()
    agent_id = agent["id"]
    print(f"Created: {agent['name']} (id={agent_id})")

    # Submit (triggers security scan + evaluation pipeline)
    print(f"Submitting (runs security scan + evaluation, may take ~4 min)...")
    try:
        submit_resp = requests.post(
            f"{api_url}/v1/agents/{agent_id}/submit", headers=headers,
            timeout=300
        )
        if submit_resp.status_code == 200:
            result = submit_resp.json()
            print(f"Done -> status: {result.get('status', 'unknown')}")
        else:
            print(f"Submit failed: {submit_resp.status_code}: {submit_resp.text}", file=sys.stderr)
            sys.exit(1)
    except requests.exceptions.Timeout:
        print("Submit timed out (pipeline may still be running in background)")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a single agent submission")
    parser.add_argument("--api-url", default="http://localhost:5000", help="Registry API base URL")
    parser.add_argument("--agent-url", default="http://test-agent:5001/invoke", help="Test agent invoke endpoint")
    args = parser.parse_args()

    print(f"API: {args.api_url}")
    print(f"Agent endpoint: {args.agent_url}\n")
    seed_one_agent(args.api_url, args.agent_url)
