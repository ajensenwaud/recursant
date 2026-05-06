"""YAML config loader and Pydantic validation for recursant.yaml / registry-config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from recursant.exceptions import ConfigError


# ── Agent Config (recursant.yaml) ────────────────────────────────────────

class EndpointConfig(BaseModel):
    url: str
    type: str = "custom"
    auth_method: str = "api_key"
    timeout_seconds: int = 30
    protocol: str = "A2A"


class CapabilityConfig(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class QuotaConfig(BaseModel):
    max_tokens_per_request: int | None = None
    max_requests_per_minute: int | None = None
    max_cost_per_day_usd: float | None = None


class AgentSpec(BaseModel):
    classification: str = "internal"
    data_sensitivity: str = "none"
    risk_tier: str = "low"
    endpoint: EndpointConfig
    capabilities: list[CapabilityConfig] = Field(default_factory=list)
    quotas: QuotaConfig | None = None
    owner_id: str = "sdk-user"
    team_id: str = "default-team"
    contact_email: str = "sdk@example.com"
    description: str = ""


class AgentMetadata(BaseModel):
    name: str
    version: str = "0.1.0"
    tenant: str = "default"


class AgentConfig(BaseModel):
    apiVersion: str = "recursant/v1"
    kind: str = "Agent"
    metadata: AgentMetadata
    spec: AgentSpec

    @field_validator("kind")
    @classmethod
    def _kind_must_be_agent(cls, v: str) -> str:
        if v != "Agent":
            raise ValueError(f"Expected kind 'Agent', got '{v}'")
        return v

    def to_api_payload(self) -> dict[str, Any]:
        """Convert to the registry API create/update payload."""
        ep = self.spec.endpoint
        payload: dict[str, Any] = {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "description": self.spec.description or f"{self.metadata.name} agent",
            "owner_id": self.spec.owner_id,
            "team_id": self.spec.team_id,
            "contact_email": self.spec.contact_email,
            "tenant_id": self.metadata.tenant,
            "classification": self.spec.classification,
            "data_sensitivity": self.spec.data_sensitivity,
            "risk_tier": self.spec.risk_tier,
            "endpoint": {
                "type": ep.type,
                "url": ep.url,
                "auth_method": ep.auth_method,
                "timeout_ms": ep.timeout_seconds * 1000,
                "agent_protocol": ep.protocol,
            },
            "capabilities": [
                c.model_dump(exclude_none=True) for c in self.spec.capabilities
            ] or [{"name": "default", "description": self.spec.description or self.metadata.name}],
        }
        if self.spec.quotas:
            payload["resource_quota"] = self.spec.quotas.model_dump(exclude_none=True)
        return payload


# ── Registry Config (registry-config.yaml) ───────────────────────────────

class GuardrailConfig(BaseModel):
    name: str
    type: str = "pre_processing"
    mechanism: str = "regex"
    enforcement: str = "block"
    scope: str = "all_agents"
    priority: int = 0
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class MeshPolicyConfig(BaseModel):
    source: str
    destination: str
    action: str = "allow"
    priority: int = 0


class ComplianceRuleConfig(BaseModel):
    name: str
    type: str  # sovereignty | classification
    source_zone: str | None = None
    source_value: str | None = None
    destination_zone: str | None = None
    dest_value: str | None = None
    action: str = "block"
    priority: int = 0

    @property
    def rule_type(self) -> str:
        return self.type

    @property
    def source(self) -> str:
        return self.source_zone or self.source_value or ""

    @property
    def destination(self) -> str:
        return self.destination_zone or self.dest_value or ""


class RegistryConfigMetadata(BaseModel):
    tenant: str = "default"


class RegistryConfig(BaseModel):
    apiVersion: str = "recursant/v1"
    kind: str = "RegistryConfig"
    metadata: RegistryConfigMetadata = Field(default_factory=RegistryConfigMetadata)
    guardrails: list[GuardrailConfig] = Field(default_factory=list)
    mesh_policies: list[MeshPolicyConfig] = Field(default_factory=list)
    compliance_rules: list[ComplianceRuleConfig] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _kind_must_be_registry(cls, v: str) -> str:
        if v != "RegistryConfig":
            raise ValueError(f"Expected kind 'RegistryConfig', got '{v}'")
        return v


# ── Loader ───────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> AgentConfig | RegistryConfig:
    """Load and validate a YAML config file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must contain a YAML mapping, got {type(raw).__name__}")

    kind = raw.get("kind", "")
    try:
        if kind == "Agent":
            return AgentConfig.model_validate(raw)
        elif kind == "RegistryConfig":
            return RegistryConfig.model_validate(raw)
        else:
            raise ConfigError(f"Unknown config kind: '{kind}'. Expected 'Agent' or 'RegistryConfig'.")
    except Exception as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"Validation failed for {path}: {exc}") from exc


def validate_config(path: str | Path) -> list[str]:
    """Validate a config file and return a list of error messages (empty = valid)."""
    errors: list[str] = []
    try:
        load_config(path)
    except ConfigError as exc:
        errors.append(str(exc))
    return errors
