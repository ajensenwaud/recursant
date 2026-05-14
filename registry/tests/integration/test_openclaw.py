"""Integration tests for the OpenClaw API.

Run via:
    make k8s-test-openclaw
    (or)
    kubectl exec -n recursant deploy/recursant-registry -c registry -- \
        python -m pytest tests/integration/test_openclaw.py -v -m integration

These tests make real HTTP calls to the running gunicorn on localhost:5000
(no Flask test_client, no mocks). Each test enrolls a fresh instance with a
unique machine_id so cleanup is contained to revoke / soft-delete.
"""
import os
import secrets
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("OPENCLAW_TEST_BASE_URL", "http://localhost:5000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_token() -> str:
    if not ADMIN_PASSWORD:
        pytest.skip("ADMIN_PASSWORD env var not set")
    r = httpx.post(
        f"{BASE_URL}/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def tenant_id() -> str:
    # Unique tenant per test so admin-list assertions are deterministic
    return f"test-{secrets.token_hex(4)}"


@pytest.fixture
def machine_id() -> str:
    return f"test-machine-{secrets.token_hex(6)}"


@pytest.fixture
def admin_headers(admin_token: str, tenant_id: str) -> dict:
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-Tenant-ID": tenant_id,
        "Content-Type": "application/json",
    }


def _issue_token(admin_headers: dict, tenant_id: str, ttl: int = 600) -> str:
    r = httpx.post(
        f"{BASE_URL}/v1/openclaw/enrollment-tokens",
        headers=admin_headers,
        json={"tenant_id": tenant_id, "ttl_seconds": ttl},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["token"]


def _enroll(
    token: str,
    tenant_id: str,
    machine_id: str,
    fingerprint: dict | None = None,
) -> dict:
    r = httpx.post(
        f"{BASE_URL}/v1/openclaw/instances/enroll",
        headers={"X-Tenant-ID": tenant_id, "Content-Type": "application/json"},
        json={
            "enrollment_token": token,
            "tenant_id": tenant_id,
            "machine_id": machine_id,
            "instance_fingerprint": fingerprint or {"os": "linux"},
            "plugin_version": "test-0.0.1",
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def _instance_headers(jwt: str, tenant_id: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
    if tenant_id:
        h["X-Tenant-ID"] = tenant_id
    return h


# ---------------------------------------------------------------------------
# Tests — enrollment-token issuance
# ---------------------------------------------------------------------------


class TestEnrollmentTokenIssuance:
    def test_admin_can_issue_token(self, admin_headers, tenant_id):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/enrollment-tokens",
            headers=admin_headers,
            json={"tenant_id": tenant_id, "ttl_seconds": 60},
            timeout=10.0,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["token"]
        assert body["tenant_id"] == tenant_id
        assert "expires_at" in body

    def test_non_admin_cannot_issue_token(self, tenant_id):
        # Use a bogus JWT — should 401, not 403, since token decode fails first
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/enrollment-tokens",
            headers={
                "Authorization": "Bearer not-a-real-token",
                "X-Tenant-ID": tenant_id,
                "Content-Type": "application/json",
            },
            json={},
            timeout=10.0,
        )
        assert r.status_code in (401, 403)

    def test_token_is_single_use(self, admin_headers, tenant_id, machine_id):
        token = _issue_token(admin_headers, tenant_id)
        first = _enroll(token, tenant_id, machine_id)
        assert first["instance_id"]

        # Re-using the same token with a different machine should fail
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/enroll",
            headers={"X-Tenant-ID": tenant_id, "Content-Type": "application/json"},
            json={
                "enrollment_token": token,
                "tenant_id": tenant_id,
                "machine_id": f"{machine_id}-other",
                "instance_fingerprint": {"os": "linux"},
            },
            timeout=10.0,
        )
        assert r.status_code == 400
        assert "token" in r.json()["error"].lower()


# ---------------------------------------------------------------------------
# Tests — enrollment
# ---------------------------------------------------------------------------


class TestInstanceEnrollment:
    def test_enroll_with_valid_token(self, admin_headers, tenant_id, machine_id):
        token = _issue_token(admin_headers, tenant_id)
        body = _enroll(token, tenant_id, machine_id)
        assert body["status"] == "pending"
        # Returned JWT should parse and have three dot-separated parts
        assert body["jwt"].count(".") == 2
        # Backing agent_id is a UUID
        uuid.UUID(body["agent_id"])
        uuid.UUID(body["instance_id"])

    def test_enroll_rejects_missing_machine_id(self, admin_headers, tenant_id):
        token = _issue_token(admin_headers, tenant_id)
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/enroll",
            headers={"X-Tenant-ID": tenant_id, "Content-Type": "application/json"},
            json={
                "enrollment_token": token,
                "tenant_id": tenant_id,
                "instance_fingerprint": {},
            },
            timeout=10.0,
        )
        assert r.status_code == 400
        assert "machine_id" in r.json()["error"]

    def test_enroll_rejects_unknown_token(self, tenant_id, machine_id):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/enroll",
            headers={"X-Tenant-ID": tenant_id, "Content-Type": "application/json"},
            json={
                "enrollment_token": "totally-not-real",
                "tenant_id": tenant_id,
                "machine_id": machine_id,
                "instance_fingerprint": {},
            },
            timeout=10.0,
        )
        assert r.status_code == 400

    def test_reenroll_same_machine_returns_existing_instance(
        self, admin_headers, tenant_id, machine_id
    ):
        token1 = _issue_token(admin_headers, tenant_id)
        a = _enroll(token1, tenant_id, machine_id)

        # Issuing another token + enrolling with same machine_id should return
        # the SAME instance_id (idempotent on machine_id). New token IS consumed.
        token2 = _issue_token(admin_headers, tenant_id)
        b = _enroll(token2, tenant_id, machine_id)
        assert b["instance_id"] == a["instance_id"]
        assert b["agent_id"] == a["agent_id"]


# ---------------------------------------------------------------------------
# Tests — instance-scoped operations
# ---------------------------------------------------------------------------


class TestInstanceOperations:
    @pytest.fixture
    def enrolled(self, admin_headers, tenant_id, machine_id) -> dict:
        token = _issue_token(admin_headers, tenant_id)
        return _enroll(token, tenant_id, machine_id)

    def test_heartbeat(self, enrolled):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/heartbeat",
            headers=_instance_headers(enrolled["jwt"]),
            json={"plugin_version": "test-0.0.2"},
            timeout=10.0,
        )
        assert r.status_code == 200
        assert r.json()["status"] in ("pending", "active")

    def test_heartbeat_rejects_missing_token(self):
        r = httpx.post(f"{BASE_URL}/v1/openclaw/instances/heartbeat", json={}, timeout=10.0)
        assert r.status_code == 401

    def test_heartbeat_rejects_bogus_token(self):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/heartbeat",
            headers=_instance_headers("not.a.jwt"),
            json={},
            timeout=10.0,
        )
        assert r.status_code == 401

    def test_fetch_policy_returns_expected_shape(self, enrolled):
        r = httpx.get(
            f"{BASE_URL}/v1/openclaw/instances/policy",
            headers=_instance_headers(enrolled["jwt"]),
            timeout=10.0,
        )
        assert r.status_code == 200
        body = r.json()
        assert {"version", "allowed_tools", "blocked_tools", "rate_limit", "pii_redaction"} <= set(body)
        # In DRAFT state, allowed_tools should be empty and blocked_tools is ["*"]
        assert body["allowed_tools"] == []
        assert body["blocked_tools"] == ["*"]
        assert body["pii_redaction"] is True  # PII data sensitivity is the default

    def test_audit_batch_accepts_events(self, enrolled):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/audit",
            headers=_instance_headers(enrolled["jwt"]),
            json={
                "events": [
                    {
                        "type": "llm_call",
                        "decision": "allow",
                        "decisionReason": None,
                        "payload": {"provider": "openrouter", "model": "openrouter/auto"},
                        "timestamp": "2026-05-14T12:00:00Z",
                    },
                    {
                        "type": "tool_call",
                        "decision": "block",
                        "decisionReason": "blocked by policy",
                        "payload": {"toolName": "shell"},
                        "timestamp": "2026-05-14T12:00:01Z",
                    },
                ]
            },
            timeout=10.0,
        )
        assert r.status_code == 200
        assert r.json() == {"accepted": 2}

    def test_audit_batch_rejects_non_list_events(self, enrolled):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/audit",
            headers=_instance_headers(enrolled["jwt"]),
            json={"events": "not-a-list"},
            timeout=10.0,
        )
        assert r.status_code == 400

    def test_deregister_revokes_instance(self, enrolled):
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/deregister",
            headers=_instance_headers(enrolled["jwt"]),
            json={},
            timeout=10.0,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "revoked"

        # Subsequent calls with the same JWT must be rejected
        r2 = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/heartbeat",
            headers=_instance_headers(enrolled["jwt"]),
            json={},
            timeout=10.0,
        )
        assert r2.status_code == 403


# ---------------------------------------------------------------------------
# Tests — admin list / detail / revoke
# ---------------------------------------------------------------------------


class TestAdminEndpoints:
    def test_list_instances_for_tenant(self, admin_headers, tenant_id, machine_id):
        token = _issue_token(admin_headers, tenant_id)
        _enroll(token, tenant_id, machine_id)
        r = httpx.get(
            f"{BASE_URL}/v1/openclaw/instances",
            headers=admin_headers,
            timeout=10.0,
        )
        assert r.status_code == 200
        instances = r.json()["instances"]
        machines = {i["machine_id"] for i in instances}
        assert machine_id in machines

    def test_get_instance_by_id(self, admin_headers, tenant_id, machine_id):
        token = _issue_token(admin_headers, tenant_id)
        enrolled = _enroll(token, tenant_id, machine_id)
        r = httpx.get(
            f"{BASE_URL}/v1/openclaw/instances/{enrolled['instance_id']}",
            headers=admin_headers,
            timeout=10.0,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == enrolled["instance_id"]
        assert body["machine_id"] == machine_id
        assert body["tenant_id"] == tenant_id

    def test_get_instance_not_found(self, admin_headers):
        r = httpx.get(
            f"{BASE_URL}/v1/openclaw/instances/{uuid.uuid4()}",
            headers=admin_headers,
            timeout=10.0,
        )
        assert r.status_code == 404

    def test_admin_revoke_blocks_instance_jwt(self, admin_headers, tenant_id, machine_id):
        token = _issue_token(admin_headers, tenant_id)
        enrolled = _enroll(token, tenant_id, machine_id)

        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/{enrolled['instance_id']}/revoke",
            headers=admin_headers,
            json={},
            timeout=10.0,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "revoked"

        # The instance's JWT can no longer be used
        r2 = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/heartbeat",
            headers=_instance_headers(enrolled["jwt"]),
            json={},
            timeout=10.0,
        )
        assert r2.status_code == 403


# ---------------------------------------------------------------------------
# Tests — audit row lands in registry
# ---------------------------------------------------------------------------


class TestAuditPersistence:
    def test_audit_event_creates_audit_log_row(self, admin_headers, tenant_id, machine_id):
        """Push an audit event then verify it shows up in /v1/audit-logs."""
        token = _issue_token(admin_headers, tenant_id)
        enrolled = _enroll(token, tenant_id, machine_id)

        marker = secrets.token_hex(8)
        r = httpx.post(
            f"{BASE_URL}/v1/openclaw/instances/audit",
            headers=_instance_headers(enrolled["jwt"], tenant_id),
            json={
                "events": [
                    {
                        "type": "llm_call",
                        "decision": "allow",
                        "payload": {"marker": marker, "provider": "openrouter"},
                        "timestamp": "2026-05-14T12:00:00Z",
                    }
                ]
            },
            timeout=10.0,
        )
        assert r.status_code == 200

        # Query audit log via admin endpoint, scoped to this tenant. The
        # list endpoint elides `detail`, so we have to fetch each entry's
        # detail view to find the marker.
        r2 = httpx.get(
            f"{BASE_URL}/v1/audit-logs",
            headers=admin_headers,
            params={"resource_type": "openclaw_instance", "action": "openclaw.llm_call"},
            timeout=10.0,
        )
        assert r2.status_code == 200
        logs = r2.json().get("logs") or []
        assert logs, f"no openclaw.llm_call rows for tenant {tenant_id}"

        found = False
        for log in logs:
            r3 = httpx.get(
                f"{BASE_URL}/v1/audit-logs/{log['id']}",
                headers=admin_headers,
                timeout=10.0,
            )
            assert r3.status_code == 200
            detail = (r3.json() or {}).get("detail") or {}
            payload = detail.get("payload") or {}
            if payload.get("marker") == marker:
                found = True
                assert detail["decision"] == "allow"
                break
        assert found, (
            f"audit row with marker {marker} not found in tenant {tenant_id} "
            f"(scanned {len(logs)} llm_call rows)"
        )
