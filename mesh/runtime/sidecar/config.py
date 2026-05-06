"""Sidecar configuration — loads from recursant-sidecar.yaml."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class TLSConfig(BaseModel):
    """mTLS certificate paths and rotation settings."""

    cert_path: str = Field(description="Path to sidecar certificate (PEM)")
    key_path: str = Field(description="Path to sidecar private key (PEM)")
    ca_path: str = Field(description="Path to CA certificate (PEM)")
    # Certificate auto-rotation
    rotation_enabled: bool = Field(
        default=False,
        description="Enable automatic certificate rotation",
    )
    rotation_check_interval_seconds: int = Field(
        default=3600,
        description="How often to check certificate expiry",
    )
    renewal_days_before_expiry: int = Field(
        default=30,
        description="Renew certificate this many days before expiry",
    )


class AuthenticationConfig(BaseModel):
    """Authentication interceptor config."""

    enabled: bool = True
    schemes: list[str] = Field(default=["mtls", "api_key"])
    api_key: Optional[str] = Field(
        default=None,
        description="Shared API key for dev mode (header X-Sidecar-API-Key)",
    )
    # JWT authentication
    jwt_secret: Optional[str] = Field(
        default=None,
        description="Symmetric HS256 key for JWT verification",
    )
    jwt_public_key_path: Optional[str] = Field(
        default=None,
        description="Path to asymmetric RS256/ES256 public key (PEM)",
    )
    jwt_algorithms: list[str] = Field(
        default=["HS256"],
        description="Allowed JWT algorithms",
    )
    jwt_issuer: Optional[str] = Field(
        default=None,
        description="Required 'iss' claim in JWT",
    )
    jwt_audience: Optional[str] = Field(
        default=None,
        description="Required 'aud' claim in JWT",
    )
    jwt_agent_claim: str = Field(
        default="sub",
        description="JWT claim containing agent identity",
    )


class FallbackRule(BaseModel):
    """Static fallback authorisation rule."""

    source: str = Field(description="Source agent name or '*' for any")
    destination: str = Field(description="Destination agent name or '*' for any")
    action: str = Field(description="'allow' or 'deny'")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("allow", "deny"):
            raise ValueError("action must be 'allow' or 'deny'")
        return v


class AuthorisationConfig(BaseModel):
    """Authorisation interceptor config."""

    enabled: bool = True
    default_action: str = Field(default="deny")
    fallback_rules: list[FallbackRule] = Field(default_factory=list)

    @field_validator("default_action")
    @classmethod
    def validate_default_action(cls, v: str) -> str:
        if v not in ("allow", "deny"):
            raise ValueError("default_action must be 'allow' or 'deny'")
        return v


class AuditConfig(BaseModel):
    """Audit logging interceptor config."""

    enabled: bool = True
    log_file: Optional[str] = Field(
        default=None,
        description="Path to audit log file. None = stdout only.",
    )
    flush_interval_seconds: int = Field(
        default=5,
        description="How often to flush buffered audit records to the registry",
    )


class ComplianceConfig(BaseModel):
    """Compliance interceptor config — sovereignty and classification enforcement."""

    enabled: bool = True
    default_action: str = Field(
        default="block",
        description="Default action when no rule matches: 'block' or 'warn'",
    )
    sovereignty_rules: list[dict] = Field(
        default_factory=list,
        description="List of {source_zone, dest_zone, action} rules",
    )
    classification_rules: list[dict] = Field(
        default_factory=list,
        description="List of {min_classification, max_dest_classification, action} rules",
    )
    # GDPR consent enforcement
    consent_enforcement: bool = Field(
        default=False,
        description="If true, block PII flows when no active consent exists for the data subject",
    )
    consent_cache_ttl_seconds: int = Field(
        default=300,
        description="TTL for cached consent lookups",
    )

    @field_validator("default_action")
    @classmethod
    def validate_compliance_default(cls, v: str) -> str:
        if v not in ("block", "warn"):
            raise ValueError("default_action must be 'block' or 'warn'")
        return v


class RedactionConfig(BaseModel):
    """PII redaction interceptor config."""

    enabled: bool = True
    mode: str = Field(
        default="redact",
        description="Mode: 'redact' (replace PII), 'block' (reject on PII), 'warn' (log only)",
    )
    custom_patterns: dict[str, str] = Field(
        default_factory=dict,
        description="Custom regex patterns: {name: pattern}",
    )
    # PII detection backend
    backend: str = Field(
        default="regex",
        description="PII detection backend: 'regex' (default) or 'presidio' (ML-based NER)",
    )
    presidio_score_threshold: float = Field(
        default=0.5,
        description="Minimum confidence score for Presidio detections (0.0-1.0)",
    )
    presidio_entities: list[str] = Field(
        default_factory=list,
        description="Presidio entity types to detect (empty = all defaults)",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("redact", "block", "warn"):
            raise ValueError("mode must be 'redact', 'block', or 'warn'")
        return v

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in ("regex", "presidio"):
            raise ValueError("backend must be 'regex' or 'presidio'")
        return v


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker settings."""

    failure_threshold: int = Field(default=5, description="Consecutive failures before opening")
    recovery_timeout_seconds: int = Field(default=30, description="Seconds before half-open probe")
    # Connection pool limits (Istio-style)
    max_connections: int = Field(
        default=100,
        description="Max concurrent TCP connections per destination",
    )
    max_pending_requests: int = Field(
        default=100,
        description="Max requests queued waiting for a connection",
    )
    max_requests_per_connection: int = Field(
        default=0,
        description="Recycle connections after N requests (0 = unlimited)",
    )


class RetryConfig(BaseModel):
    """Retry policy settings."""

    max_attempts: int = Field(default=3, description="Max retry attempts")
    backoff_base_seconds: float = Field(default=1.0, description="Base backoff interval")
    backoff_max_seconds: float = Field(default=30.0, description="Max backoff interval")


class ResilienceConfig(BaseModel):
    """Resilience config — circuit breaker + retry."""

    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)


class TelemetryConfig(BaseModel):
    """OpenTelemetry tracing and metrics config."""

    enabled: bool = False
    otlp_endpoint: str = Field(default="http://localhost:4317", description="OTLP exporter endpoint")
    service_name: str = Field(default="recursant-sidecar", description="Service name for traces")
    sample_rate: float = Field(default=1.0, description="Trace sample rate (0.0 to 1.0)")
    prometheus_enabled: bool = Field(default=False, description="Enable Prometheus /metrics endpoint")


class LoadBalancingConfig(BaseModel):
    """Load balancing algorithm config."""

    algorithm: str = Field(
        default="round-robin",
        description="Algorithm: round-robin, random, least-requests, consistent-hash",
    )
    consistent_hash_key: str = Field(
        default="source_agent",
        description="Key for consistent hashing (source_agent, skill, task_id)",
    )

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        valid = {"round-robin", "random", "least-requests", "consistent-hash"}
        if v not in valid:
            raise ValueError(f"algorithm must be one of {valid}")
        return v


class TrafficSplitRule(BaseModel):
    """A single traffic split rule for a skill."""

    skill: str = Field(description="Skill to match")
    destinations: list[dict] = Field(
        description="List of {agent_name: str, weight: int}",
    )


class TrafficSplitConfig(BaseModel):
    """Traffic splitting (weighted routing) config."""

    enabled: bool = False
    rules: list[TrafficSplitRule] = Field(default_factory=list)


class GrpcConfig(BaseModel):
    """gRPC config sync settings."""

    enabled: bool = True
    control_plane_url: str = Field(default="localhost:50051", description="gRPC control plane address")
    fallback_to_rest: bool = Field(default=True, description="Fall back to REST polling if gRPC fails")


class RateLimitingConfig(BaseModel):
    """Rate limiting interceptor config — token bucket per source agent."""

    enabled: bool = True
    default_requests_per_minute: int = Field(
        default=60,
        description="Default RPM limit per source agent",
    )
    burst_multiplier: float = Field(
        default=1.5,
        description="Burst capacity as multiplier of per-second rate",
    )
    per_agent_overrides: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Per-agent RPM overrides: {agent_name: {requests_per_minute: N}}",
    )


class DelayFaultConfig(BaseModel):
    """Delay fault injection config."""

    enabled: bool = False
    fixed_delay_ms: int = Field(default=1000, description="Delay in milliseconds")
    percentage: float = Field(default=100.0, description="Percentage of requests affected (0-100)")


class AbortFaultConfig(BaseModel):
    """Abort fault injection config."""

    enabled: bool = False
    http_status: int = Field(default=503, description="HTTP status code for abort")
    percentage: float = Field(default=100.0, description="Percentage of requests affected (0-100)")


class FaultInjectionConfig(BaseModel):
    """Fault injection interceptor config for chaos testing."""

    enabled: bool = False
    delay: DelayFaultConfig = Field(default_factory=DelayFaultConfig)
    abort: AbortFaultConfig = Field(default_factory=AbortFaultConfig)
    match_source: Optional[str] = Field(default=None, description="Only inject for this source agent")
    match_destination: Optional[str] = Field(default=None, description="Only inject for this destination agent")
    match_direction: Optional[str] = Field(default=None, description="Only inject for this direction (inbound/outbound)")


class GuardrailConfig(BaseModel):
    """Guardrail interceptor config."""

    enabled: bool = True
    sync_interval_seconds: int = Field(
        default=30,
        description="How often to sync guardrails from registry",
    )
    llm_timeout_ms: int = Field(
        default=5000,
        description="Default timeout for LLM judge calls",
    )
    weaviate_url: str = Field(
        default="http://weaviate:8080",
        description="Weaviate URL for vector_lookup guardrails",
    )
    weaviate_timeout_ms: int = Field(
        default=2000,
        description="Timeout for Weaviate queries",
    )
    max_consecutive_errors: int = Field(
        default=5,
        description="Auto-disable a guardrail after N consecutive evaluation errors",
    )


class CoTAuditConfig(BaseModel):
    """Chain-of-thought auditing configuration."""

    enabled: bool = False
    provider: str = Field(
        default="anthropic",
        description="LLM provider for CoT analysis",
    )
    model: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Model to use for CoT LLM analysis",
    )
    max_tokens: int = Field(
        default=512,
        description="Max tokens for LLM analysis response",
    )
    timeout_ms: int = Field(
        default=10000,
        description="Timeout for LLM CoT analysis",
    )
    risk_threshold: str = Field(
        default="medium",
        description="Minimum risk level to flag (none/low/medium/high/critical)",
    )
    analyze_tool_calls: bool = Field(
        default=True,
        description="Analyze tool calls for unauthorized usage",
    )
    analyze_retrieval: bool = Field(
        default=True,
        description="Analyze retrieved documents for injection",
    )
    analyze_decision_points: bool = Field(
        default=True,
        description="Analyze reasoning traces for manipulation",
    )


class InterceptorsConfig(BaseModel):
    """Configuration for all interceptors."""

    authentication: AuthenticationConfig = Field(
        default_factory=AuthenticationConfig,
    )
    authorisation: AuthorisationConfig = Field(
        default_factory=AuthorisationConfig,
    )
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rate_limiting: RateLimitingConfig = Field(default_factory=RateLimitingConfig)
    fault_injection: FaultInjectionConfig = Field(default_factory=FaultInjectionConfig)
    guardrails: GuardrailConfig = Field(default_factory=GuardrailConfig)
    cot_audit: CoTAuditConfig = Field(default_factory=CoTAuditConfig)


class SidecarConfig(BaseModel):
    """Top-level sidecar configuration.

    Loaded from recursant-sidecar.yaml. All fields have sensible defaults
    so a minimal config file works for local development.
    """

    # Networking
    port: int = Field(
        default=9901,
        description="Local proxy port (agent → sidecar)",
    )
    a2a_port: int = Field(
        default=8443,
        description="External A2A-facing port (sidecar ↔ sidecar, mTLS)",
    )
    agent_port: int = Field(
        default=5010,
        description="Port of the local agent process to proxy to",
    )
    agent_host: str = Field(
        default="localhost",
        description="Hostname of the local agent process (for Docker: service name)",
    )

    # Registry (control plane)
    registry_url: str = Field(
        default="http://localhost:5000",
        description="Recursant registry REST API base URL",
    )
    registry_urls: list[str] = Field(
        default_factory=list,
        description="Ordered list of registry URLs (primary first). "
                    "Falls back to registry_url if empty.",
    )
    registry_failover_timeout: float = Field(
        default=3.0,
        description="Seconds before failing over to next registry URL",
    )
    registry_api_key: Optional[str] = Field(
        default=None,
        description="API key for authenticating to the registry (X-Mesh-API-Key)",
    )

    # Agent identity
    agent_card_path: str = Field(
        default="./agent_card.yaml",
        description="Path to the local agent_card.yaml",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Agent UUID in the registry. Required for mesh registration.",
    )

    # Logging
    log_level: LogLevel = Field(default=LogLevel.INFO)

    # Interceptors
    interceptors: InterceptorsConfig = Field(
        default_factory=InterceptorsConfig,
    )

    # TLS
    tls: Optional[TLSConfig] = Field(
        default=None,
        description="mTLS config. None = TLS disabled (dev mode).",
    )

    # Resilience
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)

    # Telemetry
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    # Load balancing
    load_balancing: LoadBalancingConfig = Field(default_factory=LoadBalancingConfig)

    # Traffic splitting
    traffic_split: TrafficSplitConfig = Field(default_factory=TrafficSplitConfig)

    # gRPC
    grpc: GrpcConfig = Field(default_factory=GrpcConfig)

    # Co-located agents — agents sharing this pod that can be routed locally
    local_agents: dict[str, int] = Field(
        default_factory=dict,
        description="Map of agent_name → agent_port for co-located agents in the same pod. "
                    "Populated from the injection annotation. Enables governed local routing "
                    "so intra-pod agent calls still pass through the interceptor pipeline.",
    )

    # Sync intervals
    heartbeat_interval_seconds: int = Field(
        default=30,
        description="How often to send heartbeat to registry",
    )
    policy_sync_interval_seconds: int = Field(
        default=30,
        description="How often to fetch policies from registry",
    )
    tool_sync_interval_seconds: int = Field(
        default=30,
        description="How often to fetch tool assignments and egress rules from registry",
    )
    discovery_cache_ttl_seconds: int = Field(
        default=60,
        description="TTL for cached discovery results",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> SidecarConfig:
        """Load config from a YAML file.

        The YAML is expected to have an optional top-level `recursant.sidecar`
        key (matching the spec), but a flat structure is also accepted.
        """
        path = Path(path)
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        # Support nested `recursant.sidecar` key or flat structure
        if "recursant" in raw and "sidecar" in raw["recursant"]:
            data = raw["recursant"]["sidecar"]
        elif "sidecar" in raw:
            data = raw["sidecar"]
        else:
            data = raw

        return cls.model_validate(data)

    @classmethod
    def from_env(cls) -> SidecarConfig:
        """Load config from environment variables (for Docker).

        Env vars are prefixed with SIDECAR_ and uppercased, e.g.:
        SIDECAR_PORT=9901, SIDECAR_REGISTRY_URL=http://registry:5000
        SIDECAR_REGISTRY_URLS=http://reg1:5000,http://reg2:5000
        """
        import os

        data: dict = {}
        prefix = "SIDECAR_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                field_name = key[len(prefix) :].lower()
                # Parse comma-separated registry_urls into a list
                if field_name == "registry_urls" and isinstance(value, str):
                    data[field_name] = [u.strip() for u in value.split(",") if u.strip()]
                else:
                    data[field_name] = value

        return cls.model_validate(data)
