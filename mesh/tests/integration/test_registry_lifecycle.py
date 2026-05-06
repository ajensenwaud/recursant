"""Integration tests: sidecar registry client and lifecycle manager.

Tests the RegistryClient and LifecycleManager against the real registry
(K8s cluster or Docker Compose on localhost:5000). For resilience tests
(cache fallback, error handling), the real registry is used for initial
calls, then _registry_url is swapped to an unreachable address to simulate
failure.

Ensure the registry is reachable before running these tests.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from runtime.common.models import (
    AuditRecord,
    Direction,
    PolicyRule,
)
from runtime.sidecar.config import (
    AuditConfig,
    AuthorisationConfig,
    InterceptorsConfig,
    SidecarConfig,
)
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.lifecycle import LifecycleManager
from runtime.sidecar.registry_client import RegistryClient, RegistryClientError
from tests.integration.conftest import (
    MESH_API_KEY,
    REGISTRY_URL,
    admin_login,
    create_agent_in_registry,
    deregister_sidecar,
    registry_available,
    set_agent_status,
)


pytestmark = pytest.mark.skipif(
    not registry_available(),
    reason="Real registry not available (K8s or Docker Compose)",
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(scope="module")
def registry_agent():
    """Create an APPROVED agent for lifecycle tests.

    Yields (agent_id, agent_name). On teardown, deregisters the sidecar
    and resets the agent status back to DRAFT.
    """
    token = admin_login()
    agent_name = "Lifecycle Test Agent"
    agent_id = create_agent_in_registry(
        token=token,
        name=agent_name,
        skill="lifecycle-test",
        desc="Agent for registry lifecycle integration tests",
        endpoint_url="http://127.0.0.1:17001",
    )
    set_agent_status(agent_name, "APPROVED")

    yield agent_id, agent_name

    deregister_sidecar(agent_id)
    set_agent_status(agent_name, "DRAFT")


@pytest.fixture(scope="module")
def draft_agent():
    """Create a DRAFT agent (not approved) for negative tests.

    Yields (agent_id, agent_name).
    """
    token = admin_login()
    agent_name = "Lifecycle Draft Agent"
    agent_id = create_agent_in_registry(
        token=token,
        name=agent_name,
        skill="draft-test",
        desc="Draft agent for negative lifecycle tests",
        endpoint_url="http://127.0.0.1:17001",
    )
    # Explicitly ensure DRAFT status (create_agent_in_registry may leave it
    # in SUBMITTED or another state depending on the registry logic).
    set_agent_status(agent_name, "DRAFT")

    yield agent_id, agent_name


@pytest.fixture
def registry_client():
    """Return a fresh RegistryClient pointing at the real registry."""
    return RegistryClient(
        registry_url=REGISTRY_URL,
        api_key=MESH_API_KEY,
    )


# ===========================================================================
# Tests: Registration lifecycle
# ===========================================================================


class TestRegistrationLifecycle:
    """Test register -> heartbeat -> deregister flow against the real registry."""

    def test_register_then_heartbeat_then_deregister(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        # Register
        result = registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={"name": agent_name, "version": "1.0.0", "skills": [{"id": "lifecycle-test"}]},
        )
        assert result["status"] == "registered"

        # Heartbeat
        result = registry_client.heartbeat(agent_id)
        assert result["status"] == "ok"

        # Deregister
        result = registry_client.deregister(agent_id)
        assert result["status"] == "deregistered"

    def test_registration_caches_policies(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        result = registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={"name": agent_name, "version": "1.0.0", "skills": []},
        )

        policies = registry_client.cached_policies
        assert policies is not None
        # Policies list may be empty or populated depending on what's seeded
        assert isinstance(policies, list)

        # Cleanup
        registry_client.deregister(agent_id)

    def test_registration_failure_for_draft_agent(self, registry_client, draft_agent):
        """A DRAFT agent cannot register -- real registry returns 403."""
        agent_id, agent_name = draft_agent

        with pytest.raises(RegistryClientError, match="Registration failed"):
            registry_client.register(
                agent_id=agent_id,
                sidecar_url="https://localhost:17901",
                agent_card={"name": agent_name, "version": "1.0.0", "skills": []},
            )


# ===========================================================================
# Tests: Discovery
# ===========================================================================


class TestDiscovery:
    """Test skill-based agent discovery with caching against the real registry."""

    def test_discover_returns_agents(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        # Must register first so agent appears in discovery
        registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={
                "name": agent_name,
                "version": "1.0.0",
                "skills": [{"id": "lifecycle-test", "name": "lifecycle-test"}],
            },
        )

        agents = registry_client.discover("lifecycle-test")
        assert len(agents) >= 1
        names = [a["name"] for a in agents]
        assert agent_name in names

        registry_client.deregister(agent_id)

    def test_discover_uses_cache(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={
                "name": agent_name,
                "version": "1.0.0",
                "skills": [{"id": "lifecycle-test", "name": "lifecycle-test"}],
            },
        )

        # First call populates cache
        registry_client.discover("lifecycle-test")
        cache_key = "lifecycle-test:"
        assert cache_key in registry_client._discovery_cache

        # Second call should use cache (verify cache entry still there)
        agents = registry_client.discover("lifecycle-test")
        assert len(agents) >= 1

        registry_client.deregister(agent_id)

    def test_discover_cache_expires(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={
                "name": agent_name,
                "version": "1.0.0",
                "skills": [{"id": "lifecycle-test", "name": "lifecycle-test"}],
            },
        )

        registry_client.set_cache_ttl(0.01)  # 10ms TTL
        registry_client.discover("lifecycle-test")

        time.sleep(0.02)  # Wait for TTL to expire

        # Cache entry should be expired -- next call makes new HTTP request
        cache_key = "lifecycle-test:"
        _, expiry = registry_client._discovery_cache[cache_key]
        assert time.time() > expiry  # Expired

        # Call again -- should refresh the cache
        registry_client.discover("lifecycle-test")
        _, new_expiry = registry_client._discovery_cache[cache_key]
        assert new_expiry > expiry  # New expiry is later

        registry_client.deregister(agent_id)

    def test_discover_falls_back_to_stale_cache(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={
                "name": agent_name,
                "version": "1.0.0",
                "skills": [{"id": "lifecycle-test", "name": "lifecycle-test"}],
            },
        )

        # Populate cache with real data
        agents = registry_client.discover("lifecycle-test")
        assert len(agents) >= 1

        # Expire cache and break the URL
        registry_client.set_cache_ttl(0)
        registry_client._registry_url = "http://127.0.0.1:1"  # unreachable

        # Should fall back to stale cache
        agents = registry_client.discover("lifecycle-test")
        assert len(agents) >= 1
        assert agents[0]["name"] == agent_name

        # Restore URL for cleanup
        registry_client._registry_url = REGISTRY_URL.rstrip("/")
        registry_client.deregister(agent_id)

    def test_resolve_destination_returns_url_and_name(self, registry_client, registry_agent):
        agent_id, agent_name = registry_agent

        registry_client.register(
            agent_id=agent_id,
            sidecar_url="https://localhost:17901",
            agent_card={
                "name": agent_name,
                "version": "1.0.0",
                "skills": [{"id": "lifecycle-test", "name": "lifecycle-test"}],
            },
        )

        url, name = asyncio.run(registry_client.resolve_destination("lifecycle-test"))
        assert url == "https://localhost:17901"
        assert name == agent_name

        registry_client.deregister(agent_id)


# ===========================================================================
# Tests: Policy fetch
# ===========================================================================


class TestPolicyFetch:
    """Test policy fetching from the real registry."""

    def test_fetch_policies(self, registry_client):
        """Fetch policies from the real registry."""
        policies = registry_client.fetch_policies()
        assert isinstance(policies, list)
        # May be empty or populated depending on registry state
        for p in policies:
            assert isinstance(p, PolicyRule)

    def test_fetch_policies_falls_back_to_cached(self, registry_client):
        """After successful fetch, breaking URL should return stale cache."""
        # First fetch succeeds
        policies = registry_client.fetch_policies()
        assert isinstance(policies, list)

        # Break the URL
        registry_client._registry_url = "http://127.0.0.1:1"

        # Should return cached policies
        cached = registry_client.fetch_policies()
        assert cached == policies


# ===========================================================================
# Tests: Audit shipping
# ===========================================================================


class TestAuditShipping:
    """Test audit record shipping to the real registry."""

    def test_ship_audit_records(self, registry_client):
        """Ship audit records to the real registry."""
        records = [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_agent_name": "Agent A",
                "dest_agent_name": "Agent B",
                "a2a_method": "message/send",
                "message_hash": "abc123",
                "direction": "outbound",
                "decision": "pass",
                "outcome": "success",
            },
        ]
        result = registry_client.ship_audit_records(records)
        assert result["count"] >= 1

    def test_ship_empty_records_is_noop(self, registry_client):
        result = registry_client.ship_audit_records([])
        assert result["count"] == 0


# ===========================================================================
# Tests: Lifecycle manager integration
# ===========================================================================


class TestLifecycleManager:
    """Test the LifecycleManager against the real registry."""

    @staticmethod
    def _make_lifecycle(agent_id, agent_name):
        """Build a LifecycleManager with real registry configuration."""
        config = SidecarConfig(
            port=17901,
            a2a_port=17901,
            agent_port=17001,
            agent_id=agent_id,
            registry_url=REGISTRY_URL,
            registry_api_key=MESH_API_KEY,
            heartbeat_interval_seconds=3600,
            policy_sync_interval_seconds=3600,
            interceptors=InterceptorsConfig(
                audit=AuditConfig(enabled=True, flush_interval_seconds=3600),
            ),
        )
        client = RegistryClient(
            registry_url=REGISTRY_URL,
            api_key=MESH_API_KEY,
        )
        authz = AuthorisationInterceptor(AuthorisationConfig(enabled=True, default_action="deny"))
        audit = AuditInterceptor(AuditConfig(enabled=True, flush_interval_seconds=3600))
        agent_card = {"name": agent_name, "version": "1.0.0", "skills": [{"id": "lifecycle-test"}]}

        lifecycle = LifecycleManager(
            config=config,
            registry_client=client,
            authz_interceptor=authz,
            audit_interceptor=audit,
            agent_card_json=agent_card,
        )
        return lifecycle, authz, audit, client

    def test_startup_registers_and_applies_policies(self, registry_agent):
        agent_id, agent_name = registry_agent
        lifecycle, authz, audit, client = self._make_lifecycle(agent_id, agent_name)

        result = lifecycle.startup()
        assert result["status"] == "registered"
        assert lifecycle.is_running

        # Policies should have been applied (list, possibly empty)
        assert isinstance(authz._registry_policies, list)

        lifecycle.shutdown()
        assert not lifecycle.is_running

    def test_shutdown_deregisters(self, registry_agent):
        agent_id, agent_name = registry_agent
        lifecycle, authz, audit, client = self._make_lifecycle(agent_id, agent_name)

        lifecycle.startup()
        lifecycle.shutdown()

        # After deregistration, agent should not appear in discovery
        agents = client.discover("lifecycle-test", use_cache=False)
        agent_ids = [a["agent_id"] for a in agents]
        assert agent_id not in agent_ids

    def test_audit_flush_on_shutdown(self, registry_agent):
        agent_id, agent_name = registry_agent
        lifecycle, authz, audit, client = self._make_lifecycle(agent_id, agent_name)

        # Add a record to the audit buffer
        audit._buffer.append(
            AuditRecord(
                source_agent_name="A",
                dest_agent_name="B",
                a2a_method="message/send",
                message_hash="test-hash",
                direction=Direction.OUTBOUND,
                decision="pass",
                outcome="success",
            )
        )

        lifecycle.startup()
        lifecycle.shutdown()

        # Buffer should be drained (records shipped to registry)
        assert len(audit._buffer) == 0
