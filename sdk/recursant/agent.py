"""High-level Agent abstraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recursant.config import AgentConfig, load_config
from recursant.exceptions import ConfigError


class Agent:
    """High-level representation of an agent for the Recursant registry.

    Can be constructed programmatically or loaded from a YAML config file.
    """

    def __init__(
        self,
        name: str,
        version: str = "0.1.0",
        endpoint_url: str = "",
        endpoint_type: str = "custom",
        classification: str = "internal",
        data_sensitivity: str = "none",
        risk_tier: str = "low",
        description: str = "",
        owner_id: str = "sdk-user",
        team_id: str = "default-team",
        contact_email: str = "sdk@example.com",
        tenant_id: str = "default",
        auth_method: str = "api_key",
        timeout_seconds: int = 30,
        protocol: str = "A2A",
        capabilities: list[dict[str, Any]] | None = None,
        resource_quota: dict[str, Any] | None = None,
    ):
        self.name = name
        self.version = version
        self.endpoint_url = endpoint_url
        self.endpoint_type = endpoint_type
        self.classification = classification
        self.data_sensitivity = data_sensitivity
        self.risk_tier = risk_tier
        self.description = description or f"{name} agent"
        self.owner_id = owner_id
        self.team_id = team_id
        self.contact_email = contact_email
        self.tenant_id = tenant_id
        self.auth_method = auth_method
        self.timeout_seconds = timeout_seconds
        self.protocol = protocol
        self.capabilities = capabilities or [
            {"name": "default", "description": self.description}
        ]
        self.resource_quota = resource_quota

    @classmethod
    def from_config(cls, path: str | Path) -> Agent:
        """Load an Agent from a recursant.yaml config file."""
        cfg = load_config(path)
        if not isinstance(cfg, AgentConfig):
            raise ConfigError(f"Expected kind 'Agent', got '{cfg.kind}'")
        spec = cfg.spec
        return cls(
            name=cfg.metadata.name,
            version=cfg.metadata.version,
            tenant_id=cfg.metadata.tenant,
            endpoint_url=spec.endpoint.url,
            endpoint_type=spec.endpoint.type,
            auth_method=spec.endpoint.auth_method,
            timeout_seconds=spec.endpoint.timeout_seconds,
            protocol=spec.endpoint.protocol,
            classification=spec.classification,
            data_sensitivity=spec.data_sensitivity,
            risk_tier=spec.risk_tier,
            description=spec.description,
            owner_id=spec.owner_id,
            team_id=spec.team_id,
            contact_email=spec.contact_email,
            capabilities=[
                c.model_dump(exclude_none=True) for c in spec.capabilities
            ],
            resource_quota=(
                spec.quotas.model_dump(exclude_none=True) if spec.quotas else None
            ),
        )

    def to_api_payload(self) -> dict[str, Any]:
        """Convert to the registry API create payload."""
        payload: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "owner_id": self.owner_id,
            "team_id": self.team_id,
            "contact_email": self.contact_email,
            "tenant_id": self.tenant_id,
            "classification": self.classification,
            "data_sensitivity": self.data_sensitivity,
            "risk_tier": self.risk_tier,
            "endpoint": {
                "type": self.endpoint_type,
                "url": self.endpoint_url,
                "auth_method": self.auth_method,
                "timeout_ms": self.timeout_seconds * 1000,
                "agent_protocol": self.protocol,
            },
            "capabilities": self.capabilities,
        }
        if self.resource_quota:
            payload["resource_quota"] = self.resource_quota
        return payload
