"""Tests for the registry client and lifecycle manager."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from runtime.common.models import (
    AuditRecord,
    Direction,
    InterceptorAction,
    InterceptorDecision,
    PolicyAction,
    PolicyRule,
)
from runtime.sidecar.config import AuditConfig, AuthorisationConfig, SidecarConfig
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.lifecycle import LifecycleManager
from runtime.sidecar.registry_client import RegistryClient, RegistryClientError


# ===========================================================================
# RegistryClient unit tests
# ===========================================================================


class TestRegistryClientInit:
    def test_default_config(self):
        client = RegistryClient(registry_url="http://localhost:5000")
        assert client._registry_url == "http://localhost:5000"
        assert client._tenant_id == "default"

    def test_strips_trailing_slash(self):
        client = RegistryClient(registry_url="http://localhost:5000/")
        assert client._registry_url == "http://localhost:5000"

    def test_headers_include_tenant_and_api_key(self):
        client = RegistryClient(
            registry_url="http://localhost:5000",
            api_key="test-key",
            tenant_id="acme",
        )
        headers = client._headers()
        assert headers["X-Tenant-ID"] == "acme"
        assert headers["X-Mesh-API-Key"] == "test-key"

    def test_headers_without_api_key(self):
        client = RegistryClient(registry_url="http://localhost:5000")
        headers = client._headers()
        assert "X-Mesh-API-Key" not in headers

    def test_url_builder(self):
        client = RegistryClient(registry_url="http://localhost:5000")
        assert client._url("/register") == "http://localhost:5000/v1/mesh/register"


# ===========================================================================
# B1-B8: fetch_agent_status() governance status tests
# ===========================================================================


class _FakeResponse:
    """Minimal fake httpx.Response for controlled status_code checks."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class TestFetchAgentStatus:
    """Tests for RegistryClient.fetch_agent_status() — governance lookups."""

    def _make_client(self, cache_ttl: float = 60.0) -> RegistryClient:
        return RegistryClient(
            registry_url="http://localhost:5000",
            api_key="test-key",
            tenant_id="default",
            timeout=5.0,
            cache_ttl=cache_ttl,
        )

    # --- B1: Returns status on successful lookup ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_returns_status_on_success(self, mock_request):
        """Successful lookup returns the status string."""
        mock_request.return_value = _FakeResponse(200, {"status": "active", "agent_id": "123"})
        client = self._make_client()

        result = client.fetch_agent_status("my-agent")

        assert result == "active"
        mock_request.assert_called_once()

    # --- B2: Returns None when agent not found (404) ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_returns_none_on_404(self, mock_request):
        """404 response returns None (agent not found)."""
        mock_request.return_value = _FakeResponse(404)
        client = self._make_client()

        result = client.fetch_agent_status("unknown-agent")

        assert result is None

    # --- B3: Cache hit — no HTTP call on second request ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_cache_hit_no_second_http_call(self, mock_request):
        """Second call within TTL uses cache, no HTTP request."""
        mock_request.return_value = _FakeResponse(200, {"status": "active"})
        client = self._make_client(cache_ttl=60.0)

        result1 = client.fetch_agent_status("my-agent")
        result2 = client.fetch_agent_status("my-agent")

        assert result1 == "active"
        assert result2 == "active"
        assert mock_request.call_count == 1

    # --- B4: Cache expiry — fresh fetch after TTL ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_cache_expiry_triggers_fresh_fetch(self, mock_request):
        """After TTL expires, a new HTTP call is made."""
        mock_request.return_value = _FakeResponse(200, {"status": "active"})
        client = self._make_client(cache_ttl=0.1)  # 100ms TTL

        result1 = client.fetch_agent_status("my-agent")
        assert mock_request.call_count == 1

        # Wait for cache to expire
        time.sleep(0.15)

        mock_request.return_value = _FakeResponse(200, {"status": "suspended"})
        result2 = client.fetch_agent_status("my-agent")

        assert result1 == "active"
        assert result2 == "suspended"
        assert mock_request.call_count == 2

    # --- B5: Registry down with stale cache — returns stale value ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_registry_down_returns_stale_cache(self, mock_request):
        """ConnectError with stale cache returns the cached value (fail-open)."""
        mock_request.return_value = _FakeResponse(200, {"status": "active"})
        client = self._make_client(cache_ttl=0.1)

        result1 = client.fetch_agent_status("my-agent")
        assert result1 == "active"

        time.sleep(0.15)

        mock_request.side_effect = httpx.ConnectError("connection refused")
        result2 = client.fetch_agent_status("my-agent")

        assert result2 == "active"  # stale cache

    # --- B6: Registry down with no cache — returns None ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_registry_down_no_cache_returns_none(self, mock_request):
        """ConnectError with no prior cache returns None (fail-closed)."""
        mock_request.side_effect = httpx.ConnectError("connection refused")
        client = self._make_client()

        result = client.fetch_agent_status("my-agent")

        assert result is None

    # --- B7: Non-200 response with stale cache — returns stale value ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_non_200_returns_stale_cache(self, mock_request):
        """500 response with stale cache returns the cached value."""
        mock_request.return_value = _FakeResponse(200, {"status": "active"})
        client = self._make_client(cache_ttl=0.1)

        result1 = client.fetch_agent_status("my-agent")
        assert result1 == "active"

        time.sleep(0.15)

        mock_request.return_value = _FakeResponse(500)
        result2 = client.fetch_agent_status("my-agent")

        assert result2 == "active"  # stale cache

    # --- B8: Non-200 response with no cache — returns None ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_non_200_no_cache_returns_none(self, mock_request):
        """500 response with no prior cache returns None."""
        mock_request.return_value = _FakeResponse(500)
        client = self._make_client()

        result = client.fetch_agent_status("my-agent")

        assert result is None

    # --- Additional: TimeoutException handling ---

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_timeout_returns_stale_cache(self, mock_request):
        """TimeoutException with stale cache returns the cached value."""
        mock_request.return_value = _FakeResponse(200, {"status": "active"})
        client = self._make_client(cache_ttl=0.1)

        result1 = client.fetch_agent_status("my-agent")
        assert result1 == "active"

        time.sleep(0.15)

        mock_request.side_effect = httpx.TimeoutException("read timed out")
        result2 = client.fetch_agent_status("my-agent")

        assert result2 == "active"

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_timeout_no_cache_returns_none(self, mock_request):
        """TimeoutException with no cache returns None."""
        mock_request.side_effect = httpx.TimeoutException("read timed out")
        client = self._make_client()

        result = client.fetch_agent_status("my-agent")

        assert result is None


class TestRegistryClientRegister:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_register_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "registered",
                "agent_id": "uuid-1",
                "policies": [
                    {"source": "*", "destination": "*", "action": "allow", "priority": 0}
                ],
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        result = client.register(
            agent_id="uuid-1",
            sidecar_url="https://host:8443",
            agent_card={"name": "test"},
        )

        assert result["status"] == "registered"
        assert client.cached_policies is not None
        assert len(client.cached_policies) == 1

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_register_caches_policies(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "status": "registered",
                "agent_id": "uuid-1",
                "policies": [
                    {"source": "agent-a", "destination": "agent-b", "action": "allow", "priority": 0},
                    {"source": "*", "destination": "*", "action": "deny", "priority": 10},
                ],
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        client.register(
            agent_id="uuid-1",
            sidecar_url="https://host:8443",
            agent_card={"name": "test"},
        )

        policies = client.cached_policies
        assert len(policies) == 2
        assert policies[0].source == "agent-a"
        assert policies[0].action == PolicyAction.ALLOW
        assert policies[1].action == PolicyAction.DENY

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_register_raises_on_http_error(self, mock_post):
        response = MagicMock(
            status_code=403,
            content=b'{"error": "Agent must be ACTIVE"}',
        )
        response.json.return_value = {"error": "Agent must be ACTIVE"}
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "forbidden", request=MagicMock(), response=response,
        )
        mock_post.return_value = response

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError, match="Agent must be ACTIVE"):
            client.register(
                agent_id="uuid-1",
                sidecar_url="https://host:8443",
                agent_card={"name": "test"},
            )

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_register_raises_on_connect_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError, match="failed"):
            client.register(
                agent_id="uuid-1",
                sidecar_url="https://host:8443",
                agent_card={"name": "test"},
            )


class TestRegistryClientHeartbeat:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_heartbeat_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "ok"},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        result = client.heartbeat("uuid-1")
        assert result["status"] == "ok"

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_heartbeat_raises_on_404(self, mock_post):
        response = MagicMock(status_code=404)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=response,
        )
        mock_post.return_value = response

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError):
            client.heartbeat("uuid-1")


class TestRegistryClientDeregister:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_deregister_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "deregistered"},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        result = client.deregister("uuid-1")
        assert result["status"] == "deregistered"


class TestRegistryClientDiscovery:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_discover_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "agents": [
                    {
                        "agent_id": "uuid-2",
                        "name": "fact-checker",
                        "sidecar_url": "https://host-b:8444",
                        "skills": ["fact-check"],
                        "version": "1.0.0",
                        "status": "healthy",
                    }
                ]
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        agents = client.discover("fact-check")

        assert len(agents) == 1
        assert agents[0]["name"] == "fact-checker"
        assert agents[0]["sidecar_url"] == "https://host-b:8444"

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_discover_caches_result(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"agents": [{"name": "agent-b", "sidecar_url": "https://b:8444"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        client.set_cache_ttl(60.0)

        # First call hits the API
        agents1 = client.discover("fact-check")
        # Second call uses cache
        agents2 = client.discover("fact-check")

        assert mock_get.call_count == 1
        assert agents1 == agents2

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_discover_cache_bypass(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"agents": []},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        client.discover("fact-check", use_cache=False)
        client.discover("fact-check", use_cache=False)

        assert mock_get.call_count == 2

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_discover_returns_stale_cache_on_error(self, mock_get):
        # First call succeeds
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"agents": [{"name": "cached-agent"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        client.set_cache_ttl(0.001)  # Expire immediately
        agents1 = client.discover("fact-check")

        # Expire the cache
        time.sleep(0.01)

        # Second call fails
        mock_get.side_effect = httpx.ConnectError("connection refused")
        agents2 = client.discover("fact-check")

        assert agents2 == agents1  # Returns stale cache

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_discover_raises_when_no_cache(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("connection refused")

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError, match="Discovery failed"):
            client.discover("fact-check")

    @pytest.mark.asyncio
    @patch("runtime.sidecar.registry_client.httpx.request")
    async def test_resolve_destination(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "agents": [
                    {"name": "fact-checker", "sidecar_url": "https://host-b:8444"}
                ]
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        url, name = await client.resolve_destination("fact-check")

        assert url == "https://host-b:8444"
        assert name == "fact-checker"

    @pytest.mark.asyncio
    @patch("runtime.sidecar.registry_client.httpx.request")
    async def test_resolve_destination_raises_when_empty(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"agents": []},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError, match="No agent found"):
            await client.resolve_destination("nonexistent-skill")


class TestRegistryClientPolicies:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_policies(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "policies": [
                    {"source": "agent-a", "destination": "agent-b", "action": "allow", "priority": 0},
                ]
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        policies = client.fetch_policies()

        assert len(policies) == 1
        assert policies[0].source == "agent-a"
        assert policies[0].action == PolicyAction.ALLOW

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_policies_caches_result(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"policies": [
                {"source": "*", "destination": "*", "action": "deny", "priority": 0}
            ]},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        client.fetch_policies()

        assert client.cached_policies is not None
        assert len(client.cached_policies) == 1

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_policies_returns_cached_on_error(self, mock_get):
        # First call succeeds
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"policies": [
                {"source": "*", "destination": "*", "action": "allow", "priority": 0}
            ]},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        policies1 = client.fetch_policies()

        # Second call fails
        mock_get.side_effect = httpx.ConnectError("connection refused")
        policies2 = client.fetch_policies()

        assert policies2 == policies1  # Returns cached


class TestRegistryClientToolGovernance:
    """Tests for tool and egress rule fetching."""

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_tools_for_agent_success(self, mock_request):
        """Fetches and caches tools for an agent."""
        mock_request.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "tools": [
                    {"name": "verify_customer", "endpoint_url": "http://stub:6000/verify", "http_method": "POST"},
                ]
            },
        )
        mock_request.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        tools = client.fetch_tools_for_agent("Auth Agent")

        assert len(tools) == 1
        assert tools[0]["name"] == "verify_customer"
        assert client.cached_tools == tools

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_tools_returns_cached_on_error(self, mock_request):
        """Returns cached tools when registry is unreachable."""
        # First call succeeds
        mock_request.return_value = MagicMock(
            status_code=200,
            json=lambda: {"tools": [{"name": "t1"}]},
        )
        mock_request.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        tools1 = client.fetch_tools_for_agent("Agent")

        # Second call fails
        mock_request.side_effect = httpx.ConnectError("connection refused")
        tools2 = client.fetch_tools_for_agent("Agent")

        assert tools2 == tools1

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_tools_returns_empty_when_no_cache(self, mock_request):
        """Returns empty list when registry fails and no cache exists."""
        mock_request.side_effect = httpx.ConnectError("connection refused")

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        tools = client.fetch_tools_for_agent("Agent")

        assert tools == []

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_egress_rules_success(self, mock_request):
        """Fetches and caches egress rules for an agent."""
        mock_request.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "rules": [
                    {"url_pattern": "http://stub:6000/*", "action": "allow", "priority": 0},
                    {"url_pattern": "*", "action": "deny", "priority": 100},
                ]
            },
        )
        mock_request.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        rules = client.fetch_egress_rules_for_agent("Auth Agent")

        assert len(rules) == 2
        assert rules[0]["action"] == "allow"
        assert client.cached_egress_rules == rules

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_egress_rules_returns_cached_on_error(self, mock_request):
        """Returns cached rules when registry is unreachable."""
        mock_request.return_value = MagicMock(
            status_code=200,
            json=lambda: {"rules": [{"url_pattern": "*", "action": "deny"}]},
        )
        mock_request.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        rules1 = client.fetch_egress_rules_for_agent("Agent")

        mock_request.side_effect = httpx.ConnectError("connection refused")
        rules2 = client.fetch_egress_rules_for_agent("Agent")

        assert rules2 == rules1

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_fetch_egress_rules_returns_empty_when_no_cache(self, mock_request):
        """Returns empty list when registry fails and no cache exists."""
        mock_request.side_effect = httpx.ConnectError("connection refused")

        client = RegistryClient(registry_url="http://localhost:5000", api_key="test-key")
        rules = client.fetch_egress_rules_for_agent("Agent")

        assert rules == []

    def test_cached_tools_none_by_default(self):
        """cached_tools returns None before first fetch."""
        client = RegistryClient(registry_url="http://localhost:5000")
        assert client.cached_tools is None

    def test_cached_egress_rules_none_by_default(self):
        """cached_egress_rules returns None before first fetch."""
        client = RegistryClient(registry_url="http://localhost:5000")
        assert client.cached_egress_rules is None


class TestRegistryClientAudit:
    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_ship_audit_records(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"status": "accepted", "count": 2},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        client = RegistryClient(registry_url="http://localhost:5000")
        result = client.ship_audit_records([
            {"timestamp": "2026-01-01T00:00:00Z", "a2a_method": "message/send",
             "message_hash": "abc", "direction": "inbound", "decision": "pass", "outcome": "success"},
            {"timestamp": "2026-01-01T00:00:01Z", "a2a_method": "tasks/get",
             "message_hash": "def", "direction": "inbound", "decision": "pass", "outcome": "success"},
        ])

        assert result["count"] == 2

    def test_ship_empty_records(self):
        client = RegistryClient(registry_url="http://localhost:5000")
        result = client.ship_audit_records([])
        assert result["status"] == "no records"

    @patch("runtime.sidecar.registry_client.httpx.request")
    def test_ship_raises_on_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")

        client = RegistryClient(registry_url="http://localhost:5000")
        with pytest.raises(RegistryClientError, match="Audit shipping failed"):
            client.ship_audit_records([{"a2a_method": "test"}])


# ===========================================================================
# LifecycleManager unit tests
# ===========================================================================


def _make_lifecycle(agent_id="uuid-1") -> tuple[LifecycleManager, RegistryClient]:
    config = SidecarConfig(
        agent_id=agent_id,
        heartbeat_interval_seconds=1,
        policy_sync_interval_seconds=1,
        interceptors={
            "authentication": {"enabled": False},
            "authorisation": {"enabled": True, "default_action": "deny"},
            "audit": {"enabled": True, "flush_interval_seconds": 1},
        },
    )
    registry = MagicMock(spec=RegistryClient)
    registry.cached_policies = [
        PolicyRule(source="*", destination="*", action=PolicyAction.ALLOW, priority=0)
    ]
    registry.register.return_value = {
        "status": "registered",
        "agent_id": agent_id,
        "policies": [],
    }
    registry.heartbeat.return_value = {"status": "ok"}
    registry.deregister.return_value = {"status": "deregistered"}
    registry.fetch_policies.return_value = []
    registry.ship_audit_records.return_value = {"status": "accepted", "count": 0}
    registry.all_registry_urls = ["http://localhost:5000"]
    registry.stop.return_value = None
    registry.fetch_tools_for_agent.return_value = []
    registry.fetch_egress_rules_for_agent.return_value = []

    authz = AuthorisationInterceptor(config.interceptors.authorisation)
    audit = AuditInterceptor(config.interceptors.audit)
    agent_card = {"name": "test-agent", "version": "1.0.0"}

    lifecycle = LifecycleManager(
        config=config,
        registry_client=registry,
        authz_interceptor=authz,
        audit_interceptor=audit,
        agent_card_json=agent_card,
    )
    return lifecycle, registry


class TestLifecycleManager:
    def test_startup_registers_with_registry(self):
        lifecycle, registry = _make_lifecycle()
        lifecycle.startup()

        registry.register.assert_called_once()
        assert lifecycle.is_running

        lifecycle.shutdown()

    def test_startup_applies_policies(self):
        lifecycle, registry = _make_lifecycle()
        lifecycle.startup()

        # Policies from cached_policies should have been applied
        assert lifecycle._authz.active_policies is not None

        lifecycle.shutdown()

    def test_shutdown_deregisters(self):
        lifecycle, registry = _make_lifecycle()
        lifecycle.startup()
        lifecycle.shutdown()

        registry.deregister.assert_called_once_with("uuid-1", sidecar_url=lifecycle._sidecar_url)
        assert not lifecycle.is_running

    def test_shutdown_without_startup_is_noop(self):
        lifecycle, registry = _make_lifecycle()
        lifecycle.shutdown()
        registry.deregister.assert_not_called()

    def test_startup_without_agent_id_skips_registration(self):
        lifecycle, registry = _make_lifecycle(agent_id=None)
        result = lifecycle.startup()

        assert result["status"] == "skipped"
        registry.register.assert_not_called()

        lifecycle.shutdown()

    def test_shutdown_flushes_audit(self):
        lifecycle, registry = _make_lifecycle()
        lifecycle.startup()

        # Add some audit records via create_record_from_result (the real path)
        audit = lifecycle._audit
        from runtime.common.models import InterceptorContext
        ctx = InterceptorContext(
            direction=Direction.INBOUND,
            a2a_method="message/send",
            payload={"test": True},
        )
        audit.create_record_from_result(ctx, [], "success")

        lifecycle.shutdown()

        # Audit records should have been shipped
        registry.ship_audit_records.assert_called()

    def test_serialize_audit_record(self):
        record = AuditRecord(
            a2a_method="message/send",
            message_hash="abc123",
            direction=Direction.INBOUND,
            decision="pass",
            outcome="success",
            source_agent_name="agent-a",
            dest_agent_name="agent-b",
            interceptor_decisions=[
                InterceptorDecision(
                    interceptor="authentication",
                    action=InterceptorAction.PASS,
                    reason="ok",
                )
            ],
        )

        serialized = LifecycleManager._serialize_audit_record(record)

        assert serialized["a2a_method"] == "message/send"
        assert serialized["direction"] == "inbound"
        assert serialized["source_agent_name"] == "agent-a"
        assert serialized["details"] is not None
        assert serialized["details"][0]["interceptor"] == "authentication"
