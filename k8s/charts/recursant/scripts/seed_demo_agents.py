"""Seed demo agents and mesh policies in the registry.

Creates two agents, submits them through the governance pipeline
(security scan + evaluation + approval), and creates mesh policies
so the sidecars can register and communicate.

Usage:
    python examples/seed_demo_agents.py [--registry-url URL] [--api-key KEY]

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    REGISTRY_API_KEY: Admin API key or JWT token
    MESH_API_KEY: API key for mesh endpoints
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import httpx

DEFAULT_REGISTRY_URL = "http://localhost:5000"


def get_auth_headers(args) -> dict[str, str]:
    """Build auth headers for registry requests."""
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
    }
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    return headers


def get_mesh_headers(args) -> dict[str, str]:
    """Build auth headers for mesh API requests."""
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
    }
    if args.mesh_api_key:
        headers["X-Mesh-API-Key"] = args.mesh_api_key
    return headers


def login(base_url: str, username: str, password: str) -> str:
    """Login to the registry and return a JWT token."""
    resp = httpx.post(
        f"{base_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["token"]


def create_agent(base_url: str, headers: dict, agent_data: dict) -> dict:
    """Create an agent in the registry, or return existing if duplicate."""
    resp = httpx.post(
        f"{base_url}/v1/agents",
        json=agent_data,
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code == 201:
        agent = resp.json()
        print(f"  Created agent: {agent['name']} (id={agent['id']})")
        return agent
    elif resp.status_code == 409:
        # Duplicate — find existing
        print(f"  Agent '{agent_data['name']}' already exists, finding...")
        list_resp = httpx.get(
            f"{base_url}/v1/agents",
            headers=headers,
            timeout=10.0,
        )
        for a in list_resp.json().get("agents", []):
            if a["name"] == agent_data["name"]:
                print(f"  Found existing agent: {a['name']} (id={a['id']})")
                return a
        print(f"  ERROR: Could not find existing agent")
        return {}
    else:
        print(f"  ERROR creating agent: {resp.status_code} {resp.text}")
        return {}




def create_mesh_policy(base_url: str, headers: dict, policy: dict) -> None:
    """Create a mesh authorisation policy."""
    resp = httpx.post(
        f"{base_url}/v1/mesh/policies",
        json=policy,
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code == 201:
        print(f"  Created policy: {policy['source_agent_name']} -> {policy['dest_agent_name']}: {policy['action']}")
    else:
        print(f"  Policy creation: {resp.status_code} {resp.text}")


def main():
    parser = argparse.ArgumentParser(description="Seed demo agents for Recursant Mesh")
    parser.add_argument("--registry-url", default=os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL))
    parser.add_argument("--token", default=os.environ.get("REGISTRY_TOKEN"))
    parser.add_argument("--username", default=os.environ.get("REGISTRY_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("REGISTRY_PASSWORD", "admin"))
    parser.add_argument("--mesh-api-key", default=os.environ.get("MESH_API_KEY"))
    args = parser.parse_args()

    base_url = args.registry_url.rstrip("/")
    print(f"Seeding demo agents at {base_url}")

    # Login if no token provided
    if not args.token:
        print("Logging in...")
        try:
            args.token = login(base_url, args.username, args.password)
        except Exception as e:
            print(f"Login failed: {e}")
            print("Continuing without auth (may fail if registry requires it)")

    headers = get_auth_headers(args)

    # ---------------------------------------------------------------
    # Create Agent A: Research Assistant
    # ---------------------------------------------------------------
    print("\n--- Agent A: Research Assistant ---")
    agent_a = create_agent(base_url, headers, {
        "name": "Research Assistant",
        "description": "Produces research claims and coordinates fact-checking with other agents",
        "version": "1.0.0",
        "owner_id": "mesh-demo",
        "team_id": "mesh-demo",
        "contact_email": "demo@recursant.ai",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {
                "name": "research",
                "description": "Generates research claims about a given topic",
            },
            {
                "name": "research-and-verify",
                "description": "Generates a claim and coordinates fact-checking via a remote agent",
            },
        ],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agent-a:5010/a2a",
            "auth_method": "mtls",
        },
    })

    mesh_headers = get_mesh_headers(args)

    # ---------------------------------------------------------------
    # Create Agent B: Fact Checker
    # ---------------------------------------------------------------
    print("\n--- Agent B: Fact Checker ---")
    agent_b = create_agent(base_url, headers, {
        "name": "Fact Checker Agent",
        "description": "Verifies factual claims using multiple sources and returns evidence",
        "version": "1.0.0",
        "owner_id": "mesh-demo",
        "team_id": "mesh-demo",
        "contact_email": "demo@recursant.ai",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [
            {
                "name": "fact-check",
                "description": "Verifies a factual claim and returns a verdict with evidence",
            },
        ],
        "endpoint": {
            "type": "langgraph",
            "url": "http://agent-b:5011/a2a",
            "auth_method": "mtls",
        },
    })

    # ---------------------------------------------------------------
    # Create mesh policies
    # ---------------------------------------------------------------
    print("\n--- Mesh Policies ---")

    # Allow Research Assistant to call Fact Checker
    create_mesh_policy(base_url, mesh_headers, {
        "source_agent_name": "Research Assistant",
        "dest_agent_name": "Fact Checker Agent",
        "action": "allow",
        "priority": 0,
    })

    # Allow Fact Checker to respond to Research Assistant
    create_mesh_policy(base_url, mesh_headers, {
        "source_agent_name": "Fact Checker Agent",
        "dest_agent_name": "Research Assistant",
        "action": "allow",
        "priority": 1,
    })

    # Default deny
    create_mesh_policy(base_url, mesh_headers, {
        "source_agent_name": "*",
        "dest_agent_name": "*",
        "action": "deny",
        "priority": 100,
    })

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n--- Summary ---")
    print(f"Agent A (Research Assistant): {agent_a.get('id', 'FAILED')} [DRAFT]")
    print(f"Agent B (Fact Checker):       {agent_b.get('id', 'FAILED')} [DRAFT]")
    print("Mesh policies: 3 created (allow A->B, allow B->A, default deny)")
    print("\nAgents created as DRAFT. The pipeline container will submit them")
    print("once the agent processes are healthy.")


if __name__ == "__main__":
    main()
