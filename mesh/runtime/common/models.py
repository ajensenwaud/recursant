"""Shared Pydantic models for the Recursant mesh runtime."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InterceptorAction(str, enum.Enum):
    """What an interceptor decided to do."""

    PASS = "pass"
    BLOCK = "block"
    MODIFY = "modify"


class InterceptorDecision(BaseModel):
    """Result of a single interceptor processing a message."""

    interceptor: str = Field(description="Name of the interceptor")
    action: InterceptorAction
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason for block/modify",
    )
    modified_payload: Optional[dict[str, Any]] = Field(
        default=None,
        description="Modified message payload (only if action=modify)",
    )
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional details (e.g. triggered_spans for guardrails)",
    )


class Direction(str, enum.Enum):
    """Whether a message is arriving or departing."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class InterceptorContext(BaseModel):
    """Context passed through the interceptor pipeline."""

    direction: Direction
    a2a_method: str = Field(description="A2A JSON-RPC method, e.g. 'message/send'")
    payload: dict[str, Any] = Field(description="A2A message payload")
    source_agent_id: Optional[str] = Field(default=None)
    source_agent_name: Optional[str] = Field(default=None)
    dest_agent_id: Optional[str] = Field(default=None)
    dest_agent_name: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    client_cert_cn: Optional[str] = Field(
        default=None,
        description="Common Name from client mTLS certificate",
    )
    client_cert_sans: list[str] = Field(
        default_factory=list,
        description="Subject Alternative Names from client cert",
    )
    # Compliance context — populated from discovery cache
    source_sovereignty_zone: Optional[str] = Field(default=None)
    dest_sovereignty_zone: Optional[str] = Field(default=None)
    source_classification: Optional[str] = Field(default=None)
    dest_classification: Optional[str] = Field(default=None)


class AuditRecord(BaseModel):
    """Immutable audit record for a single A2A interaction."""

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    source_agent_id: Optional[str] = None
    source_agent_name: Optional[str] = None
    dest_agent_id: Optional[str] = None
    dest_agent_name: Optional[str] = None
    task_id: Optional[str] = None
    a2a_method: str
    message_hash: str = Field(description="SHA-256 hex digest of the message payload")
    direction: Direction
    interceptor_decisions: list[InterceptorDecision] = Field(default_factory=list)
    decision: str = Field(description="Overall decision: 'pass' or 'block'")
    outcome: str = Field(description="'success', 'blocked', or 'error'")
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional context (error messages, etc.)",
    )
    sidecar_id: Optional[str] = None
    # Hash-chain fields for tamper-evident audit logs
    record_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of this record (including previous_record_hash)",
    )
    previous_record_hash: Optional[str] = Field(
        default=None,
        description="record_hash of the preceding record in the chain",
    )
    sequence_number: Optional[int] = Field(
        default=None,
        description="Monotonically increasing per-sidecar sequence number",
    )
    # Chain-of-thought audit fields (extracted for indexing/filtering)
    cot_risk_level: Optional[str] = Field(
        default=None,
        description="CoT risk level: none, low, medium, high, critical",
    )
    cot_flags: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="CoT analysis flags (issues found in reasoning trace)",
    )


class PolicyAction(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class PolicyRule(BaseModel):
    """An authorisation rule: which agents can talk to which."""

    id: Optional[str] = None
    source: str = Field(description="Source agent name or '*' for any")
    destination: str = Field(description="Destination agent name or '*' for any")
    action: PolicyAction
    priority: int = Field(
        default=0,
        description="Lower number = higher priority",
    )


class MeshAgent(BaseModel):
    """An agent discovered via the registry mesh API."""

    agent_id: str
    name: str
    sidecar_url: str
    skills: list[str] = Field(default_factory=list)
    version: str
    status: str = "healthy"
    last_heartbeat: Optional[datetime] = None
    sovereignty_zone: Optional[str] = None
    classification: Optional[str] = Field(default=None)
    failover_priority: int = Field(default=0)
