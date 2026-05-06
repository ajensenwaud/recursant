"""Deploy workflow — register + submit agent through governance pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recursant.agent import Agent
from recursant.client import RecursantClient
from recursant.client._models import AgentResponse
from recursant.exceptions import ConflictError, NotFoundError


@dataclass
class DeployResult:
    """Result of a deploy operation."""

    agent: AgentResponse
    created: bool = False
    updated: bool = False
    submitted: bool = False
    errors: list[str] = field(default_factory=list)


def deploy(
    agent: Agent,
    registry_url: str,
    *,
    submit: bool = True,
    username: str | None = None,
    password: str | None = None,
    api_key: str | None = None,
    tenant_id: str | None = None,
) -> DeployResult:
    """Register an agent and optionally submit it through the governance pipeline.

    Idempotent: creates the agent if it doesn't exist, updates if it does.
    """
    effective_tenant = tenant_id or agent.tenant_id

    with RecursantClient(
        registry_url,
        username=username,
        password=password,
        api_key=api_key,
        tenant_id=effective_tenant,
    ) as client:
        payload = agent.to_api_payload()
        created = False
        updated = False

        # Try to find existing agent by name
        existing = _find_agent_by_name(client, agent.name)

        if existing:
            # Update existing agent — remove 'name' as it's not allowed in updates
            update_payload = {k: v for k, v in payload.items() if k not in ("name", "tenant_id")}
            agent_resp = client.agents.update(str(existing.id), **update_payload)
            updated = True
        else:
            # Create new agent
            try:
                agent_resp = client.agents.create(**payload)
                created = True
            except ConflictError:
                # Race condition: was created between check and create
                existing = _find_agent_by_name(client, agent.name)
                if existing:
                    update_payload = {k: v for k, v in payload.items() if k not in ("name", "tenant_id")}
                    agent_resp = client.agents.update(str(existing.id), **update_payload)
                    updated = True
                else:
                    raise

        result = DeployResult(agent=agent_resp, created=created, updated=updated)

        # Submit if requested and agent is in DRAFT status
        if submit and agent_resp.status == "draft":
            try:
                agent_resp = client.agents.submit(str(agent_resp.id))
                result.agent = agent_resp
                result.submitted = True
            except Exception as exc:
                result.errors.append(f"Submit failed: {exc}")

        return result


def _find_agent_by_name(client: RecursantClient, name: str) -> AgentResponse | None:
    """Look up an agent by name, returning None if not found."""
    try:
        paginated = client.agents.list(name=name)
        for a in paginated.agents:
            if a.name == name:
                # Fetch full details
                return client.agents.get(str(a.id))
    except (NotFoundError, Exception):
        pass
    return None
