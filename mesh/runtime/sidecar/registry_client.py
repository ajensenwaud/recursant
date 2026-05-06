"""REST client for the Recursant Registry mesh control plane API.

Handles registration, heartbeat, deregistration, discovery, policy
fetching, and audit record shipping.

Supports multi-registry failover: when configured with multiple registry
URLs, requests automatically fail over to the next healthy URL on
connection/timeout errors.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import httpx
import structlog

from runtime.common.models import PolicyAction, PolicyRule
from runtime.sidecar.telemetry import record_discovery_cache

logger = structlog.get_logger()


class RegistryClientError(Exception):
    """Base exception for registry client errors."""


class RegistryClient:
    """Client for the registry's /v1/mesh/* endpoints.

    Provides methods for sidecar lifecycle (register, heartbeat, deregister),
    agent discovery, policy fetching, and audit log shipping.

    When initialised with multiple registry URLs, automatically fails over
    to the next URL on connection/timeout errors and runs a background
    health check loop to re-promote recovered URLs.
    """

    def __init__(
        self,
        registry_url: str = "http://localhost:5000",
        registry_urls: list[str] | None = None,
        api_key: Optional[str] = None,
        tenant_id: str = "default",
        timeout: float = 10.0,
        failover_timeout: float = 3.0,
        cache_ttl: float = 60.0,
    ):
        # Build the ordered URL list: explicit list takes precedence
        if registry_urls:
            self._urls = [u.rstrip("/") for u in registry_urls]
        else:
            self._urls = [registry_url.rstrip("/")]

        self._api_key = api_key
        self._tenant_id = tenant_id
        self._timeout = timeout
        self._failover_timeout = failover_timeout

        # Failover state
        self._current_index: int = 0
        self._url_health: dict[str, bool] = {u: True for u in self._urls}
        self._lock = threading.Lock()

        # Health check background thread (only when multiple URLs)
        self._health_stop = threading.Event()
        self._health_thread: threading.Thread | None = None
        if len(self._urls) > 1:
            self._health_thread = threading.Thread(
                target=self._health_check_loop, daemon=True, name="registry-health",
            )
            self._health_thread.start()

        # Discovery cache: skill -> (result, expiry_time)
        self._discovery_cache: dict[str, tuple[list[dict], float]] = {}
        self._cache_ttl: float = cache_ttl

        # Cached policies from registry
        self._policies: list[PolicyRule] | None = None

        # Keep the original single-URL accessor for backwards compat
        self._registry_url = self._urls[0]

    def stop(self) -> None:
        """Stop background threads."""
        self._health_stop.set()
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)

    # -----------------------------------------------------------------
    # Multi-URL failover internals
    # -----------------------------------------------------------------

    @property
    def active_registry_url(self) -> str:
        """Return the currently active registry URL."""
        with self._lock:
            return self._urls[self._current_index]

    @property
    def all_registry_urls(self) -> list[str]:
        """Return all configured registry URLs."""
        return list(self._urls)

    def mark_unhealthy(self, url: str) -> None:
        """Mark a registry URL as unhealthy and advance to the next."""
        with self._lock:
            self._url_health[url] = False
            # Advance to next healthy URL
            for i in range(len(self._urls)):
                candidate = self._urls[(self._current_index + i + 1) % len(self._urls)]
                if self._url_health.get(candidate, False):
                    self._current_index = self._urls.index(candidate)
                    logger.warning(
                        "registry_failover",
                        from_url=url,
                        to_url=candidate,
                    )
                    return
            # All unhealthy — stay on current
            logger.error("all_registries_unhealthy")

    def _health_check_loop(self) -> None:
        """Background thread: periodically check unhealthy URLs and re-promote."""
        while not self._health_stop.wait(timeout=30):
            for url in self._urls:
                if self._url_health.get(url, True):
                    continue
                try:
                    resp = httpx.get(
                        f"{url}/health",
                        timeout=self._failover_timeout,
                    )
                    if resp.status_code == 200:
                        with self._lock:
                            self._url_health[url] = True
                        logger.info("registry_recovered", url=url)
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | list | None = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make an HTTP request with automatic failover across registry URLs.

        Tries the current primary URL first, then fails over to other
        healthy URLs. Raises RegistryClientError if all URLs fail.
        """
        effective_timeout = timeout or self._timeout
        last_error: Exception | None = None

        tried = set()
        for _ in range(len(self._urls)):
            url = self.active_registry_url
            if url in tried:
                break
            tried.add(url)

            full_url = f"{url}/v1/mesh{path}"
            try:
                resp = httpx.request(
                    method,
                    full_url,
                    json=json,
                    params=params,
                    headers=self._headers(),
                    timeout=effective_timeout,
                )
                # Success — mark healthy and return
                with self._lock:
                    self._url_health[url] = True
                return resp

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(
                    "registry_request_failed",
                    url=full_url,
                    method=method,
                    error=str(e),
                )
                last_error = e
                self.mark_unhealthy(url)

        raise RegistryClientError(
            f"All registry URLs failed for {method} {path}: {last_error}"
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["X-Mesh-API-Key"] = self._api_key
        return headers

    def _url(self, path: str) -> str:
        """Build URL for the active registry. Used by legacy callers."""
        return f"{self.active_registry_url}/v1/mesh{path}"

    # -----------------------------------------------------------------
    # Agent lookup
    # -----------------------------------------------------------------

    def lookup_agent_id_by_name(self, agent_name: str) -> str | None:
        """Look up an agent's UUID by name from the registry.

        Uses the mesh API key (not admin JWT) via /v1/mesh/agents/lookup.
        Falls back to None if lookup fails.
        """
        try:
            resp = self._request(
                "GET",
                "/agents/lookup",
                params={"name": agent_name},
            )
            if resp.status_code != 200:
                logger.warning("agent_lookup_failed", status=resp.status_code)
                return None

            agent_id = resp.json().get("agent_id")
            logger.info("agent_lookup_success", name=agent_name, agent_id=agent_id)
            return agent_id

        except RegistryClientError as e:
            logger.warning("agent_lookup_error", error=str(e))
            return None

    # -----------------------------------------------------------------
    # Registered agents
    # -----------------------------------------------------------------

    def fetch_registered_agents(self) -> set[str]:
        """Fetch the names of all currently registered (active + healthy) agents.

        Calls GET /v1/mesh/discover with no skill filter, which returns
        all healthy active agents.
        """
        try:
            resp = self._request("GET", "/discover")
            resp.raise_for_status()
            data = resp.json()
            return {a["name"] for a in data.get("agents", [])}
        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("fetch_registered_agents_failed", error=str(e))
            return set()

    # -----------------------------------------------------------------
    # Registration lifecycle
    # -----------------------------------------------------------------

    def register(
        self,
        agent_id: str,
        sidecar_url: str,
        agent_card: dict[str, Any],
        sovereignty_zone: Optional[str] = None,
    ) -> dict[str, Any]:
        """Register this sidecar with the registry.

        Returns the registration response including current policies.
        """
        payload = {
            "agent_id": agent_id,
            "sidecar_url": sidecar_url,
            "agent_card": agent_card,
            "sovereignty_zone": sovereignty_zone,
        }

        try:
            resp = self._request("POST", "/register", json=payload)
            resp.raise_for_status()
            data = resp.json()

            # Cache policies from registration response
            if "policies" in data:
                self._policies = self._parse_policies(data["policies"])

            logger.info(
                "registry_registered",
                agent_id=agent_id,
                policy_count=len(data.get("policies", [])),
            )
            return data

        except httpx.HTTPStatusError as e:
            body = e.response.json() if e.response.content else {}
            error_msg = body.get("error", str(e))
            logger.error("registry_register_failed", error=error_msg, status=e.response.status_code)
            raise RegistryClientError(f"Registration failed: {error_msg}") from e
        except RegistryClientError:
            raise

    def heartbeat(self, agent_id: str) -> dict[str, Any]:
        """Send a heartbeat to the registry."""
        try:
            resp = self._request("POST", "/heartbeat", json={"agent_id": agent_id})
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("heartbeat_failed", agent_id=agent_id, error=str(e))
            raise RegistryClientError(f"Heartbeat failed: {e}") from e

    def deregister(self, agent_id: str, sidecar_url: str | None = None) -> dict[str, Any]:
        """Deregister this sidecar from the registry."""
        payload: dict[str, Any] = {"agent_id": agent_id}
        if sidecar_url:
            payload["sidecar_url"] = sidecar_url
        try:
            resp = self._request("POST", "/deregister", json=payload)
            resp.raise_for_status()
            logger.info("registry_deregistered", agent_id=agent_id)
            return resp.json()
        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("deregister_failed", agent_id=agent_id, error=str(e))
            raise RegistryClientError(f"Deregister failed: {e}") from e

    # -----------------------------------------------------------------
    # Multi-registry operations (register/heartbeat/deregister to ALL)
    # -----------------------------------------------------------------

    def register_all(
        self,
        agent_id: str,
        sidecar_url: str,
        agent_card: dict[str, Any],
        sovereignty_zone: Optional[str] = None,
    ) -> dict[str, Any]:
        """Register with ALL reachable registries.

        Returns the response from the primary registry. Logs errors
        for secondary registries but does not fail.
        """
        payload = {
            "agent_id": agent_id,
            "sidecar_url": sidecar_url,
            "agent_card": agent_card,
            "sovereignty_zone": sovereignty_zone,
        }

        primary_result = None
        for url in self._urls:
            try:
                resp = httpx.post(
                    f"{url}/v1/mesh/register",
                    json=payload,
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if primary_result is None:
                    primary_result = data
                    # Cache policies from primary
                    if "policies" in data:
                        self._policies = self._parse_policies(data["policies"])
                logger.info("registry_registered", agent_id=agent_id, registry=url)
            except Exception as e:
                logger.warning(
                    "multi_registry_register_failed",
                    registry=url, agent_id=agent_id, error=str(e),
                )

        if primary_result is None:
            raise RegistryClientError("Registration failed on all registries")
        return primary_result

    def heartbeat_all(self, agent_id: str) -> None:
        """Send heartbeat to ALL reachable registries."""
        for url in self._urls:
            try:
                resp = httpx.post(
                    f"{url}/v1/mesh/heartbeat",
                    json={"agent_id": agent_id},
                    headers=self._headers(),
                    timeout=self._failover_timeout,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.warning(
                    "multi_registry_heartbeat_failed",
                    registry=url, agent_id=agent_id, error=str(e),
                )

    def deregister_all(self, agent_id: str, sidecar_url: str | None = None) -> None:
        """Deregister from ALL registries."""
        for url in self._urls:
            payload: dict[str, Any] = {"agent_id": agent_id}
            if sidecar_url:
                payload["sidecar_url"] = sidecar_url
            try:
                resp = httpx.post(
                    f"{url}/v1/mesh/deregister",
                    json=payload,
                    headers=self._headers(),
                    timeout=self._failover_timeout,
                )
                resp.raise_for_status()
                logger.info("registry_deregistered", agent_id=agent_id, registry=url)
            except Exception as e:
                logger.warning(
                    "multi_registry_deregister_failed",
                    registry=url, agent_id=agent_id, error=str(e),
                )

    # -----------------------------------------------------------------
    # Discovery
    # -----------------------------------------------------------------

    def discover(
        self,
        skill: str,
        sovereignty_zone: Optional[str] = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Discover agents by skill.

        Returns a list of agent dicts with sidecar_url, name, etc.
        Uses a local cache with configurable TTL.
        """
        cache_key = f"{skill}:{sovereignty_zone or ''}"

        if use_cache and cache_key in self._discovery_cache:
            agents, expiry = self._discovery_cache[cache_key]
            if time.time() < expiry:
                record_discovery_cache(hit=True)
                return agents

        params: dict[str, str] = {}
        if skill:
            params["skill"] = skill
        if sovereignty_zone:
            params["sovereignty_zone"] = sovereignty_zone

        try:
            resp = self._request("GET", "/discover", params=params)
            resp.raise_for_status()
            data = resp.json()
            agents = data.get("agents", [])

            # Cache result
            record_discovery_cache(hit=False)
            self._discovery_cache[cache_key] = (agents, time.time() + self._cache_ttl)

            return agents

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            # Return stale cache if available
            if cache_key in self._discovery_cache:
                logger.warning("discovery_failed_using_cache", skill=skill, error=str(e))
                return self._discovery_cache[cache_key][0]
            logger.error("discovery_failed", skill=skill, error=str(e))
            raise RegistryClientError(f"Discovery failed: {e}") from e

    async def resolve_destination(self, skill: str) -> tuple[str, str]:
        """Resolve a skill to a destination sidecar URL and agent name.

        This is the async callable passed to handle_outbound_request.

        Returns:
            (sidecar_url, agent_name)

        Raises:
            RegistryClientError: If no agent found for the skill.
        """
        agents = self.discover(skill)
        if not agents:
            raise RegistryClientError(f"No agent found for skill '{skill}'")

        # Use the first healthy agent
        agent = agents[0]
        return agent["sidecar_url"], agent["name"]

    async def resolve_destinations(
        self,
        skill: str,
        load_balancer: Any = None,
        context: dict | None = None,
    ) -> list[tuple[str, str]]:
        """Resolve a skill to an ordered list of destination (url, name) pairs.

        Returns all matching agents ordered by status (healthy first) and
        failover_priority, for use by the failover routing logic.
        If a load_balancer is provided, it reorders the destinations.

        Returns:
            List of (sidecar_url, agent_name) tuples.

        Raises:
            RegistryClientError: If no agents found for the skill.
        """
        agents = self.discover(skill)
        if not agents:
            raise RegistryClientError(f"No agent found for skill '{skill}'")

        destinations = [(a["sidecar_url"], a["name"]) for a in agents]

        if load_balancer is not None:
            destinations = load_balancer.select(destinations, context)

        return destinations

    def set_cache_ttl(self, ttl_seconds: float) -> None:
        """Update the discovery cache TTL."""
        self._cache_ttl = ttl_seconds

    def clear_cache(self) -> None:
        """Clear the discovery cache."""
        self._discovery_cache.clear()

    # -----------------------------------------------------------------
    # Policies
    # -----------------------------------------------------------------

    def fetch_policies(self) -> list[PolicyRule]:
        """Fetch current authorisation policies from the registry."""
        try:
            resp = self._request("GET", "/policies")
            resp.raise_for_status()
            data = resp.json()

            self._policies = self._parse_policies(data.get("policies", []))
            return self._policies

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("policy_fetch_failed", error=str(e))
            if self._policies is not None:
                logger.info("using_cached_policies", count=len(self._policies))
                return self._policies
            raise RegistryClientError(f"Policy fetch failed: {e}") from e

    @property
    def cached_policies(self) -> list[PolicyRule] | None:
        """Return the currently cached policies."""
        return self._policies

    @staticmethod
    def _parse_policies(raw_policies: list[dict]) -> list[PolicyRule]:
        """Parse policy dicts from registry into PolicyRule objects."""
        return [
            PolicyRule(
                source=p["source"],
                destination=p["destination"],
                action=PolicyAction(p["action"]),
                priority=p.get("priority", 0),
            )
            for p in raw_policies
        ]

    # -----------------------------------------------------------------
    # Compliance rules
    # -----------------------------------------------------------------

    def fetch_compliance_rules(self) -> dict:
        """Fetch compliance rules (sovereignty + classification) from the registry.

        Returns:
            Dict with 'sovereignty_rules' and 'classification_rules' lists.
        """
        try:
            resp = self._request("GET", "/compliance-rules")
            resp.raise_for_status()
            data = resp.json()

            self._compliance_rules = data
            return data

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("compliance_rules_fetch_failed", error=str(e))
            if hasattr(self, '_compliance_rules') and self._compliance_rules is not None:
                logger.info("using_cached_compliance_rules")
                return self._compliance_rules
            raise RegistryClientError(f"Compliance rules fetch failed: {e}") from e

    @property
    def cached_compliance_rules(self) -> dict | None:
        """Return currently cached compliance rules."""
        return getattr(self, '_compliance_rules', None)

    # -----------------------------------------------------------------
    # Consent
    # -----------------------------------------------------------------

    def fetch_consent(
        self,
        data_subject_id: str,
        consent_type: str = "processing",
    ) -> dict[str, Any]:
        """Query consent status for a data subject.

        Returns:
            Dict with 'has_active_consent' bool and 'consents' list.
        """
        cache_key = f"consent:{data_subject_id}:{consent_type}"

        # Check cache
        if cache_key in self._discovery_cache:
            result, expiry = self._discovery_cache[cache_key]
            if time.time() < expiry:
                return result[0] if result else {"has_active_consent": False, "consents": []}

        try:
            resp = self._request(
                "GET",
                f"/consent/{data_subject_id}",
                params={"consent_type": consent_type},
            )
            resp.raise_for_status()
            data = resp.json()

            # Cache with consent TTL (reuse discovery cache structure)
            self._discovery_cache[cache_key] = ([data], time.time() + 300)
            return data

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("consent_fetch_failed", subject=data_subject_id, error=str(e))
            # Return stale cache if available
            if cache_key in self._discovery_cache:
                result, _ = self._discovery_cache[cache_key]
                return result[0] if result else {"has_active_consent": False, "consents": []}
            return {"has_active_consent": False, "consents": []}

    # -----------------------------------------------------------------
    # Agent governance status
    # -----------------------------------------------------------------

    def fetch_agent_status(self, agent_name: str) -> str | None:
        """Look up an agent's governance status by name.

        Uses the existing /v1/mesh/agents/lookup endpoint which returns
        agent_id, name, and status.  Cached with discovery TTL.

        Returns:
            Status string (e.g. "active", "draft") or None if not found.
        """
        cache_key = f"agent_status:{agent_name}"

        if cache_key in self._discovery_cache:
            result, expiry = self._discovery_cache[cache_key]
            if time.time() < expiry:
                return result[0] if result else None

        try:
            resp = self._request(
                "GET",
                "/agents/lookup",
                params={"name": agent_name},
            )
            if resp.status_code != 200:
                logger.warning("agent_status_lookup_failed",
                               name=agent_name, status=resp.status_code)
                # Return stale cache if available
                if cache_key in self._discovery_cache:
                    result, _ = self._discovery_cache[cache_key]
                    return result[0] if result else None
                return None

            status = resp.json().get("status")
            self._discovery_cache[cache_key] = ([status], time.time() + self._cache_ttl)
            return status

        except RegistryClientError as e:
            logger.warning("agent_status_lookup_error", name=agent_name, error=str(e))
            if cache_key in self._discovery_cache:
                result, _ = self._discovery_cache[cache_key]
                return result[0] if result else None
            return None

    # -----------------------------------------------------------------
    # Tool governance
    # -----------------------------------------------------------------

    def fetch_tools_for_agent(self, agent_name: str) -> list[dict]:
        """Fetch approved tools assigned to this agent.

        Calls GET /v1/mesh/tools/for-agent?agent_name=X and caches the result.
        """
        try:
            resp = self._request(
                "GET",
                "/tools/for-agent",
                params={"agent_name": agent_name},
            )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._cached_tools = tools
            logger.info("tools_fetched", agent_name=agent_name, count=len(tools))
            return tools

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("tools_fetch_failed", agent_name=agent_name, error=str(e))
            if hasattr(self, '_cached_tools') and self._cached_tools is not None:
                logger.info("using_cached_tools", count=len(self._cached_tools))
                return self._cached_tools
            return []

    def fetch_egress_rules_for_agent(self, agent_name: str) -> list[dict]:
        """Fetch egress rules matching this agent.

        Calls GET /v1/mesh/egress-rules/for-agent?agent_name=X and caches the result.
        """
        try:
            resp = self._request(
                "GET",
                "/egress-rules/for-agent",
                params={"agent_name": agent_name},
            )
            resp.raise_for_status()
            data = resp.json()
            rules = data.get("rules", [])
            self._cached_egress_rules = rules
            logger.info("egress_rules_fetched", agent_name=agent_name, count=len(rules))
            return rules

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("egress_rules_fetch_failed", agent_name=agent_name, error=str(e))
            if hasattr(self, '_cached_egress_rules') and self._cached_egress_rules is not None:
                logger.info("using_cached_egress_rules", count=len(self._cached_egress_rules))
                return self._cached_egress_rules
            return []

    @property
    def cached_tools(self) -> list[dict] | None:
        """Return currently cached tools for this agent."""
        return getattr(self, '_cached_tools', None)

    @property
    def cached_egress_rules(self) -> list[dict] | None:
        """Return currently cached egress rules for this agent."""
        return getattr(self, '_cached_egress_rules', None)

    # -----------------------------------------------------------------
    # Guardrails
    # -----------------------------------------------------------------

    def fetch_guardrails_for_agent(self, agent_name: str) -> list[dict]:
        """Fetch active guardrails for this agent.

        Calls GET /v1/mesh/guardrails/for-agent?agent_name=X and caches the result.
        """
        try:
            resp = self._request(
                "GET",
                "/guardrails/for-agent",
                params={"agent_name": agent_name},
            )
            resp.raise_for_status()
            data = resp.json()
            guardrails = data.get("guardrails", [])
            self._cached_guardrails = guardrails
            logger.info("guardrails_fetched", agent_name=agent_name, count=len(guardrails))
            return guardrails

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("guardrails_fetch_failed", agent_name=agent_name, error=str(e))
            if hasattr(self, '_cached_guardrails') and self._cached_guardrails is not None:
                logger.info("using_cached_guardrails", count=len(self._cached_guardrails))
                return self._cached_guardrails
            return []

    @property
    def cached_guardrails(self) -> list[dict] | None:
        """Return currently cached guardrails for this agent."""
        return getattr(self, '_cached_guardrails', None)

    # -----------------------------------------------------------------
    # Guardrail event shipping
    # -----------------------------------------------------------------

    def ship_guardrail_events(
        self,
        events: list[dict[str, Any]],
        agent_name: str,
    ) -> dict[str, Any]:
        """Ship a batch of guardrail evaluation events to the registry.

        Args:
            events: List of guardrail event dicts from GuardrailEvaluator.drain_events().
            agent_name: Name of the agent producing the events.
        """
        if not events:
            return {"status": "no events", "count": 0}

        # Enrich events with agent_name
        for event in events:
            event["agent_name"] = agent_name

        try:
            resp = self._request("POST", "/guardrail-events", json={"events": events})
            resp.raise_for_status()
            data = resp.json()
            logger.info("guardrail_events_shipped", count=data.get("count", len(events)))
            return data

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("guardrail_events_shipping_failed", count=len(events), error=str(e))
            raise RegistryClientError(f"Guardrail events shipping failed: {e}") from e

    # -----------------------------------------------------------------
    # Audit shipping
    # -----------------------------------------------------------------

    def ship_audit_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Ship a batch of audit records to the registry.

        Args:
            records: List of audit record dicts (serialized AuditRecord).
        """
        if not records:
            return {"status": "no records", "count": 0}

        try:
            resp = self._request("POST", "/audit", json={"records": records})
            resp.raise_for_status()
            data = resp.json()
            logger.info("audit_records_shipped", count=data.get("count", len(records)))
            return data

        except (httpx.HTTPStatusError, RegistryClientError) as e:
            logger.warning("audit_shipping_failed", count=len(records), error=str(e))
            raise RegistryClientError(f"Audit shipping failed: {e}") from e
