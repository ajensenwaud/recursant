"""Flask app factory for the Recursant sidecar.

Creates and configures the Flask application with:
- POST /a2a — inbound A2A JSON-RPC endpoint
- POST /a2a/send — local proxy endpoint (agent → sidecar → remote sidecar)
- GET /.well-known/agent.json — Agent Card serving
- GET /healthz — liveness probe
- GET /readyz — readiness probe
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog
from flask import Flask, Response, jsonify, request

logger = structlog.get_logger()

from runtime.sidecar.agent_card import (
    agent_card_to_json,
    build_agent_card,
    load_agent_card_yaml,
)
from runtime.sidecar.config import SidecarConfig
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.authentication import AuthenticationInterceptor
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.interceptors.compliance import ComplianceInterceptor
from runtime.sidecar.interceptors.fault_injection import FaultInjectionInterceptor
from runtime.sidecar.interceptors.pre_guardrail import PreProcessingGuardrailInterceptor
from runtime.sidecar.interceptors.rate_limiter import RateLimitingInterceptor
from runtime.sidecar.interceptors.redaction import RedactionInterceptor
from runtime.sidecar.guardrail_eval import GuardrailEvaluator
from runtime.sidecar.interceptors.post_guardrail import PostProcessingGuardrailInterceptor
from runtime.sidecar.client import OutboundClient, handle_outbound_request
from runtime.sidecar.load_balancer import create_load_balancer
from runtime.sidecar.resilience import CircuitBreaker, RetryPolicy
from runtime.sidecar.server import handle_a2a_request, proxy_to_agent_sse
from runtime.sidecar.kafka_producer import KafkaEventProducer
from runtime.sidecar.telemetry import init_telemetry, instrument_flask, instrument_httpx
from runtime.sidecar.tools import handle_egress_request, handle_tool_call


def create_app(config: Optional[SidecarConfig] = None) -> Flask:
    """Create and configure the sidecar Flask application.

    Args:
        config: Sidecar configuration. If None, uses defaults.
    """
    if config is None:
        config = SidecarConfig()

    app = Flask(__name__)
    app.config["SIDECAR_CONFIG"] = config

    # Initialize telemetry
    init_telemetry(config.telemetry)
    instrument_flask(app)
    instrument_httpx()

    # Load agent card
    agent_card_json = _load_agent_card(config)
    app.config["AGENT_CARD_JSON"] = agent_card_json

    agent_base_url = f"http://{config.agent_host}:{config.agent_port}"
    local_agent_name = agent_card_json.get("name")

    # Build interceptors
    fault_injection_interceptor = FaultInjectionInterceptor(config.interceptors.fault_injection)
    auth_interceptor = AuthenticationInterceptor(
        config.interceptors.authentication, local_agent_name=local_agent_name,
    )
    rate_limit_interceptor = RateLimitingInterceptor(config.interceptors.rate_limiting)
    authz_interceptor = AuthorisationInterceptor(config.interceptors.authorisation)
    compliance_interceptor = ComplianceInterceptor(config.interceptors.compliance)
    redaction_interceptor = RedactionInterceptor(config.interceptors.redaction)
    # sidecar_id for hash chain — use agent card name or fallback
    sidecar_id = agent_card_json.get("name") or "unknown-sidecar"
    audit_interceptor = AuditInterceptor(config.interceptors.audit, sidecar_id=sidecar_id)

    # Build guardrail evaluator and interceptors
    guardrail_config = config.interceptors.guardrails
    _llm_client = None
    _weaviate_client = None
    if guardrail_config.enabled:
        from runtime.sidecar.llm_client import LLMClient
        from runtime.sidecar.weaviate_client import SidecarWeaviateClient
        _llm_client = LLMClient()
        _weaviate_client = SidecarWeaviateClient(
            url=guardrail_config.weaviate_url,
            timeout_ms=guardrail_config.weaviate_timeout_ms,
        )
    guardrail_evaluator = GuardrailEvaluator(
        llm_client=_llm_client,
        weaviate_client=_weaviate_client,
    )
    guardrail_evaluator._max_consecutive_errors = guardrail_config.max_consecutive_errors
    pre_guardrail_interceptor = PreProcessingGuardrailInterceptor(
        guardrail_evaluator, enabled=guardrail_config.enabled,
    )
    post_guardrail_interceptor = PostProcessingGuardrailInterceptor(
        guardrail_evaluator, enabled=guardrail_config.enabled,
    )

    # Pipeline order: fault_injection -> auth -> rate_limit -> authz -> compliance -> pre_guardrails -> redaction -> audit
    interceptors: list[Interceptor] = [
        fault_injection_interceptor,
        auth_interceptor,
        rate_limit_interceptor,
        authz_interceptor,
        compliance_interceptor,
        pre_guardrail_interceptor,
        redaction_interceptor,
        audit_interceptor,
    ]

    app.config["INTERCEPTORS"] = interceptors
    app.config["AUTH_INTERCEPTOR"] = auth_interceptor
    app.config["AUDIT_INTERCEPTOR"] = audit_interceptor
    app.config["AUTHZ_INTERCEPTOR"] = authz_interceptor
    app.config["COMPLIANCE_INTERCEPTOR"] = compliance_interceptor
    app.config["PRE_GUARDRAIL_INTERCEPTOR"] = pre_guardrail_interceptor
    app.config["POST_GUARDRAIL_INTERCEPTOR"] = post_guardrail_interceptor

    # Build CoT auditor if enabled
    cot_config = config.interceptors.cot_audit
    if cot_config.enabled:
        from runtime.sidecar.interceptors.cot_auditor import CoTAuditor
        cot_auditor = CoTAuditor(
            llm_client=_llm_client,
            provider=cot_config.provider,
            model=cot_config.model,
            max_tokens=cot_config.max_tokens,
            timeout_ms=cot_config.timeout_ms,
            risk_threshold=cot_config.risk_threshold,
            analyze_tool_calls=cot_config.analyze_tool_calls,
            analyze_retrieval=cot_config.analyze_retrieval,
            analyze_decision_points=cot_config.analyze_decision_points,
        )
        app.config["COT_AUDITOR"] = cot_auditor

    # Build Kafka event producer (no-op if KAFKA_BOOTSTRAP_SERVERS not set)
    kafka_producer = KafkaEventProducer(client_id=sidecar_id)
    app.config["KAFKA_PRODUCER"] = kafka_producer
    audit_interceptor.set_kafka_producer(kafka_producer)

    # Build resilience components
    circuit_breaker = CircuitBreaker(config.resilience.circuit_breaker)
    retry_policy = RetryPolicy(config.resilience.retry)

    # Build outbound client with TLS config + resilience
    outbound_client = OutboundClient(
        tls_cert_path=config.tls.cert_path if config.tls else None,
        tls_key_path=config.tls.key_path if config.tls else None,
        tls_ca_path=config.tls.ca_path if config.tls else None,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
    )
    app.config["OUTBOUND_CLIENT"] = outbound_client

    # Build load balancer
    lb = create_load_balancer(
        config.load_balancing.algorithm,
        consistent_hash_key=config.load_balancing.consistent_hash_key,
    )
    app.config["LOAD_BALANCER"] = lb

    # Resolve destination callables — set by registry client
    app.config["RESOLVE_DESTINATION"] = None
    app.config["RESOLVE_DESTINATIONS"] = None

    # Local agents map for intra-pod governed routing
    # Populated from config.local_agents or RECURSANT_LOCAL_AGENTS env var
    local_agents = dict(config.local_agents) if config.local_agents else {}
    if not local_agents:
        import json as _json
        import os as _os
        raw = _os.environ.get("RECURSANT_LOCAL_AGENTS", "")
        if raw:
            try:
                # Format: [{"agentName": "Auth Agent", "agentPort": 5021}, ...]
                for entry in _json.loads(raw):
                    name = entry.get("agentName") or entry.get("name", "")
                    port = entry.get("agentPort") or entry.get("port")
                    if name and port:
                        local_agents[name] = int(port)
            except (ValueError, TypeError):
                pass
    # Exclude self — don't route to ourselves
    if local_agent_name and local_agent_name in local_agents:
        del local_agents[local_agent_name]
    app.config["LOCAL_AGENTS"] = local_agents
    if local_agents:
        logger.info("local_agents_registered", agents=local_agents)

    # ---------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------

    @app.route("/a2a", methods=["POST"])
    def a2a_endpoint():
        """Inbound A2A JSON-RPC endpoint.

        For tasks/sendSubscribe, runs the interceptor pipeline on the initial
        request and then streams SSE events from the local agent.
        """
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: invalid JSON"},
            }), 400

        # Extract auth context from request
        client_cert_cn = _extract_client_cert_cn()
        api_key = request.headers.get("X-Sidecar-API-Key")
        if api_key and "_api_key" not in data.get("params", {}):
            params = data.setdefault("params", {})
            params["_api_key"] = api_key

        # Inject JWT Bearer token if present
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            params = data.setdefault("params", {})
            params["_jwt_token"] = auth_header[7:]

        # Check if this is an SSE streaming request
        method = data.get("method")
        if method == "tasks/sendSubscribe":
            # Run interceptor pipeline first
            loop = _get_or_create_event_loop()
            response = loop.run_until_complete(
                handle_a2a_request(
                    data=data,
                    interceptors=interceptors,
                    agent_base_url=agent_base_url,
                    audit_interceptor=audit_interceptor,
                    client_cert_cn=client_cert_cn,
                    dest_agent_name=local_agent_name,
                    post_guardrail_interceptor=app.config.get("POST_GUARDRAIL_INTERCEPTOR"),
                )
            )

            # If blocked, return JSON error (not SSE)
            if "error" in response:
                status_code = _error_to_status(response)
                return jsonify(response), status_code

            # Stream SSE from the local agent
            try:
                return Response(
                    proxy_to_agent_sse(agent_base_url, data),
                    content_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )
            except Exception:
                return jsonify({
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32003, "message": "Agent SSE stream failed"},
                }), 502

        # Standard JSON-RPC handling
        loop = _get_or_create_event_loop()
        response = loop.run_until_complete(
            handle_a2a_request(
                data=data,
                interceptors=interceptors,
                agent_base_url=agent_base_url,
                audit_interceptor=audit_interceptor,
                client_cert_cn=client_cert_cn,
                dest_agent_name=local_agent_name,
                post_guardrail_interceptor=app.config.get("POST_GUARDRAIL_INTERCEPTOR"),
            )
        )

        status_code = 200 if "error" not in response else _error_to_status(response)
        return jsonify(response), status_code

    @app.route("/a2a/send", methods=["POST"])
    def a2a_send_endpoint():
        """Local proxy endpoint — agent sends outbound A2A requests here.

        Expected JSON body:
            {
                "skill": "fact-check",
                "message": "Is the Eiffel Tower 330m tall?",
                "destination_url": "https://host-b:8444"  # optional
            }

        The sidecar resolves the skill to a destination agent (via registry)
        or uses the provided destination_url, runs the outbound interceptor
        pipeline, and forwards the A2A request to the remote sidecar.
        """
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "invalid JSON"}), 400

        skill = data.get("skill")
        message = data.get("message")

        if not skill or not message:
            return jsonify({"error": "skill and message are required"}), 400

        dest_url = data.get("destination_url")
        dest_name = data.get("destination_agent_name")

        loop = _get_or_create_event_loop()
        response = loop.run_until_complete(
            handle_outbound_request(
                skill=skill,
                message=message,
                interceptors=interceptors,
                source_agent_name=local_agent_name,
                dest_agent_name=dest_name,
                dest_sidecar_url=dest_url,
                outbound_client=outbound_client,
                audit_interceptor=audit_interceptor,
                resolve_destination=app.config.get("RESOLVE_DESTINATION"),
                resolve_destinations=app.config.get("RESOLVE_DESTINATIONS"),
                local_agents=app.config.get("LOCAL_AGENTS"),
                post_guardrail_interceptor=post_guardrail_interceptor,
            )
        )

        if "error" in response:
            if response.get("blocked"):
                return jsonify(response), 403
            status_code = _error_to_status(response)
            return jsonify(response), status_code

        return jsonify(response)

    @app.route("/tools/call", methods=["POST"])
    def tools_call_endpoint():
        """Tool execution gateway — agents call tools through the sidecar.

        Expected JSON body:
            {
                "tool_name": "verify_customer",
                "arguments": {"ban": "12345", "pin": "9999"}
            }
        """
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "invalid JSON"}), 400

        tool_name = data.get("tool_name")
        arguments = data.get("arguments", {})

        if not tool_name:
            return jsonify({"error": "tool_name is required"}), 400

        registry_client = app.config.get("REGISTRY_CLIENT")
        cached_tools = registry_client.cached_tools if registry_client else None

        result, status_code = handle_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            source_agent_name=local_agent_name or "unknown",
            cached_tools=cached_tools,
            audit_interceptor=audit_interceptor,
        )

        return jsonify(result), status_code

    @app.route("/egress", methods=["POST"])
    def egress_endpoint():
        """Egress proxy — agents make external HTTP calls through the sidecar.

        Expected JSON body:
            {
                "method": "GET",
                "url": "https://api.example.com/data",
                "headers": {},
                "body": null
            }
        """
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({"error": "invalid JSON"}), 400

        egress_method = data.get("method", "GET")
        url = data.get("url")
        egress_headers = data.get("headers")
        body = data.get("body")

        if not url:
            return jsonify({"error": "url is required"}), 400

        registry_client = app.config.get("REGISTRY_CLIENT")
        cached_rules = registry_client.cached_egress_rules if registry_client else None

        result, status_code = handle_egress_request(
            method=egress_method,
            url=url,
            headers=egress_headers,
            body=body,
            source_agent_name=local_agent_name or "unknown",
            cached_egress_rules=cached_rules,
            audit_interceptor=audit_interceptor,
        )

        return jsonify(result), status_code

    @app.route("/traces/spans", methods=["POST"])
    def submit_traces_spans():
        """Receive reasoning spans from local agent and forward to registry."""
        data = request.get_json(silent=True)
        if not data or "spans" not in data:
            return jsonify({"error": "Request body with 'spans' array required"}), 400

        # Attach sidecar_id to each span's metadata
        sidecar_id = config.agent_name or "unknown-sidecar"
        for span in data.get("spans", []):
            meta = span.get("metadata") or {}
            meta["sidecar_id"] = sidecar_id
            span["metadata"] = meta

        # Forward to registry
        registry_url = config.registry_url
        headers = {"Content-Type": "application/json"}
        if config.mesh_api_key:
            headers["X-Mesh-API-Key"] = config.mesh_api_key
        headers["X-Tenant-ID"] = getattr(config, "tenant_id", "default")

        try:
            resp = httpx.post(
                f"{registry_url}/v1/mesh/traces/spans",
                json=data,
                headers=headers,
                timeout=10.0,
            )
            return jsonify(resp.json()), resp.status_code
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to forward spans to registry: %s", exc)
            return jsonify({"error": f"Failed to forward spans: {exc}"}), 502

    @app.route("/.well-known/agent.json", methods=["GET"])
    def agent_card():
        """Serve the A2A Agent Card."""
        return jsonify(app.config["AGENT_CARD_JSON"])

    @app.route("/healthz", methods=["GET"])
    def healthz():
        """Liveness probe — always returns 200 if the process is running."""
        return jsonify({"status": "ok"})

    # Prometheus metrics endpoint
    if config.telemetry.prometheus_enabled:
        @app.route("/metrics", methods=["GET"])
        def metrics_endpoint():
            """Prometheus-compatible metrics endpoint."""
            from runtime.sidecar.telemetry import generate_metrics_response
            body, content_type = generate_metrics_response()
            return Response(body, content_type=content_type)

    @app.route("/readyz", methods=["GET"])
    def readyz():
        """Readiness probe — checks registry connectivity."""
        registry_url = config.registry_url
        try:
            resp = httpx.get(f"{registry_url}/health", timeout=5.0)
            if resp.status_code == 200:
                return jsonify({"status": "ready", "registry": "connected"})
            return jsonify({"status": "not ready", "registry": "unhealthy"}), 503
        except (httpx.ConnectError, httpx.TimeoutException):
            return jsonify({"status": "not ready", "registry": "unreachable"}), 503

    return app


def _load_agent_card(config: SidecarConfig) -> dict:
    """Load and build the agent card, or return a placeholder on error."""
    scheme = "https" if config.tls else "http"
    try:
        raw = load_agent_card_yaml(config.agent_card_path)
        import os as _os
        advertise_host = _os.environ.get("SIDECAR_ADVERTISE_HOST", "localhost")
        default_port = str(config.a2a_port if config.tls else config.port)
        advertise_port = _os.environ.get("SIDECAR_ADVERTISE_PORT", default_port)
        default_scheme = "https" if config.tls else "http"
        advertise_scheme = _os.environ.get("SIDECAR_ADVERTISE_SCHEME", default_scheme)
        sidecar_url = f"{advertise_scheme}://{advertise_host}:{advertise_port}"
        card = build_agent_card(
            raw,
            sidecar_url=sidecar_url,
            registry_url=config.registry_url,
        )
        return agent_card_to_json(card)
    except FileNotFoundError:
        return {
            "name": "unconfigured-sidecar",
            "description": "Agent card not loaded",
            "version": "0.0.0",
            "url": f"{scheme}://localhost:{config.a2a_port}",
            "skills": [],
            "capabilities": {},
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
        }


def _extract_client_cert_cn() -> Optional[str]:
    """Extract the client certificate CN from the request.

    In production with uvicorn + SSL, the cert info is available
    via the WSGI environ. For testing, we use a custom header.
    """
    # Check for test/dev header first
    cn = request.headers.get("X-Client-Cert-CN")
    if cn:
        return cn

    # In production, the TLS layer sets this in the environ
    peer_cert = request.environ.get("peercert")
    if peer_cert and isinstance(peer_cert, dict):
        for rdn in peer_cert.get("subject", ()):
            for attr, value in rdn:
                if attr == "commonName":
                    return value
    return None


def _error_to_status(response: dict) -> int:
    """Map JSON-RPC error codes to HTTP status codes."""
    code = response.get("error", {}).get("code", 0)
    mapping = {
        -32700: 400,  # Parse error
        -32600: 400,  # Invalid request
        -32601: 404,  # Method not found
        -32001: 401,  # Authentication failed
        -32002: 403,  # Authorisation denied
        -32003: 502,  # Agent unavailable
    }
    return mapping.get(code, 500)


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get the current event loop or create a new one."""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
