"""Tool execution gateway and egress proxy for the sidecar.

Handles tool calls and egress HTTP requests, enforcing authorization
and creating audit records for every operation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Any, Optional

import httpx
import structlog

from runtime.common.models import AuditRecord, Direction

logger = structlog.get_logger()


def handle_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    source_agent_name: str,
    cached_tools: list[dict] | None,
    audit_interceptor: Any,
) -> tuple[dict, int]:
    """Execute a tool call through the sidecar gateway.

    Looks up the tool in the cached registry data, validates it is
    approved and assigned, makes the HTTP call, and creates an audit record.

    Args:
        tool_name: Name of the tool to call.
        arguments: Arguments to pass to the tool endpoint.
        source_agent_name: Name of the calling agent.
        cached_tools: List of tool dicts from registry (approved + assigned).
        audit_interceptor: AuditInterceptor instance for creating audit records.

    Returns:
        (response_dict, http_status_code)
    """
    tools = cached_tools or []
    tool = None
    for t in tools:
        if t["name"] == tool_name:
            tool = t
            break

    arguments_hash = hashlib.sha256(
        json.dumps(arguments, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    if tool is None:
        logger.warning(
            "tool_call_blocked",
            tool_name=tool_name,
            agent=source_agent_name,
            reason="not_found_or_not_assigned",
        )
        _record_tool_audit(
            audit_interceptor,
            source_agent_name=source_agent_name,
            tool_name=tool_name,
            endpoint_url=None,
            arguments_hash=arguments_hash,
            response_status=403,
            decision="block",
            outcome="blocked",
        )
        return {
            "error": f"Tool '{tool_name}' not found or not assigned to this agent",
        }, 403

    endpoint_url = tool.get("endpoint_url")
    mcp_server_url = tool.get("mcp_server_url")

    if mcp_server_url:
        # Route through MCP server via SSE transport
        try:
            from runtime.sidecar.sse_client import call_mcp_tool

            result_text = call_mcp_tool(mcp_server_url, tool_name, arguments)
            response_status = 200

            try:
                response_json = json.loads(result_text)
            except (json.JSONDecodeError, TypeError):
                response_json = {"result": result_text}

        except Exception as e:
            logger.error(
                "mcp_tool_call_failed",
                tool_name=tool_name,
                mcp_server_url=mcp_server_url,
                error=str(e),
            )
            _record_tool_audit(
                audit_interceptor,
                source_agent_name=source_agent_name,
                tool_name=tool_name,
                endpoint_url=mcp_server_url,
                arguments_hash=arguments_hash,
                response_status=502,
                decision="pass",
                outcome="error",
            )
            return {
                "error": f"MCP server unreachable: {e}",
            }, 502
    else:
        # Fallback: direct HTTP call (for tools without an MCP server)
        http_method = tool.get("http_method", "POST")

        try:
            resp = httpx.request(
                http_method,
                endpoint_url,
                json=arguments,
                timeout=30.0,
            )
            response_status = resp.status_code

            try:
                response_json = resp.json()
            except Exception:
                response_json = {"raw": resp.text}

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(
                "tool_call_failed",
                tool_name=tool_name,
                endpoint_url=endpoint_url,
                error=str(e),
            )
            _record_tool_audit(
                audit_interceptor,
                source_agent_name=source_agent_name,
                tool_name=tool_name,
                endpoint_url=endpoint_url,
                arguments_hash=arguments_hash,
                response_status=502,
                decision="pass",
                outcome="error",
            )
            return {
                "error": f"Tool endpoint unreachable: {e}",
            }, 502

    _record_tool_audit(
        audit_interceptor,
        source_agent_name=source_agent_name,
        tool_name=tool_name,
        endpoint_url=mcp_server_url or endpoint_url,
        arguments_hash=arguments_hash,
        response_status=response_status,
        decision="pass",
        outcome="success" if response_status < 400 else "error",
    )

    return {
        "tool_name": tool_name,
        "status": response_status,
        "result": response_json,
    }, 200


def handle_egress_request(
    method: str,
    url: str,
    headers: dict[str, str] | None,
    body: Any,
    source_agent_name: str,
    cached_egress_rules: list[dict] | None,
    audit_interceptor: Any,
) -> tuple[dict, int]:
    """Proxy an egress HTTP request through the sidecar.

    Evaluates the URL against egress rules (sorted by priority, first match
    wins, fnmatch glob matching). If no allow rule matches, blocks the request.

    Args:
        method: HTTP method (GET, POST, etc.).
        url: Target URL.
        headers: Optional HTTP headers.
        body: Optional request body.
        source_agent_name: Name of the calling agent.
        cached_egress_rules: List of egress rule dicts from registry.
        audit_interceptor: AuditInterceptor instance.

    Returns:
        (response_dict, http_status_code)
    """
    rules = cached_egress_rules or []
    decision = _evaluate_egress_rules(url, rules)

    if decision != "allow":
        logger.warning(
            "egress_blocked",
            url=url,
            agent=source_agent_name,
        )
        _record_egress_audit(
            audit_interceptor,
            source_agent_name=source_agent_name,
            method=method,
            url=url,
            response_status=403,
            decision="block",
            outcome="blocked",
        )
        return {
            "error": f"Egress to '{url}' is denied by policy",
        }, 403

    try:
        resp = httpx.request(
            method,
            url,
            headers=headers or {},
            json=body if isinstance(body, (dict, list)) else None,
            content=body if isinstance(body, (str, bytes)) else None,
            timeout=30.0,
        )
        response_status = resp.status_code
        try:
            response_json = resp.json()
        except Exception:
            response_json = {"raw": resp.text}

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error("egress_failed", url=url, error=str(e))
        _record_egress_audit(
            audit_interceptor,
            source_agent_name=source_agent_name,
            method=method,
            url=url,
            response_status=502,
            decision="pass",
            outcome="error",
        )
        return {"error": f"Egress request failed: {e}"}, 502

    _record_egress_audit(
        audit_interceptor,
        source_agent_name=source_agent_name,
        method=method,
        url=url,
        response_status=response_status,
        decision="pass",
        outcome="success" if response_status < 400 else "error",
    )

    return {
        "status": response_status,
        "result": response_json,
    }, 200


def _evaluate_egress_rules(url: str, rules: list[dict]) -> str:
    """Evaluate URL against egress rules. First match wins. Default deny."""
    for rule in rules:
        pattern = rule.get("url_pattern", "")
        if fnmatch(url, pattern):
            return rule.get("action", "deny")
    return "deny"


def _record_tool_audit(
    audit_interceptor: Any,
    source_agent_name: str,
    tool_name: str,
    endpoint_url: Optional[str],
    arguments_hash: str,
    response_status: int,
    decision: str,
    outcome: str,
) -> None:
    """Create an audit record for a tool call."""
    if not audit_interceptor:
        return

    record = AuditRecord(
        a2a_method="tools/call",
        message_hash=arguments_hash,
        direction=Direction.OUTBOUND,
        decision=decision,
        outcome=outcome,
        source_agent_name=source_agent_name,
        dest_agent_name=tool_name,
        details={
            "tool_name": tool_name,
            "endpoint_url": endpoint_url,
            "arguments_hash": arguments_hash,
            "response_status": response_status,
        },
    )
    audit_interceptor.buffer_record(record)


def _record_egress_audit(
    audit_interceptor: Any,
    source_agent_name: str,
    method: str,
    url: str,
    response_status: int,
    decision: str,
    outcome: str,
) -> None:
    """Create an audit record for an egress HTTP request."""
    if not audit_interceptor:
        return

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]

    record = AuditRecord(
        a2a_method="egress/http",
        message_hash=url_hash,
        direction=Direction.OUTBOUND,
        decision=decision,
        outcome=outcome,
        source_agent_name=source_agent_name,
        dest_agent_name=url,
        details={
            "method": method,
            "url": url,
            "response_status": response_status,
        },
    )
    audit_interceptor.buffer_record(record)
