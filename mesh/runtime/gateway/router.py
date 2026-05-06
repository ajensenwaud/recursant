"""Gateway routing — discovers agents and forwards requests."""

from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog

from runtime.sidecar.client import OutboundClient
from runtime.sidecar.load_balancer import LoadBalancer, RoundRobinBalancer
from runtime.sidecar.registry_client import RegistryClient, RegistryClientError
from runtime.sidecar.resilience import CircuitBreaker, CircuitOpenError, ConnectionPoolExhaustedError

logger = structlog.get_logger()


class GatewayRouter:
    """Routes external requests to mesh agents via discovery and forwarding."""

    def __init__(
        self,
        registry_client: RegistryClient,
        outbound_client: OutboundClient,
        load_balancer: Optional[LoadBalancer] = None,
    ):
        self._registry = registry_client
        self._client = outbound_client
        self._load_balancer = load_balancer or RoundRobinBalancer()

    async def route_to_skill(
        self,
        skill: str,
        message: str,
        source_identity: str = "gateway-client",
    ) -> dict[str, Any]:
        """Route a request to an agent that provides the given skill.

        Discovers agents, applies load balancing, and attempts each
        destination with failover.
        """
        try:
            agents = self._registry.discover(skill)
        except RegistryClientError as e:
            logger.error("gateway_discovery_failed", skill=skill, error=str(e))
            return {"error": f"Discovery failed for skill '{skill}': {e}"}

        if not agents:
            return {"error": f"No agent found for skill '{skill}'"}

        destinations = [(a["sidecar_url"], a["name"]) for a in agents]
        destinations = self._load_balancer.select(destinations, {"source_agent": source_identity, "skill": skill})

        request_id = str(uuid.uuid4())
        params = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": str(uuid.uuid4()),
            }
        }

        last_error = ""
        for url, name in destinations:
            try:
                response = await self._client.send_a2a_request(
                    destination_url=url,
                    method="message/send",
                    params=params,
                    request_id=request_id,
                    source_agent_name=source_identity,
                )
                return response
            except (CircuitOpenError, ConnectionPoolExhaustedError) as e:
                logger.warning("gateway_failover", url=url, error=str(e))
                last_error = str(e)
                continue
            except Exception as e:
                logger.warning("gateway_send_error", url=url, error=str(e))
                last_error = str(e)
                continue

        return {"error": f"All destinations exhausted for skill '{skill}': {last_error}"}

    def list_skills(self) -> list[dict[str, Any]]:
        """List all discoverable skills from the registry."""
        try:
            agents = self._registry.discover("")
            skills = set()
            for agent in agents:
                for skill in agent.get("skills", []):
                    skills.add(skill)
            return [{"skill": s} for s in sorted(skills)]
        except RegistryClientError:
            return []
