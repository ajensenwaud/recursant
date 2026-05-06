#!/usr/bin/env python3
"""Mesh simulation script for validating the visualiser (V12).

Runs in an infinite loop, randomly:
- Adding/removing agents across simulated hosts
- Registering/deregistering sidecars
- Generating allowed and blocked audit events between random agent pairs
- Creating/deleting policies

Usage:
    python scripts/simulate_mesh.py
    python scripts/simulate_mesh.py --max-agents 50 --hosts 8 --interval 3
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            _key, _val = _key.strip(), _val.strip()
            if _val:
                os.environ.setdefault(_key, _val)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://127.0.0.1:5000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
MESH_API_KEY = os.environ.get("MESH_API_KEY", "mesh-dev-key")
PROJECT_ROOT = os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent))

AGENT_NOUNS = [
    "planner", "analyst", "researcher", "checker", "validator",
    "reviewer", "writer", "compiler", "dispatcher", "monitor",
    "scanner", "resolver", "reporter", "inspector", "evaluator",
    "synthesiser", "classifier", "extractor", "summariser", "optimizer",
]

SKILLS = [
    "research", "fact-check", "analysis", "planning", "reporting",
    "validation", "classification", "extraction", "synthesis", "optimization",
]

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def admin_login() -> str:
    resp = requests.post(
        f"{REGISTRY_URL}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["token"]


def auth_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
    }


def mesh_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }

# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------

def create_agent(token: str, name: str, skill: str, host: str) -> str | None:
    """Create an agent in the registry. Returns agent UUID or None."""
    payload = {
        "name": name,
        "description": f"Simulated agent ({skill}) on {host}",
        "version": "1.0.0",
        "owner_id": "mesh-simulator",
        "team_id": "mesh-simulator",
        "contact_email": "sim@recursant.ai",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [{"name": skill, "description": f"Skill: {skill}"}],
        "endpoint": {
            "type": "langgraph",
            "url": f"http://{host}:5010",
            "auth_method": "mtls",
        },
    }
    resp = requests.post(
        f"{REGISTRY_URL}/v1/agents",
        json=payload,
        headers=auth_headers(token),
        timeout=10,
    )
    if resp.status_code == 201:
        return resp.json()["id"]
    if resp.status_code == 409:
        # Already exists
        lookup = requests.get(
            f"{REGISTRY_URL}/v1/mesh/agents/lookup",
            params={"name": name},
            headers=mesh_headers(),
            timeout=10,
        )
        if lookup.status_code == 200:
            return lookup.json()["agent_id"]
    print(f"  Failed to create agent {name}: {resp.status_code}", file=sys.stderr)
    return None


def set_agent_approved(name: str) -> None:
    """Set agent to APPROVED via direct DB (bypasses governance pipeline)."""
    sql = (
        f"UPDATE agents SET status = 'APPROVED' "
        f"WHERE name = '{name}' AND tenant_id = 'default'"
    )
    subprocess.run(
        ["docker", "compose", "exec", "-T", "registry-db",
         "psql", "-U", "registry", "-d", "registry", "-c", sql],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )


def delete_agent(token: str, agent_id: str) -> None:
    """Soft-delete an agent."""
    requests.delete(
        f"{REGISTRY_URL}/v1/agents/{agent_id}",
        headers=auth_headers(token),
        timeout=10,
    )

# ---------------------------------------------------------------------------
# Mesh operations
# ---------------------------------------------------------------------------

def register_sidecar(agent_id: str, name: str, skill: str, host: str) -> bool:
    agent_card = {
        "name": name,
        "description": f"Simulated {skill} agent",
        "version": "1.0.0",
        "skills": [{"id": skill, "name": skill}],
        "default_input_modes": ["text"],
        "default_output_modes": ["text"],
        "capabilities": {"streaming": False},
        "endpoint": {"type": "langgraph", "url": f"http://{host}:5010"},
    }
    resp = requests.post(
        f"{REGISTRY_URL}/v1/mesh/register",
        json={
            "agent_id": agent_id,
            "sidecar_url": f"http://{host}:9901",
            "agent_card": agent_card,
        },
        headers=mesh_headers(),
        timeout=10,
    )
    return resp.status_code == 200


def deregister_sidecar(agent_id: str) -> None:
    requests.post(
        f"{REGISTRY_URL}/v1/mesh/deregister",
        json={"agent_id": agent_id},
        headers=mesh_headers(),
        timeout=10,
    )


def send_audit_event(
    src_name: str, dst_name: str, outcome: str = "allowed"
) -> None:
    """Submit a simulated audit event."""
    now = datetime.now(timezone.utc).isoformat()
    msg = f"{src_name}->{dst_name}@{now}"
    msg_hash = hashlib.sha256(msg.encode()).hexdigest()
    requests.post(
        f"{REGISTRY_URL}/v1/mesh/audit",
        json={
            "records": [{
                "timestamp": now,
                "source_agent_name": src_name,
                "dest_agent_name": dst_name,
                "a2a_method": "message/send",
                "message_hash": msg_hash,
                "direction": "outbound",
                "decision": "allow" if outcome == "allowed" else "block",
                "outcome": outcome,
                "task_id": str(uuid.uuid4()),
            }],
        },
        headers=mesh_headers(),
        timeout=10,
    )


def create_policy(src: str, dst: str, action: str = "block") -> str | None:
    resp = requests.post(
        f"{REGISTRY_URL}/v1/mesh/policies",
        json={
            "source_agent_name": src,
            "dest_agent_name": dst,
            "action": action,
            "priority": 100,
        },
        headers=mesh_headers(),
        timeout=10,
    )
    if resp.status_code == 201:
        return resp.json().get("id")
    return None


def delete_policy(policy_id: str) -> None:
    requests.delete(
        f"{REGISTRY_URL}/v1/mesh/policies/{policy_id}",
        headers=mesh_headers(),
        timeout=10,
    )

# ---------------------------------------------------------------------------
# Simulation loop
# ---------------------------------------------------------------------------

class SimState:
    def __init__(self, hosts: list[str], max_agents: int):
        self.hosts = hosts
        self.max_agents = max_agents
        self.agents: dict[str, dict] = {}  # name -> {id, host, skill}
        self.policies: dict[str, dict] = {}  # policy_id -> {src, dst}
        self.token = admin_login()

    def random_name(self) -> str:
        noun = random.choice(AGENT_NOUNS)
        suffix = random.randint(1000, 9999)
        return f"sim-agent-{noun}-{suffix}"

    def add_agent(self) -> None:
        if len(self.agents) >= self.max_agents:
            return
        name = self.random_name()
        skill = random.choice(SKILLS)
        host = random.choice(self.hosts)
        agent_id = create_agent(self.token, name, skill, host)
        if not agent_id:
            return
        set_agent_approved(name)
        ok = register_sidecar(agent_id, name, skill, host)
        if ok:
            self.agents[name] = {"id": agent_id, "host": host, "skill": skill}
            print(f"  + Agent {name} on {host} ({skill})")
        else:
            print(f"  ! Failed to register sidecar for {name}")

    def remove_agent(self) -> None:
        if len(self.agents) < 3:
            return
        name = random.choice(list(self.agents.keys()))
        info = self.agents.pop(name)
        deregister_sidecar(info["id"])
        delete_agent(self.token, info["id"])
        print(f"  - Agent {name} removed")

    def send_message(self, blocked: bool = False) -> None:
        if len(self.agents) < 2:
            return
        names = list(self.agents.keys())
        src = random.choice(names)
        dst = random.choice([n for n in names if n != src])
        # For blocked messages, pick agents on different hosts
        if blocked:
            src_host = self.agents[src]["host"]
            cross_host = [n for n in names if n != src and self.agents[n]["host"] != src_host]
            if cross_host:
                dst = random.choice(cross_host)
        outcome = "blocked" if blocked else "allowed"
        send_audit_event(src, dst, outcome)
        print(f"  {'X' if blocked else '>'} {src} -> {dst} ({outcome})")

    def manage_policy(self) -> None:
        if len(self.agents) < 2:
            return
        # Sometimes create, sometimes delete
        if self.policies and random.random() < 0.4:
            pid = random.choice(list(self.policies.keys()))
            info = self.policies.pop(pid)
            delete_policy(pid)
            print(f"  ~ Removed policy: {info['src']} -> {info['dst']} block")
        else:
            names = list(self.agents.keys())
            src = random.choice(names)
            dst = random.choice([n for n in names if n != src])
            pid = create_policy(src, dst, "block")
            if pid:
                self.policies[pid] = {"src": src, "dst": dst}
                print(f"  ~ Created policy: {src} -> {dst} block")

    def cleanup(self) -> None:
        print("\nCleaning up simulation agents...")
        for name, info in list(self.agents.items()):
            deregister_sidecar(info["id"])
            delete_agent(self.token, info["id"])
            print(f"  - Cleaned up {name}")
        for pid in list(self.policies.keys()):
            delete_policy(pid)
        self.agents.clear()
        self.policies.clear()
        print("Cleanup complete.")


def main():
    parser = argparse.ArgumentParser(description="Simulate mesh activity for visualiser testing")
    parser.add_argument("--interval", type=float, default=2.0, help="Base tick interval in seconds")
    parser.add_argument("--max-agents", type=int, default=25, help="Maximum agents in the pool")
    parser.add_argument("--hosts", type=int, default=5, help="Number of simulated hosts")
    args = parser.parse_args()

    host_names = [
        "sim-host-alpha.internal",
        "sim-host-beta.internal",
        "sim-host-gamma.internal",
        "sim-host-delta.internal",
        "sim-host-epsilon.internal",
        "sim-host-zeta.internal",
        "sim-host-eta.internal",
        "sim-host-theta.internal",
    ][:args.hosts]

    print(f"Mesh Simulator starting")
    print(f"  Registry: {REGISTRY_URL}")
    print(f"  Max agents: {args.max_agents}")
    print(f"  Hosts: {', '.join(host_names)}")
    print(f"  Interval: {args.interval}s")
    print()

    state = SimState(host_names, args.max_agents)

    # Handle Ctrl+C
    def on_signal(sig, frame):
        state.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    tick = 0
    try:
        while True:
            tick += 1
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] Tick {tick} ({len(state.agents)} agents, {len(state.policies)} policies)")

            # Ramp up: add agents faster during first 30 ticks
            if tick <= 30 and len(state.agents) < args.max_agents:
                state.add_agent()
                if random.random() < 0.5:
                    state.add_agent()

            # Steady state actions
            r = random.random()
            if r < 0.15 and len(state.agents) < args.max_agents:
                state.add_agent()
            elif r < 0.20:
                state.remove_agent()

            # Send messages (most frequent action)
            msg_count = random.randint(1, 3)
            for _ in range(msg_count):
                blocked = random.random() < 0.15
                state.send_message(blocked=blocked)

            # Occasionally manage policies
            if random.random() < 0.1:
                state.manage_policy()

            time.sleep(args.interval + random.uniform(-0.5, 0.5))

    except KeyboardInterrupt:
        state.cleanup()


if __name__ == "__main__":
    main()
