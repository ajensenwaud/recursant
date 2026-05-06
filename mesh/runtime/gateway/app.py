"""Flask app factory for the Recursant Ingress Gateway.

Provides:
- POST /a2a/<skill> — route external requests to mesh agents by skill
- GET /agents — list discoverable skills/agents
- GET /healthz, /readyz, /metrics — operational endpoints
"""

from __future__ import annotations

import asyncio
from typing import Optional

from flask import Flask, Response, jsonify, request

from runtime.gateway.config import GatewayConfig
from runtime.gateway.router import GatewayRouter
from runtime.sidecar.client import OutboundClient
from runtime.sidecar.interceptors.rate_limiter import RateLimitingInterceptor, TokenBucket
from runtime.sidecar.load_balancer import create_load_balancer
from runtime.sidecar.registry_client import RegistryClient
from runtime.sidecar.resilience import CircuitBreaker, RetryPolicy
from runtime.sidecar.config import CircuitBreakerConfig, RetryConfig


def create_gateway_app(config: Optional[GatewayConfig] = None) -> Flask:
    """Create and configure the gateway Flask application."""
    if config is None:
        config = GatewayConfig()

    app = Flask(__name__)
    app.config["GATEWAY_CONFIG"] = config

    # Build registry client
    registry_client = RegistryClient(
        registry_url=config.registry_url,
        api_key=config.registry_api_key,
    )

    # Build outbound client with mTLS to sidecars + resilience
    circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
    retry_policy = RetryPolicy(RetryConfig())
    outbound_client = OutboundClient(
        tls_cert_path=config.tls_cert_path,
        tls_key_path=config.tls_key_path,
        tls_ca_path=config.tls_ca_path,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
    )

    # Build load balancer
    load_balancer = create_load_balancer("round-robin")

    # Build router
    router = GatewayRouter(
        registry_client=registry_client,
        outbound_client=outbound_client,
        load_balancer=load_balancer,
    )
    app.config["ROUTER"] = router

    # Rate limiter (global, per source IP)
    rate_bucket = TokenBucket(
        rate=config.rate_limit_rpm / 60.0,
        capacity=config.rate_limit_rpm / 60.0 * 2,  # 2x burst
    )

    # ---------------------------------------------------------------
    # Authentication helpers
    # ---------------------------------------------------------------

    def _authenticate() -> tuple[bool, str]:
        """Authenticate external client. Returns (ok, identity)."""
        # API key check
        if config.auth_api_key:
            api_key = request.headers.get("X-API-Key")
            if api_key == config.auth_api_key:
                return True, "api-key-client"

        # JWT check
        if config.jwt_secret:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    import jwt as pyjwt
                    token = auth_header[7:]
                    claims = pyjwt.decode(
                        token,
                        config.jwt_secret,
                        algorithms=config.jwt_algorithms,
                        issuer=config.jwt_issuer,
                        audience=config.jwt_audience,
                    )
                    return True, claims.get("sub", "jwt-client")
                except Exception:
                    return False, ""

        # If no auth is configured, allow all (dev mode)
        if not config.auth_api_key and not config.jwt_secret:
            return True, "anonymous"

        return False, ""

    # ---------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------

    @app.route("/a2a/<skill>", methods=["POST"])
    def a2a_skill_route(skill):
        """Route an external A2A request to a mesh agent by skill."""
        # Authenticate
        authed, identity = _authenticate()
        if not authed:
            return jsonify({"error": "Authentication required"}), 401

        # Rate limit
        if not rate_bucket.consume():
            return jsonify({"error": "Rate limit exceeded"}), 429

        # Extract message
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        message = data.get("message", "")
        if not message:
            return jsonify({"error": "message is required"}), 400

        # Route to agent
        current_router = app.config["ROUTER"]
        loop = _get_or_create_event_loop()
        response = loop.run_until_complete(
            current_router.route_to_skill(skill, message, source_identity=identity)
        )

        if "error" in response:
            return jsonify(response), 502
        return jsonify(response)

    @app.route("/agents", methods=["GET"])
    def list_agents():
        """List discoverable skills/agents."""
        authed, _ = _authenticate()
        if not authed:
            return jsonify({"error": "Authentication required"}), 401

        current_router = app.config["ROUTER"]
        skills = current_router.list_skills()
        return jsonify({"skills": skills})

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/readyz", methods=["GET"])
    def readyz():
        import httpx
        try:
            resp = httpx.get(f"{config.registry_url}/health", timeout=5.0)
            if resp.status_code == 200:
                return jsonify({"status": "ready", "registry": "connected"})
            return jsonify({"status": "not ready", "registry": "unhealthy"}), 503
        except (httpx.ConnectError, httpx.TimeoutException):
            return jsonify({"status": "not ready", "registry": "unreachable"}), 503

    @app.route("/metrics", methods=["GET"])
    def metrics():
        from runtime.sidecar.telemetry import generate_metrics_response
        body, content_type = generate_metrics_response()
        return Response(body, content_type=content_type)

    return app


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
