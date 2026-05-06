"""A2A JSON-RPC inbound server — handles requests from remote sidecars.

Parses JSON-RPC envelopes, runs the interceptor pipeline, and proxies
valid requests to the local agent process.
"""

from __future__ import annotations

import asyncio
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
from runtime.sidecar.telemetry import (
    extract_trace_context,
    record_request,
    record_request_duration,
    trace_span,
)

logger = structlog.get_logger()

# Supported A2A JSON-RPC methods
SUPPORTED_METHODS = {"message/send", "tasks/get", "tasks/cancel", "tasks/sendSubscribe"}


class JSONRPCError:
    """Standard JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603
    # Custom codes for sidecar
    AUTHENTICATION_FAILED = -32001
    AUTHORISATION_DENIED = -32002
    AGENT_UNAVAILABLE = -32003


def parse_jsonrpc_request(data: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[dict], Optional[Any]]:
    """Parse a JSON-RPC 2.0 request.

    Returns:
        (method, request_id, params, error_response)
        If parsing fails, error_response is a ready-to-return dict.
    """
    if not isinstance(data, dict):
        return None, None, None, make_error_response(
            None, JSONRPCError.PARSE_ERROR, "Parse error: expected JSON object"
        )

    if data.get("jsonrpc") != "2.0":
        return None, None, None, make_error_response(
            data.get("id"), JSONRPCError.INVALID_REQUEST, "Invalid request: missing jsonrpc 2.0"
        )

    method = data.get("method")
    request_id = data.get("id")
    params = data.get("params", {})

    if not method or not isinstance(method, str):
        return None, request_id, None, make_error_response(
            request_id, JSONRPCError.INVALID_REQUEST, "Invalid request: missing method"
        )

    if method not in SUPPORTED_METHODS:
        return method, request_id, params, make_error_response(
            request_id, JSONRPCError.METHOD_NOT_FOUND, f"Method not found: {method}"
        )

    return method, request_id, params, None


def make_error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }


def make_success_response(request_id: Any, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


async def handle_a2a_request(
    data: dict[str, Any],
    interceptors: list[Interceptor],
    agent_base_url: str,
    audit_interceptor: Optional[AuditInterceptor] = None,
    client_cert_cn: Optional[str] = None,
    source_agent_name: Optional[str] = None,
    dest_agent_name: Optional[str] = None,
    post_guardrail_interceptor=None,
) -> dict[str, Any]:
    """Handle an inbound A2A JSON-RPC request.

    1. Parse JSON-RPC envelope
    2. Run interceptor pipeline (inbound)
    3. If allowed, proxy to local agent
    4. Return JSON-RPC response

    Args:
        data: Raw JSON-RPC request body.
        interceptors: Ordered list of interceptors to run.
        agent_base_url: Local agent URL (e.g. "http://localhost:5010").
        audit_interceptor: Optional audit interceptor for final record.
        client_cert_cn: CN from the client's mTLS cert (if any).
        source_agent_name: Pre-identified source agent name.
        dest_agent_name: Name of the local agent (destination for inbound).
    """
    import time as _time

    method, request_id, params, parse_error = parse_jsonrpc_request(data)
    if parse_error is not None:
        return parse_error

    start = _time.monotonic()

    with trace_span("inbound_a2a_request", {
        "method": method or "",
        "request_id": request_id or "",
        "source_agent": source_agent_name or "",
        "dest_agent": dest_agent_name or "",
    }):
        # Build interceptor context
        context = InterceptorContext(
            direction=Direction.INBOUND,
            a2a_method=method,
            payload=params or {},
            client_cert_cn=client_cert_cn,
            source_agent_name=source_agent_name,
            dest_agent_name=dest_agent_name,
            task_id=_extract_task_id(params),
        )

        # Inject API key from payload metadata if present (for dev auth)
        if "_api_key" not in context.payload:
            api_key = (params or {}).get("_api_key")
            if api_key:
                context.payload["_api_key"] = api_key

        # Run interceptor pipeline
        result = await run_pipeline(interceptors, context)

        if not result.allowed:
            blocking = result.blocking_decision
            code = _interceptor_to_error_code(blocking.interceptor if blocking else "unknown")
            reason = blocking.reason if blocking else "request blocked"

            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "blocked"
                )

            duration = _time.monotonic() - start
            record_request("inbound", method or "unknown", "blocked")
            record_request_duration("inbound", method or "unknown", duration)

            return make_error_response(request_id, code, reason)

        # Pipeline passed — proxy to local agent
        try:
            with trace_span("proxy_to_agent"):
                agent_response = await _proxy_to_agent(agent_base_url, data)
        except httpx.ConnectError:
            logger.error("agent_unavailable", agent_url=agent_base_url)
            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "error"
                )
            duration = _time.monotonic() - start
            record_request("inbound", method or "unknown", "error")
            record_request_duration("inbound", method or "unknown", duration)
            return make_error_response(
                request_id, JSONRPCError.AGENT_UNAVAILABLE, "Local agent is unavailable"
            )
        except httpx.TimeoutException:
            logger.error("agent_timeout", agent_url=agent_base_url)
            if audit_interceptor:
                audit_interceptor.create_record_from_result(
                    context, result.decisions, "error"
                )
            duration = _time.monotonic() - start
            record_request("inbound", method or "unknown", "error")
            record_request_duration("inbound", method or "unknown", duration)
            return make_error_response(
                request_id, JSONRPCError.AGENT_UNAVAILABLE, "Local agent timed out"
            )

        # Run post-processing guardrails on agent response
        response_text = _extract_response_text(agent_response)
        if post_guardrail_interceptor and response_text:
            try:
                post_result = await post_guardrail_interceptor.evaluate_response(response_text)
                if post_result.action == "block":
                    logger.warning(
                        "post_guardrail_blocked",
                        reasoning=post_result.reasoning,
                    )
                    if audit_interceptor:
                        audit_interceptor.create_record_from_result(
                            context, result.decisions, "blocked_post_guardrail"
                        )
                    duration = _time.monotonic() - start
                    record_request("inbound", method or "unknown", "blocked")
                    record_request_duration("inbound", method or "unknown", duration)
                    return make_error_response(
                        request_id, JSONRPCError.INTERNAL_ERROR,
                        f"Response blocked by guardrail: {post_result.reasoning}",
                    )
                elif post_result.action == "redact" and post_result.redacted_text:
                    agent_response = _replace_response_text(
                        agent_response, post_result.redacted_text,
                    )
            except Exception as e:
                logger.warning("post_guardrail_error", error=str(e))

        # Run chain-of-thought auditing on the response
        cot_result_dict = None
        cot_auditor = None
        try:
            from flask import current_app
            cot_auditor = current_app.config.get("COT_AUDITOR")
        except RuntimeError:
            pass  # No app context (e.g. testing)
        if cot_auditor and agent_response:
            try:
                _cot_result = await cot_auditor.analyze_response(
                    agent_response, data, dest_agent_name or "",
                )
                if _cot_result.analyzed and _cot_result.risk_level != "none":
                    cot_result_dict = _cot_result.to_dict()
                    logger.info(
                        "cot_analysis_complete",
                        risk_level=_cot_result.risk_level,
                        flag_count=len(_cot_result.flags),
                        agent=dest_agent_name,
                    )
            except Exception as e:
                logger.warning("cot_analysis_error", error=str(e))

        if audit_interceptor:
            audit_interceptor.create_record_from_result(
                context, result.decisions, "success",
                cot_analysis=cot_result_dict,
            )

        duration = _time.monotonic() - start
        record_request("inbound", method or "unknown", "success")
        record_request_duration("inbound", method or "unknown", duration)

        # Log response text flowing back through the mesh
        if response_text:
            logger.info(
                "mesh_intercept",
                direction="response",
                source=dest_agent_name,
                destination=source_agent_name,
                message_text=response_text,
            )

        return agent_response


async def _proxy_to_agent(agent_base_url: str, request_data: dict[str, Any]) -> dict[str, Any]:
    """Forward an A2A request to the local agent and return its response."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{agent_base_url}/a2a",
            json=request_data,
        )
        resp.raise_for_status()
        return resp.json()


def proxy_to_agent_sse(agent_base_url: str, request_data: dict[str, Any]):
    """Forward an A2A request to the local agent and stream SSE events back.

    Returns a generator that yields SSE-formatted lines.
    Used for tasks/sendSubscribe.
    """
    import httpx as _httpx

    with _httpx.Client(timeout=300.0) as client:
        with client.stream(
            "POST",
            f"{agent_base_url}/a2a",
            json=request_data,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                yield line + "\n"


def _extract_task_id(params: Optional[dict]) -> Optional[str]:
    """Try to extract a task ID from the A2A params."""
    if not params:
        return None
    # tasks/get and tasks/cancel have an 'id' field
    if "id" in params:
        return str(params["id"])
    # message/send might have a task context
    message = params.get("message", {})
    if isinstance(message, dict):
        return message.get("taskId")
    return None


def _replace_response_text(response: dict[str, Any], new_text: str) -> dict[str, Any]:
    """Replace the artifact text in an A2A JSON-RPC response."""
    try:
        resp_copy = response.copy()
        result = resp_copy.get("result", {})
        if isinstance(result, dict):
            result = result.copy()
            artifacts = result.get("artifacts", [])
            if artifacts:
                artifacts = [a.copy() for a in artifacts]
                artifacts[0]["text"] = new_text
                result["artifacts"] = artifacts
            resp_copy["result"] = result
        return resp_copy
    except (KeyError, IndexError, TypeError):
        return response


def _extract_response_text(response: dict[str, Any]) -> str | None:
    """Extract the artifact text from an A2A JSON-RPC response."""
    try:
        return response["result"]["artifacts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None


def _interceptor_to_error_code(interceptor_name: str) -> int:
    """Map interceptor names to JSON-RPC error codes."""
    mapping = {
        "authentication": JSONRPCError.AUTHENTICATION_FAILED,
        "authorisation": JSONRPCError.AUTHORISATION_DENIED,
    }
    return mapping.get(interceptor_name, JSONRPCError.INTERNAL_ERROR)
