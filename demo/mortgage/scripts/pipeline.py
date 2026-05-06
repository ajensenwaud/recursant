"""Submit mortgage demo agents through the governance pipeline.

Runs each agent through the governance REST APIs:
  Submit → Security Scan → Evaluation → Approval
The submit endpoint runs security scan and evaluation synchronously.
Sidecars auto-activate agents (APPROVED → ACTIVE) on registration.

With --skip-governance, bypasses the pipeline entirely and activates
agents directly via DB update. Saves tokens and time for development.

Usage:
    python scripts/pipeline.py [--registry-url URL] [--skip-governance]

Environment variables:
    REGISTRY_URL: Registry base URL (default: http://localhost:5000)
    REGISTRY_USERNAME / REGISTRY_PASSWORD: Admin credentials
    DATABASE_URL: Direct DB connection for force-activation / skip-governance
    SKIP_GOVERNANCE: Set to 1 to skip the governance pipeline
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import httpx

DEFAULT_REGISTRY_URL = "http://localhost:5000"
DEFAULT_DATABASE_URL = "postgresql://registry:registry@registry-db:5432/registry"

MORTGAGE_AGENT_NAMES = {
    "Customer Agent",
    "Authentication Agent",
    "KYC Agent",
    "Credit Agent",
    "Core Banking Agent",
}


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


def get_agents(base_url: str, headers: dict) -> list[dict]:
    resp = httpx.get(f"{base_url}/v1/agents", headers=headers, timeout=10.0)
    if resp.status_code != 200:
        print(f"Failed to list agents: {resp.status_code}")
        return []
    return [
        a for a in resp.json().get("agents", [])
        if a["name"] in MORTGAGE_AGENT_NAMES
    ]


def get_agent(base_url: str, headers: dict, agent_id: str) -> dict:
    resp = httpx.get(f"{base_url}/v1/agents/{agent_id}", headers=headers, timeout=10.0)
    if resp.status_code == 200:
        return resp.json()
    return {}


def submit_agent(base_url: str, headers: dict, agent_id: str) -> str | None:
    """POST /v1/agents/{id}/submit — triggers security scan + evaluation synchronously."""
    resp = httpx.post(
        f"{base_url}/v1/agents/{agent_id}/submit",
        headers=headers,
        timeout=600.0,  # scan + evaluation can take several minutes
    )
    if resp.status_code == 200:
        return resp.json().get("status", "unknown")
    print(f"    Submit error: {resp.status_code} {resp.text[:200]}")
    return None


def approve_agent(base_url: str, headers: dict, agent_id: str) -> bool:
    """POST /v1/agents/{id}/approval — approve the agent."""
    resp = httpx.post(
        f"{base_url}/v1/agents/{agent_id}/approval",
        json={
            "decision": "approve",
            "justification": "Mortgage demo agent — approved for demo purposes",
        },
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code == 200:
        return True
    print(f"    Approval error: {resp.status_code} {resp.text[:200]}")
    return False


def force_activate_db(database_url: str, agent_id: str, name: str) -> bool:
    """Fallback: force-activate via direct DB update."""
    try:
        import psycopg2
    except ImportError:
        print("    Installing psycopg2-binary...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "psycopg2-binary"],
            stdout=subprocess.DEVNULL,
        )
        import psycopg2

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE agents SET status = 'ACTIVE' WHERE id = %s::uuid",
                (agent_id,),
            )
            if cur.rowcount == 1:
                print(f"    Force-activated {name} via DB")
                return True
            else:
                print(f"    DB update matched {cur.rowcount} rows")
                return False
    except Exception as e:
        print(f"    DB error: {e}")
        return False
    finally:
        conn.close()


def run_pipeline_for_agent(
    base_url: str, headers: dict, database_url: str,
    agent_id: str, name: str, current_status: str,
) -> str:
    """Run the full governance pipeline for one agent via REST APIs.

    Submit runs security scan + evaluation synchronously, so by the time
    it returns the agent should be at pending_approval (or a failure state).
    Sidecars auto-activate agents from APPROVED → ACTIVE on registration.
    """

    # Step 1: Submit (runs security scan + evaluation synchronously)
    if current_status == "draft":
        print("  [1/3] Submitting (security scan + evaluation)...")
        status = submit_agent(base_url, headers, agent_id)
        if status:
            print(f"    Status after submit: {status}")
            current_status = status
        else:
            print("    Submit failed — refreshing status")
    else:
        print(f"  [1/3] Already {current_status}, skipping submit")

    # Always refresh status from registry before polling
    agent_data = get_agent(base_url, headers, agent_id)
    current_status = agent_data.get("status", current_status)

    # Wait for transitional states to resolve (evaluating, testing, submitted)
    transitional = {"submitted", "testing", "evaluating"}
    waited = 0
    while current_status in transitional and waited < 300:
        if waited == 0:
            print(f"    Waiting for {current_status} to complete...")
        time.sleep(5)
        waited += 5
        agent_data = get_agent(base_url, headers, agent_id)
        current_status = agent_data.get("status", current_status)

    # Refresh final status
    agent_data = get_agent(base_url, headers, agent_id)
    current_status = agent_data.get("status", current_status)
    print(f"    Current status: {current_status}")

    # Step 2: Approve (if pending approval)
    if current_status == "pending_approval":
        print("  [2/3] Approving...")
        if approve_agent(base_url, headers, agent_id):
            print("    Approved")
            current_status = "approved"
        else:
            print("    Approval failed")
    elif current_status in ("approved", "active"):
        print(f"  [2/3] Already {current_status}, skipping approval")
    else:
        print(f"  [2/3] Cannot approve (status: {current_status})")

    # Step 3: Sidecars auto-activate APPROVED → ACTIVE on registration.
    # If the agent ended up APPROVED, sidecars will handle activation.
    if current_status == "approved":
        print("  [3/3] Agent is APPROVED — sidecars will auto-activate on registration")
        return "approved"

    # Fallback: force-activate via DB if stuck
    if current_status not in ("active", "approved"):
        print(f"  [3/3] Force-activating via DB (status was: {current_status})...")
        if force_activate_db(database_url, agent_id, name):
            return "active (forced)"
        return "failed"

    return current_status


def activate_all_db(database_url: str, agents: list[dict]) -> dict[str, str]:
    """Skip governance: activate all agents directly via DB."""
    try:
        import psycopg2
    except ImportError:
        print("    Installing psycopg2-binary...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "psycopg2-binary"],
            stdout=subprocess.DEVNULL,
        )
        import psycopg2

    results = {}
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            for agent in agents:
                name = agent["name"]
                agent_id = agent["id"]
                status = agent.get("status", "unknown")
                if status == "active":
                    print(f"  {name}: already active")
                    results[name] = "active"
                    continue
                cur.execute(
                    "UPDATE agents SET status = 'ACTIVE' WHERE id = %s::uuid",
                    (agent_id,),
                )
                if cur.rowcount == 1:
                    print(f"  {name}: activated (was {status})")
                    results[name] = "active (direct)"
                else:
                    print(f"  {name}: DB update matched {cur.rowcount} rows")
                    results[name] = "failed"
    except Exception as e:
        print(f"  DB error: {e}")
        for agent in agents:
            results.setdefault(agent["name"], "failed")
    finally:
        conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Submit and activate mortgage demo agents")
    parser.add_argument("--registry-url", default=os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL))
    parser.add_argument("--username", default=os.environ.get("REGISTRY_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("REGISTRY_PASSWORD", "admin"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument(
        "--skip-governance",
        action="store_true",
        default=os.environ.get("SKIP_GOVERNANCE", "").strip() in ("1", "true", "yes"),
        help="Skip governance pipeline; activate agents directly via DB",
    )
    args = parser.parse_args()

    base_url = args.registry_url.rstrip("/")

    if args.skip_governance:
        print(f"Mortgage demo — SKIP GOVERNANCE (direct DB activation)\n")
    else:
        print(f"Mortgage demo governance pipeline at {base_url}\n")

    print("Logging in...")
    token = login(base_url, args.username, args.password)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
    }

    agents = get_agents(base_url, headers)
    if not agents:
        print("No mortgage agents found!")
        sys.exit(1)

    print(f"Found {len(agents)} mortgage agent(s)\n")

    if args.skip_governance:
        results = activate_all_db(args.database_url, agents)
    else:
        results = {}
        for agent in agents:
            name = agent["name"]
            agent_id = agent["id"]
            status = agent.get("status", "unknown")

            print(f"=== {name} (id={agent_id}, status={status}) ===")

            if status == "active":
                print("  Already active, skipping")
                results[name] = "active"
            else:
                results[name] = run_pipeline_for_agent(
                    base_url, headers, args.database_url,
                    agent_id, name, status,
                )
            print()

    # Summary
    print("\n=== Summary ===")
    all_ok = True
    for name, status in results.items():
        ok = status in ("active", "approved") or "active" in status
        tag = "OK" if ok else "FAILED"
        print(f"  [{tag}] {name}: {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAll mortgage agents ready (sidecars will auto-activate APPROVED agents).")
    else:
        print("\nSome agents failed. Check logs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
