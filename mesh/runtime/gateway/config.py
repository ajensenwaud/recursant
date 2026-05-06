"""Ingress Gateway configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    """Top-level ingress gateway configuration."""

    port: int = Field(default=8080, description="Gateway listen port")
    tls_cert_path: Optional[str] = Field(default=None, description="TLS cert for HTTPS termination")
    tls_key_path: Optional[str] = Field(default=None, description="TLS key for HTTPS termination")
    tls_ca_path: Optional[str] = Field(default=None, description="CA cert for mTLS to sidecars")

    registry_url: str = Field(default="http://localhost:5000", description="Registry API URL")
    registry_api_key: Optional[str] = Field(default=None, description="Mesh API key for registry")

    # Authentication for external clients
    auth_api_key: Optional[str] = Field(default=None, description="API key for external clients")
    jwt_secret: Optional[str] = Field(default=None, description="JWT secret for external clients")
    jwt_algorithms: list[str] = Field(default=["HS256"])
    jwt_issuer: Optional[str] = Field(default=None)
    jwt_audience: Optional[str] = Field(default=None)

    # Rate limiting
    rate_limit_rpm: int = Field(default=600, description="Global rate limit (requests per minute)")

    # Logging
    log_level: str = Field(default="info")

    @classmethod
    def from_yaml(cls, path: str | Path) -> GatewayConfig:
        path = Path(path)
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        data = raw.get("gateway", raw)
        return cls.model_validate(data)

    @classmethod
    def from_env(cls) -> GatewayConfig:
        import os
        data: dict = {}
        prefix = "GATEWAY_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                field_name = key[len(prefix):].lower()
                data[field_name] = value
        return cls.model_validate(data)
