"""Shared fixtures and helpers for mesh integration tests.

All integration tests use the real registry (K8s or Docker Compose).
Common boilerplate (env loading, admin login, agent creation, DB status
bypass, mesh registration, policy management, Flask server helpers) lives
here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import yaml

# ---------------------------------------------------------------------------
# Load .env from project root (ADMIN_PASSWORD, API keys, etc.)
# ---------------------------------------------------------------------------
_env_file = Path(__file__).resolve().parents[3] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            _key, _val = _key.strip(), _val.strip()
            if _val:  # skip empty values to avoid poisoning defaults
                os.environ.setdefault(_key, _val)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REGISTRY_URL = os.environ.get(
    "K8S_REGISTRY_URL",
    os.environ.get("REGISTRY_URL", "http://127.0.0.1:5000"),
)
MESH_API_KEY = os.environ.get("MESH_API_KEY", "mesh-dev-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "/home/aj/recursant")

# ---------------------------------------------------------------------------
# K8s agent/sidecar URL constants
#
# Defaults are localhost with local ports (for Docker Compose or port-forward).
# Inside a K8s pod, set these env vars to K8s service DNS names.
# ---------------------------------------------------------------------------
AGENT_A_URL = os.environ.get("AGENT_A_URL", "http://127.0.0.1:5010")
AGENT_B_URL = os.environ.get("AGENT_B_URL", "http://127.0.0.1:5011")
SIDECAR_A_URL = os.environ.get("SIDECAR_A_URL", "http://127.0.0.1:9901")
SIDECAR_B_URL = os.environ.get("SIDECAR_B_URL", "http://127.0.0.1:9902")
SIDECAR_A_A2A_URL = os.environ.get("SIDECAR_A_A2A_URL", "https://127.0.0.1:8443")
SIDECAR_B_A2A_URL = os.environ.get("SIDECAR_B_A2A_URL", "https://127.0.0.1:8444")

# K8s DB access
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "recursant")
K8S_RELEASE = os.environ.get("K8S_RELEASE", "recursant")


# ---------------------------------------------------------------------------
# Registry availability
# ---------------------------------------------------------------------------

def registry_available() -> bool:
    """Return True if the real registry is reachable."""
    try:
        resp = httpx.get(f"{REGISTRY_URL}/health", timeout=3.0)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


# ---------------------------------------------------------------------------
# Service availability
# ---------------------------------------------------------------------------

def wait_for_service(url: str, timeout: float = 30.0, path: str = "/health") -> bool:
    """Poll a URL's health endpoint until it responds 200 or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{url}{path}", timeout=3.0, verify=False)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            pass
        time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def admin_login() -> str:
    """Login as admin and return a JWT token."""
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10.0,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


def mesh_headers() -> dict[str, str]:
    """Return headers for mesh API calls (API key + tenant)."""
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "X-Mesh-API-Key": MESH_API_KEY,
    }


def auth_headers(token: str) -> dict[str, str]:
    """Return headers for admin API calls (JWT + tenant)."""
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": "default",
        "Authorization": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# DB access — environment-aware
# ---------------------------------------------------------------------------

def _kubectl_has_db_pod() -> bool:
    """Check if the K8s DB pod exists."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pod", "-n", K8S_NAMESPACE,
             f"{K8S_RELEASE}-db-0", "--no-headers"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _exec_sql(sql: str) -> str:
    """Execute SQL against the registry DB.

    Three execution modes:
    1. If REGISTRY_DB_HOST is set (inside K8s pod): direct psycopg2 connection
    2. If kubectl is available with a DB pod: kubectl exec psql
    3. Fallback: docker compose exec psql
    """
    db_host = os.environ.get("REGISTRY_DB_HOST")

    if db_host:
        # Inside K8s pod — direct psycopg2
        import psycopg2
        conn = psycopg2.connect(
            host=db_host, dbname="registry",
            user="registry", password="registry",
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        conn.close()
        return ""

    if shutil.which("kubectl") and _kubectl_has_db_pod():
        # From host — kubectl exec
        result = subprocess.run(
            ["kubectl", "exec", "-n", K8S_NAMESPACE,
             f"{K8S_RELEASE}-db-0", "--",
             "psql", "-U", "registry", "-d", "registry", "-c", sql],
            capture_output=True, text=True, check=True, timeout=15,
        )
        return result.stdout

    # Docker Compose fallback
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "registry-db",
         "psql", "-U", "registry", "-d", "registry", "-c", sql],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"DB exec failed: {result.stderr}")
    return result.stdout


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------

def create_agent_in_registry(
    token: str,
    name: str,
    skill: str,
    desc: str,
    endpoint_url: str,
) -> str:
    """Create an agent in the registry. Returns the agent UUID.

    If the agent already exists (409), looks it up and updates its endpoint.
    """
    headers = auth_headers(token)
    payload = {
        "name": name,
        "description": desc,
        "version": "1.0.0",
        "owner_id": "integration-test",
        "team_id": "integration-test",
        "contact_email": "test@recursant.ai",
        "classification": "internal",
        "data_sensitivity": "none",
        "risk_tier": "low",
        "capabilities": [{"name": skill, "description": f"Skill: {skill}"}],
        "endpoint": {
            "type": "langgraph",
            "url": endpoint_url,
            "auth_method": "mtls",
        },
    }
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/agents", json=payload, headers=headers, timeout=10.0,
    )

    if resp.status_code == 201:
        return resp.json()["id"]

    if resp.status_code == 409:
        # Already exists -- look up by name, update endpoint
        lookup = httpx.get(
            f"{REGISTRY_URL}/v1/mesh/agents/lookup",
            params={"name": name},
            headers=mesh_headers(),
            timeout=10.0,
        )
        if lookup.status_code == 200:
            agent_id = lookup.json()["agent_id"]
            httpx.put(
                f"{REGISTRY_URL}/v1/agents/{agent_id}",
                json={"endpoint": {"type": "langgraph", "url": endpoint_url, "auth_method": "mtls"}},
                headers=headers,
                timeout=10.0,
            )
            return agent_id

    raise RuntimeError(f"Failed to create agent '{name}': {resp.status_code} {resp.text}")


def set_agent_status(agent_name: str, status: str) -> None:
    """Set an agent's status directly in the DB (bypasses governance pipeline)."""
    sql = (
        f"UPDATE agents SET status = '{status}' "
        f"WHERE name = '{agent_name}' AND tenant_id = 'default'"
    )
    try:
        _exec_sql(sql)
    except Exception as exc:
        raise RuntimeError(f"DB update failed for '{agent_name}': {exc}") from exc


def set_agents_approved(agent_names: list[str]) -> None:
    """Set multiple agents to APPROVED status via direct DB update."""
    names_csv = ", ".join(f"'{n}'" for n in agent_names)
    sql = (
        f"UPDATE agents SET status = 'APPROVED' "
        f"WHERE name IN ({names_csv}) AND tenant_id = 'default' "
        f"AND status NOT IN ('APPROVED', 'ACTIVE')"
    )
    try:
        _exec_sql(sql)
    except Exception as exc:
        raise RuntimeError(f"DB update failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Mesh registration
# ---------------------------------------------------------------------------

def register_sidecar(agent_id: str, sidecar_port: int, agent_card: dict) -> httpx.Response:
    """Register a sidecar with the registry via the mesh API."""
    return httpx.post(
        f"{REGISTRY_URL}/v1/mesh/register",
        json={
            "agent_id": agent_id,
            "sidecar_url": f"http://127.0.0.1:{sidecar_port}",
            "agent_card": agent_card,
        },
        headers=mesh_headers(),
        timeout=10.0,
    )


def deregister_sidecar(agent_id: str) -> None:
    """Deregister a sidecar from the registry (best-effort)."""
    try:
        httpx.post(
            f"{REGISTRY_URL}/v1/mesh/deregister",
            json={"agent_id": agent_id},
            headers=mesh_headers(),
            timeout=10.0,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Policy management
# ---------------------------------------------------------------------------

def create_mesh_policy(
    source: str, dest: str, action: str, priority: int,
) -> str | None:
    """Create a mesh policy in the registry. Returns policy ID or None."""
    resp = httpx.post(
        f"{REGISTRY_URL}/v1/mesh/policies",
        json={
            "source_agent_name": source,
            "dest_agent_name": dest,
            "action": action,
            "priority": priority,
        },
        headers=mesh_headers(),
        timeout=10.0,
    )
    if resp.status_code == 201:
        return resp.json().get("id")
    return None


def delete_mesh_policy(policy_id: str) -> None:
    """Delete a mesh policy (best-effort)."""
    try:
        httpx.delete(
            f"{REGISTRY_URL}/v1/mesh/policies/{policy_id}",
            headers=mesh_headers(),
            timeout=10.0,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Agent card YAML
# ---------------------------------------------------------------------------

def create_agent_card_yaml(name: str, skill_id: str, description: str) -> str:
    """Write a temporary agent card YAML file. Returns the file path."""
    card = {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "skills": [{"id": skill_id, "name": skill_id, "description": f"Skill: {skill_id}"}],
        "default_input_modes": ["text"],
        "default_output_modes": ["text"],
        "capabilities": {"streaming": False, "push_notifications": False},
    }
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix=f"card-{name}-")
    with os.fdopen(fd, "w") as f:
        yaml.dump(card, f)
    return path


# ---------------------------------------------------------------------------
# Flask server helpers
# ---------------------------------------------------------------------------

def start_flask_app(app, port: int) -> threading.Thread:
    """Start a Flask app on a background daemon thread."""
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
        daemon=True,
    )
    thread.start()
    return thread


def wait_for_port(port: int, timeout: float = 5.0) -> None:
    """Wait until a TCP port is accepting connections on localhost."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=1.0) as c:
                c.get(f"http://127.0.0.1:{port}/healthz")
                return
        except (httpx.ConnectError, httpx.ReadError):
            time.sleep(0.1)
    raise RuntimeError(f"Port {port} did not become ready within {timeout}s")
