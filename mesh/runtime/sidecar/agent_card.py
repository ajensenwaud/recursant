"""Agent Card loading, enrichment, and serving.

Loads a human-friendly agent_card.yaml, converts it to an A2A SDK AgentCard,
and enriches it with Recursant governance metadata.

Targets a2a-sdk 1.0.x (protobuf-based types). The 0.x → 1.x rewrite moved
URLs into the repeated `supported_interfaces` field, made `SecurityScheme`
a protobuf oneof, renamed `security` to `security_requirements`, and made
extension params a google.protobuf.Struct.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    MutualTlsSecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct

RECURSANT_EXTENSION_URI = "urn:recursant:mesh:sidecar"
SIDECAR_VERSION = "0.1.0"


def load_agent_card_yaml(path: str | Path) -> dict[str, Any]:
    """Load raw agent card data from a YAML file."""
    path = Path(path)
    with open(path) as f:
        return yaml.safe_load(f) or {}


def build_agent_card(
    raw: dict[str, Any],
    sidecar_url: str,
    registry_url: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> AgentCard:
    """Build an A2A AgentCard from raw YAML data.

    Args:
        raw: Parsed YAML dict from agent_card.yaml.
        sidecar_url: The external URL where this sidecar serves A2A
                     (e.g. "https://host-a:8443").
        registry_url: Registry control plane URL (for extension metadata).
        tenant_id: Tenant identifier (for extension metadata).
    """
    skills = [
        AgentSkill(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            tags=s.get("tags", []),
            examples=s.get("examples") or [],
            input_modes=s.get("input_modes") or [],
            output_modes=s.get("output_modes") or [],
        )
        for s in raw.get("skills", [])
    ]

    extensions = _build_extensions(registry_url, tenant_id)
    capabilities = AgentCapabilities(
        streaming=raw.get("capabilities", {}).get("streaming", False),
        push_notifications=raw.get("capabilities", {}).get(
            "push_notifications", False
        ),
        extensions=extensions or [],
    )

    provider = None
    if "provider" in raw:
        p = raw["provider"]
        provider = AgentProvider(
            organization=p.get("organization", p.get("name", "Unknown")),
            url=p.get("url", ""),
        )

    interfaces = [AgentInterface(url=sidecar_url)]

    security_schemes = _build_security_schemes(raw.get("security_schemes", {}))
    security_requirements = _build_security_requirements(raw.get("security", []))

    kwargs: dict[str, Any] = dict(
        name=raw["name"],
        description=raw.get("description", ""),
        version=raw.get("version", "0.0.0"),
        supported_interfaces=interfaces,
        skills=skills,
        capabilities=capabilities,
        default_input_modes=raw.get("default_input_modes", ["text"]),
        default_output_modes=raw.get("default_output_modes", ["text"]),
    )
    if provider is not None:
        kwargs["provider"] = provider
    if security_schemes:
        kwargs["security_schemes"] = security_schemes
    if security_requirements:
        kwargs["security_requirements"] = security_requirements

    return AgentCard(**kwargs)


def _build_security_schemes(
    raw_schemes: dict[str, Any],
) -> dict[str, SecurityScheme]:
    """Convert YAML security scheme definitions to A2A 1.0.x types.

    Only mutualTLS is currently mapped; other schemes (apiKey, oauth2, etc.)
    can be added by populating the corresponding oneof field on SecurityScheme.
    """
    schemes: dict[str, SecurityScheme] = {}
    for name, definition in (raw_schemes or {}).items():
        scheme_type = definition.get("type", "")
        if scheme_type == "mutualTLS":
            schemes[name] = SecurityScheme(
                mtls_security_scheme=MutualTlsSecurityScheme(
                    description=definition.get("description") or "",
                )
            )
    return schemes


def _build_security_requirements(
    raw_requirements: list[Any],
) -> list[SecurityRequirement]:
    """Convert YAML security requirements to A2A 1.0.x SecurityRequirement.

    YAML shape: `[{scheme_name: [scope1, scope2]}, ...]`
    Maps each entry to a SecurityRequirement(schemes={name: StringList(list=scopes)}).
    """
    requirements: list[SecurityRequirement] = []
    for entry in raw_requirements or []:
        if not isinstance(entry, dict):
            continue
        schemes = {
            name: StringList(list=list(scopes or []))
            for name, scopes in entry.items()
        }
        if schemes:
            requirements.append(SecurityRequirement(schemes=schemes))
    return requirements


def _build_extensions(
    registry_url: Optional[str],
    tenant_id: Optional[str],
) -> list[AgentExtension]:
    """Build Recursant governance extension metadata."""
    raw_params: dict[str, Any] = {
        "sidecar_version": SIDECAR_VERSION,
    }
    if registry_url:
        raw_params["registry_url"] = registry_url
    if tenant_id:
        raw_params["tenant_id"] = tenant_id

    params = Struct()
    params.update(raw_params)

    return [
        AgentExtension(
            uri=RECURSANT_EXTENSION_URI,
            description="Recursant mesh sidecar governance metadata",
            required=False,
            params=params,
        )
    ]


def agent_card_to_json(card: AgentCard) -> dict[str, Any]:
    """Serialize an AgentCard to a JSON-compatible dict for serving."""
    return MessageToDict(card, preserving_proto_field_name=True)
