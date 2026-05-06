"""A2A outbound client — sends requests to remote sidecars.

Handles mTLS configuration, timeouts, error mapping, circuit breaking,
and retry logic for outbound A2A JSON-RPC calls.
"""

from __future__ import annotations

import asyncio
import ssl
import uuid
from typing import Any, Optional

import httpx
import structlog

from runtime.common.models import (
    Direction,
    InterceptorContext,
)
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.base import Interceptor
from runtime.sidecar.interceptors.pipeline import run_pipeline
from runtime.sidecar.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    ConnectionPoolExhaustedError,
    RetryPolicy,
)
from runtime.sidecar.server import JSONRPCError, make_error_response
from runtime.sidecar.telemetry import (
    get_trace_context_headers,
    record_request,
    record_request_duration,
    trace_span,
)

logger = structlog.get_logger()


class OutboundClient:
    """Sends A2A JSON-RPC requests to remote sidecars.

    Manages an httpx.AsyncClient with optional mTLS configuration,
    enforces request timeouts, and applies circuit breaker + retry logic.
    """

    def __init__(
        self,
        tls_cert_path: Optional[str] = None,
        tls_key_path: Optional[str] = None,
        tls_ca_path: Optional[str] = None,
        timeout: float = 30.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self._tls_cert_path = tls_cert_path
        self._tls_key_path = tls_key_path
        self._tls_ca_path = tls_ca_path
        self._timeout = timeout
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Build an SSL context for mTLS if certs are configured."""
        if not self._tls_cert_path:
            return None

        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if self._tls_ca_path:
            ctx.load_verify_locations(self._tls_ca_path)
        ctx.load_cert_chain(
            certfile=self._tls_cert_path,
            keyfile=self._tls_key_path,
        )
        return ctx

    async def send_a2a_request(
        self,
        destination_url: str,
        method: str,
        params: dict[str, Any],
        request_id: Optional[str] = None,
        source_agent_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send an A2A JSON-RPC request to a remote sidecar.

        Applies circuit breaker and retry logic when configured.

        Args:
            destination_url: The remote sidecar's base URL (e.g. https://host-b:8444).
            method: A2A method name (e.g. "message/send").
            params: JSON-RPC params.
            request_id: JSON-RPC request ID. Generated if not provided.
            source_agent_name: Name of the calling agent (for header).

        Returns:
            The JSON-RPC response dict from the remote sidecar.

        Raises:
            CircuitOpenError: If the circuit breaker is open for this destination.
            httpx.ConnectError: If the remote sidecar is unreachable.
            httpx.TimeoutException: If the request times out.
        """
        # Check circuit breaker
        if self._circuit_breaker:
            self._circuit_breaker.check(destination_url)

        # Check connection pool limits
        if self._circuit_breaker:
            if not self._circuit_breaker.acquire(destination_url):
                raise ConnectionPoolExhaustedError(
                    destination_url, "max connections/pending requests exceeded"
                )

        max_attempts = self._retry_policy.max_attempts if self._retry_policy else 1
        last_error: Exception | None = None

        try:
            for attempt in range(max_attempts):
                try:
                    result = await self._do_send(
                        destination_url, method, params, request_id, source_agent_name
                    )
                    if self._circuit_breaker:
                        self._circuit_breaker.record_success(destination_url)
                    return result
                except Exception as e:
                    last_error = e
                    if self._circuit_breaker:
                        self._circuit_breaker.record_failure(destination_url)

                    # Only retry on retryable errors
                    if self._retry_policy and self._retry_policy.is_retryable_error(e):
                        if attempt < max_attempts - 1:
                            delay = self._retry_policy.get_delay(attempt)
                            logger.warning(
                                "retry_attempt",
                                destination=destination_url,
                                attempt=attempt + 1,
                                delay=f"{delay:.2f}s",
                                error=str(e),
                            )
                            await asyncio.sleep(delay)
                            continue
                    # Non-retryable or out of attempts
                    raise

            # Should not reach here, but just in case
            raise last_error  # type: ignore[misc]
        finally:
            # Release connection pool slot
            if self._circuit_breaker:
                self._circuit_breaker.release(destination_url)

    async def _do_send(
        self,
        destination_url: str,
        method: str,
        params: dict[str, Any],
        request_id: Optional[str] = None,
        source_agent_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Perform the actual HTTP request to the remote sidecar."""
        import time as _time

        if request_id is None:
            request_id = str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        ssl_context = self._build_ssl_context()
        verify: Any = ssl_context if ssl_context else False

        start = _time.monotonic()
        with trace_span("outbound_a2a_request", {
            "destination": destination_url,
            "method": method,
            "request_id": request_id,
        }):
            async with httpx.AsyncClient(
                timeout=self._timeout,
                verify=verify,
            ) as client:
                logger.info(
                    "outbound_request",
                    destination=destination_url,
                    method=method,
                    request_id=request_id,
                )
                headers: dict[str, str] = {}
                if source_agent_name:
                    headers["X-Client-Cert-CN"] = source_agent_name

                # Propagate W3C trace context
                headers.update(get_trace_context_headers())

                resp = await client.post(
                    f"{destination_url}/a2a",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()

                duration = _time.monotonic() - start
                record_request("outbound", method, "success")
                record_request_duration("outbound", method, duration)

                return resp.json()


async def handle_outbound_request(
    skill: str,
    message: str,
    interceptors: list[Interceptor],
    source_agent_name: Optional[str] = None,
    dest_agent_name: Optional[str] = None,
    dest_sidecar_url: Optional[str] = None,
    outbound_client: Optional[OutboundClient] = None,
    audit_interceptor: Optional[AuditInterceptor] = None,
    resolve_destination: Optional[Any] = None,
    resolve_destinations: Optional[Any] = None,
    local_agents: Optional[dict[str, int]] = None,
    post_guardrail_interceptor: Optional[Any] = None,
) -> dict[str, Any]:
    """Handle an outbound A2A request from the local agent.

    1. Resolve destination agent(s) (via registry or provided URL)
    2. Build A2A JSON-RPC message
    3. Run outbound interceptor pipeline
    4. If destination is co-located (in local_agents), proxy directly to
       localhost — full governance pipeline runs but no mTLS/remote hop
    5. Otherwise, send to remote sidecar (with failover to alternatives)
    6. Return response

    Args:
        skill: The A2A skill to invoke on the remote agent.
        message: The message text to send.
        interceptors: Ordered list of interceptors for outbound pipeline.
        source_agent_name: Name of the local agent (source).
        dest_agent_name: Name of the remote agent (if known).
        dest_sidecar_url: Direct URL of destination sidecar (overrides discovery).
        outbound_client: Client to use for sending. If None, creates a default one.
        audit_interceptor: Optional audit interceptor for final record.
        resolve_destination: Async callable(skill) -> (url, agent_name).
        resolve_destinations: Async callable(skill) -> list[(url, agent_name)].
            For failover routing — tries each destination in order.
        local_agents: Map of agent_name -> port for co-located agents in the
            same pod. If the resolved destination matches, the sidecar proxies
            directly to localhost:{port} instead of sending via mTLS to a
            remote sidecar. The interceptor pipeline still runs.
        post_guardrail_interceptor: Post-processing guardrail interceptor for
            evaluating responses from locally-routed agents.
    """
    # Build list of destinations for failover
    destinations: list[tuple[str, str]] = []

    if dest_sidecar_url is not None:
        destinations = [(dest_sidecar_url, dest_agent_name or "unknown")]
    elif resolve_destinations is not None:
        try:
            destinations = await resolve_destinations(skill)
        except Exception as e:
            logger.error("discovery_failed", skill=skill, error=str(e))
            return make_error_response(
                None, JSONRPCError.AGENT_UNAVAILABLE,
                f"Failed to discover agent for skill '{skill}': {e}"
            )
    elif resolve_destination is not None:
        try:
            url, name = await resolve_destination(skill)
            destinations = [(url, name)]
        except Exception as e:
            logger.error("discovery_failed", skill=skill, error=str(e))
            return make_error_response(
                None, JSONRPCError.AGENT_UNAVAILABLE,
                f"Failed to discover agent for skill '{skill}': {e}"
            )

    if not destinations:
        return make_error_response(
            None, JSONRPCError.AGENT_UNAVAILABLE,
            f"No destination sidecar URL for skill '{skill}'"
        )

    # Use first destination for interceptor context
    dest_sidecar_url, dest_agent_name = destinations[0]

    # Build A2A message params. Generate a task_id and embed it in
    # message.taskId so the receiving sidecar's _extract_task_id() can
    # pick it up — this is what links the sender's outbound audit row
    # with the receiver's inbound row, which is what makes the trace
    # view in the registry able to reconstruct end-to-end flows.
    request_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    params = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": message}],
            "messageId": str(uuid.uuid4()),
            "taskId": task_id,
        }
    }

    # Build interceptor context for outbound
    context = InterceptorContext(
        direction=Direction.OUTBOUND,
        a2a_method="message/send",
        payload=params,
        source_agent_name=source_agent_name,
        dest_agent_name=dest_agent_name,
        task_id=task_id,
    )

    # Run outbound interceptor pipeline
    result = await run_pipeline(interceptors, context)

    if not result.allowed:
        blocking = result.blocking_decision
        reason = blocking.reason if blocking else "request blocked"

        if audit_interceptor:
            audit_interceptor.create_record_from_result(
                context, result.decisions, "blocked"
            )

        return {"error": reason, "blocked": True}

    # Check if destination is a co-located agent (local routing)
    if local_agents and dest_agent_name and dest_agent_name in local_agents:
        local_port = local_agents[dest_agent_name]
        local_url = f"http://localhost:{local_port}"
        logger.info(
            "local_routing",
            source=source_agent_name,
            destination=dest_agent_name,
            local_port=local_port,
        )

        try:
            # Build JSON-RPC request for local agent
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "message/send",
                "params": result.context.payload,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{local_url}/a2a",
                    json=jsonrpc_request,
                )
                resp.raise_for_status()
                response = resp.json()

            # Run post-guardrail on response if configured
            if post_guardrail_interceptor:
                response_text = _extract_response_text(response)
                if response_text:
                    pg_result = await post_guardrail_interceptor.evaluate_response(response_text)
                    if pg_result.action == "block":
                        response = make_error_response(
                            request_id, JSONRPCError.AUTHORISATION_DENIED,
                            f"Response blocked by guardrail: {pg_result.reasoning}",
                        )
                    elif pg_result.action == "redact":
                        _redact_response(response, pg_result.redacted_text)

            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "success",
                    extra_details={"routing": "local", "local_port": local_port},
                )

            return response

        except Exception as e:
            logger.error("local_routing_failed", dest=dest_agent_name, error=str(e))
            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "error",
                    extra_details={"routing": "local", "error": str(e)},
                )
            return make_error_response(
                request_id, JSONRPCError.AGENT_UNAVAILABLE,
                f"Local agent '{dest_agent_name}' unreachable: {e}",
            )

    # Send to remote sidecar (with failover)
    if outbound_client is None:
        outbound_client = OutboundClient()

    last_error_msg = ""
    for url, name in destinations:
        try:
            response = await outbound_client.send_a2a_request(
                destination_url=url,
                method="message/send",
                params=result.context.payload,
                request_id=request_id,
                source_agent_name=source_agent_name,
            )

            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "success"
                )

            # Log response text flowing back through the mesh
            response_text = _extract_response_text(response)
            if response_text:
                logger.info(
                    "mesh_intercept",
                    direction="response",
                    source=name,
                    destination=source_agent_name,
                    message_text=response_text,
                )

            return response

        except ConnectionPoolExhaustedError:
            logger.warning("failover_pool_exhausted", url=url, trying_next=True)
            last_error_msg = f"Connection pool exhausted for {url}"
            continue
        except CircuitOpenError:
            logger.warning("failover_circuit_open", url=url, trying_next=True)
            last_error_msg = f"Circuit breaker open for {url}"
            continue
        except httpx.ConnectError:
            logger.warning("failover_connect_error", url=url, trying_next=True)
            last_error_msg = f"Remote sidecar at {url} is unreachable"
            continue
        except httpx.TimeoutException:
            logger.warning("failover_timeout", url=url, trying_next=True)
            last_error_msg = f"Remote sidecar at {url} timed out"
            continue
        except httpx.HTTPStatusError as e:
            logger.warning("failover_http_error", url=url, status=e.response.status_code)
            last_error_msg = f"Remote sidecar at {url} returned {e.response.status_code}"
            continue

    # All destinations exhausted
    if audit_interceptor:
        audit_interceptor.create_record_from_result(
            context, result.decisions, "error"
        )
    return make_error_response(
        request_id, JSONRPCError.AGENT_UNAVAILABLE,
        f"All destinations exhausted for skill '{skill}': {last_error_msg}"
    )


    def send_a2a_stream(
        self,
        destination_url: str,
        method: str,
        params: dict[str, Any],
        request_id: Optional[str] = None,
        source_agent_name: Optional[str] = None,
    ):
        """Send an A2A request and stream SSE events from the remote sidecar.

        Yields SSE-formatted lines as they arrive.
        Uses synchronous httpx streaming.
        """
        import httpx as _httpx

        if request_id is None:
            request_id = str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        ssl_context = self._build_ssl_context()
        verify: Any = ssl_context if ssl_context else False

        headers: dict[str, str] = {}
        if source_agent_name:
            headers["X-Client-Cert-CN"] = source_agent_name

        with _httpx.Client(timeout=300.0, verify=verify) as client:
            with client.stream(
                "POST",
                f"{destination_url}/a2a",
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    yield line + "\n"


def _extract_response_text(response: dict[str, Any]) -> str | None:
    """Extract the artifact text from an A2A JSON-RPC response."""
    try:
        return response["result"]["artifacts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None


def _redact_response(response: dict[str, Any], redacted_text: str | None) -> None:
    """Replace the artifact text in an A2A response with redacted text."""
    if redacted_text is None:
        redacted_text = "[Response redacted by guardrail policy]"
    try:
        response["result"]["artifacts"][0]["text"] = redacted_text
    except (KeyError, IndexError, TypeError):
        pass
