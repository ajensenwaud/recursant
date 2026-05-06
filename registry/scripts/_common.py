"""Shared helpers for seed/wipe scripts that talk to the API via HTTP."""

import os
import sys

import requests

# ---------------------------------------------------------------------------
# .env loader (no external dependencies)
# ---------------------------------------------------------------------------

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_auth_headers(api_url: str) -> dict:
    """Log in as admin and return headers with JWT token."""
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD', 'admin')
    resp = requests.post(f"{api_url}/v1/auth/login", json={
        "username": username,
        "password": password,
    })
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    token = resp.json()["token"]
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "default",
    }
