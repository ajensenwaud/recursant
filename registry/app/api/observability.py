"""Observability API endpoints.

Provides REST endpoints for the unified observability dashboard:
traces, golden signals, cost, alerts, security posture, and tool metrics.

Authentication: JWT required (dashboard endpoints).
"""

import json
import logging
import os

from flask import jsonify, request

from app.api import api_bp
from app.api.auth import jwt_required
from app.api.mesh import mesh_api_key_required, mesh_or_jwt_required
from app.schemas.reasoning_span import ReasoningSpanSubmitSchema
from app.services.alert_service import AlertService
from app.services.security_posture_service import SecurityPostureService
from app.services.trace_service import TraceService

logger = logging.getLogger(__name__)


def _get_tenant_id() -> str:
    return request.headers.get("X-Tenant-ID", "default")


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/traces", methods=["GET"])
@jwt_required
def observability_list_traces():
    """List traces with optional filters and pagination."""
    from datetime import datetime

    tenant_id = _get_tenant_id()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    agent_name = request.args.get("agent_name")

    date_from = None
    date_to = None
    if request.args.get("date_from"):
        try:
            date_from = datetime.fromisoformat(request.args["date_from"])
        except ValueError:
            return jsonify({"error": "Invalid date_from format"}), 400
    if request.args.get("date_to"):
        try:
            date_to = datetime.fromisoformat(request.args["date_to"])
        except ValueError:
            return jsonify({"error": "Invalid date_to format"}), 400

    result = TraceService.list_traces(
        tenant_id=tenant_id,
        date_from=date_from,
        date_to=date_to,
        agent_name=agent_name,
        page=max(1, page),
        per_page=min(max(1, per_page), 200),
    )
    return jsonify(result), 200


@api_bp.route("/mesh/observability/traces/<task_id>", methods=["GET"])
@jwt_required
def observability_get_trace(task_id):
    """Get a complete trace by task_id with per-hop latency."""
    tenant_id = _get_tenant_id()
    include_spans = request.args.get("include_spans", "false").lower() == "true"
    result = TraceService.get_trace(
        task_id=task_id, tenant_id=tenant_id, include_spans=include_spans
    )
    if not result["hops"] and not result.get("reasoning_spans"):
        return jsonify({"error": "Trace not found"}), 404
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Reasoning spans
# ---------------------------------------------------------------------------


@api_bp.route("/mesh/traces/spans", methods=["POST"])
@mesh_or_jwt_required
def observability_submit_spans():
    """Receive reasoning spans from agents/sidecars."""
    tenant_id = _get_tenant_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    schema = ReasoningSpanSubmitSchema()
    errors = schema.validate(data)
    if errors:
        return jsonify({"error": "Validation failed", "messages": errors}), 400

    parsed = schema.load(data)
    try:
        span_ids = TraceService.submit_spans(parsed["spans"], tenant_id=tenant_id)
        return jsonify({"created": len(span_ids), "span_ids": span_ids}), 201
    except Exception as exc:
        logger.error("Failed to submit reasoning spans: %s", exc)
        return jsonify({"error": f"Failed to store spans: {exc}"}), 500


@api_bp.route("/mesh/observability/traces/<task_id>/spans", methods=["GET"])
@jwt_required
def observability_get_trace_spans(task_id):
    """Get reasoning spans for a specific trace."""
    tenant_id = _get_tenant_id()
    spans = TraceService.get_trace_spans(task_id=task_id, tenant_id=tenant_id)
    return jsonify({"spans": spans, "total": len(spans)}), 200


# ---------------------------------------------------------------------------
# Golden signals
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/golden-signals", methods=["GET"])
@jwt_required
def observability_golden_signals():
    """Get golden signals summary for all agents (from Redis)."""
    try:
        import redis as redis_lib

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        summary_raw = r.get("golden:summary")
        if summary_raw:
            summary = json.loads(summary_raw)
            return jsonify({"agents": summary}), 200
        return jsonify({"agents": {}}), 200
    except Exception as exc:
        logger.error("Failed to fetch golden signals: %s", exc)
        return jsonify({"agents": {}, "error": "Redis unavailable"}), 200


@api_bp.route("/mesh/observability/golden-signals/<agent_name>", methods=["GET"])
@jwt_required
def observability_golden_signals_agent(agent_name):
    """Get golden signals for a specific agent (from Redis)."""
    try:
        import redis as redis_lib

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        hash_key = f"golden:{agent_name}"
        data = r.hgetall(hash_key)
        if data:
            signals = {
                k.decode() if isinstance(k, bytes) else k:
                float(v.decode() if isinstance(v, bytes) else v)
                for k, v in data.items()
            }
            return jsonify({"agent_name": agent_name, "signals": signals}), 200
        return jsonify({"agent_name": agent_name, "signals": None}), 404
    except Exception as exc:
        logger.error("Failed to fetch golden signals for %s: %s", agent_name, exc)
        return jsonify({"agent_name": agent_name, "signals": None, "error": "Redis unavailable"}), 200


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/cost", methods=["GET"])
@jwt_required
def observability_cost_summary():
    """Get cost summary for all agents/models (from Redis)."""
    try:
        import redis as redis_lib

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)
        summary_raw = r.get("cost:summary")
        if summary_raw:
            summary = json.loads(summary_raw)
            totals = summary.get("totals", {})

            entries = []
            total_cost = 0.0
            total_input = 0
            total_output = 0
            total_requests = 0

            for key, data in totals.items():
                parts = key.split(":", 1)
                agent_name = parts[0] if parts else "unknown"
                model_name = parts[1] if len(parts) > 1 else "unknown"
                cost = float(data.get("cost_usd", 0))
                inp = int(data.get("input_tokens", 0))
                out = int(data.get("output_tokens", 0))
                req = int(data.get("request_count", 0))

                entries.append({
                    "agent_name": agent_name,
                    "model_name": model_name,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cost_usd": round(cost, 6),
                    "request_count": req,
                })

                total_cost += cost
                total_input += inp
                total_output += out
                total_requests += req

            return jsonify({
                "entries": entries,
                "total_cost_usd": round(total_cost, 6),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_requests": total_requests,
                "updated_at": summary.get("updated_at"),
            }), 200
        return jsonify({
            "entries": [],
            "total_cost_usd": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_requests": 0,
        }), 200
    except Exception as exc:
        logger.error("Failed to fetch cost summary: %s", exc)
        return jsonify({"entries": [], "error": "Redis unavailable"}), 200


@api_bp.route("/mesh/observability/cost/<agent_name>", methods=["GET"])
@jwt_required
def observability_cost_agent(agent_name):
    """Get cost breakdown for a specific agent (from Redis)."""
    try:
        import redis as redis_lib

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url)

        # Scan for all cost keys matching this agent
        entries = []
        cursor = 0
        pattern = f"cost:{agent_name}:*"
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                parts = key_str.split(":", 2)
                model_name = parts[2] if len(parts) > 2 else "unknown"
                data = r.hgetall(key)
                if data:
                    decoded = {
                        (k.decode() if isinstance(k, bytes) else k):
                        (v.decode() if isinstance(v, bytes) else v)
                        for k, v in data.items()
                    }
                    entries.append({
                        "model_name": model_name,
                        "input_tokens": int(decoded.get("input_tokens", 0)),
                        "output_tokens": int(decoded.get("output_tokens", 0)),
                        "cost_usd": round(float(decoded.get("cost_usd", 0)), 6),
                        "request_count": int(decoded.get("request_count", 0)),
                        "updated_at": decoded.get("updated_at"),
                    })
            if cursor == 0:
                break

        return jsonify({"agent_name": agent_name, "entries": entries}), 200
    except Exception as exc:
        logger.error("Failed to fetch cost for %s: %s", agent_name, exc)
        return jsonify({"agent_name": agent_name, "entries": [], "error": "Redis unavailable"}), 200


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/alerts", methods=["GET"])
@jwt_required
def observability_list_alerts():
    """List anomaly alerts."""
    tenant_id = _get_tenant_id()
    include_resolved = request.args.get("include_resolved", "false").lower() == "true"
    limit = request.args.get("limit", 100, type=int)
    limit = min(max(1, limit), 500)

    if include_resolved:
        alerts = AlertService.list_recent(
            tenant_id=tenant_id, limit=limit, include_resolved=True
        )
    else:
        alerts = AlertService.list_active(tenant_id=tenant_id)

    return jsonify({"alerts": alerts, "total": len(alerts)}), 200


@api_bp.route("/mesh/observability/alerts/<anomaly_id>", methods=["GET"])
@jwt_required
def observability_get_alert(anomaly_id):
    """Get a single anomaly alert."""
    tenant_id = _get_tenant_id()
    alert = AlertService.get(anomaly_id=anomaly_id, tenant_id=tenant_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify(alert), 200


@api_bp.route("/mesh/observability/alerts/<anomaly_id>/acknowledge", methods=["POST"])
@jwt_required
def observability_acknowledge_alert(anomaly_id):
    """Acknowledge an anomaly alert."""
    tenant_id = _get_tenant_id()
    alert = AlertService.acknowledge(anomaly_id=anomaly_id, tenant_id=tenant_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify(alert), 200


@api_bp.route("/mesh/observability/alerts/<anomaly_id>/resolve", methods=["POST"])
@jwt_required
def observability_resolve_alert(anomaly_id):
    """Resolve an anomaly alert."""
    tenant_id = _get_tenant_id()
    alert = AlertService.resolve(anomaly_id=anomaly_id, tenant_id=tenant_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify(alert), 200


# ---------------------------------------------------------------------------
# Security posture
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/security/posture", methods=["GET"])
@jwt_required
def observability_security_posture():
    """Get composite security posture score."""
    tenant_id = _get_tenant_id()
    posture = SecurityPostureService.compute_posture(tenant_id=tenant_id)
    return jsonify(posture), 200


# ---------------------------------------------------------------------------
# Tool metrics
# ---------------------------------------------------------------------------

@api_bp.route("/mesh/observability/tools/metrics", methods=["GET"])
@jwt_required
def observability_tool_metrics():
    """Get per-tool usage metrics from audit logs."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from app import db
    from app.models.mesh import MeshAuditLog, MeshTool, MeshToolAssignment

    tenant_id = _get_tenant_id()
    hours = request.args.get("hours", 24, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get all tools
    tools = MeshTool.query.filter_by(tenant_id=tenant_id).all()
    tool_names = {t.name: str(t.id) for t in tools}

    # Get tool call counts from audit logs (where a2a_method contains tool info)
    metrics = []
    for tool in tools:
        # Count audit records where details mention this tool
        total_calls = MeshAuditLog.query.filter(
            MeshAuditLog.tenant_id == tenant_id,
            MeshAuditLog.timestamp >= cutoff,
            MeshAuditLog.a2a_method == "tools/call",
            MeshAuditLog.details.cast(db.Text).contains(tool.name),
        ).count()

        error_calls = MeshAuditLog.query.filter(
            MeshAuditLog.tenant_id == tenant_id,
            MeshAuditLog.timestamp >= cutoff,
            MeshAuditLog.a2a_method == "tools/call",
            MeshAuditLog.details.cast(db.Text).contains(tool.name),
            MeshAuditLog.outcome == "error",
        ).count()

        # Get agents using this tool
        assignments = MeshToolAssignment.query.filter_by(
            tenant_id=tenant_id, tool_id=tool.id
        ).all()
        agents_using = [a.agent_name for a in assignments]

        metrics.append({
            "tool_name": tool.name,
            "tool_id": str(tool.id),
            "call_count": total_calls,
            "error_count": error_calls,
            "error_rate": round(error_calls / total_calls, 4) if total_calls > 0 else 0,
            "agents_using": agents_using,
        })

    return jsonify({"tools": metrics, "period_hours": hours}), 200


@api_bp.route("/mesh/observability/tools/effectiveness", methods=["GET"])
@jwt_required
def observability_tool_effectiveness():
    """Get guardrail effectiveness matrix data.

    Returns block rates per guardrail × attack category.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from app import db
    from app.models.guardrail import Guardrail, GuardrailEvent, GuardrailStatus

    tenant_id = _get_tenant_id()
    hours = request.args.get("hours", 24, type=int)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get active guardrails
    guardrails = Guardrail.query.filter_by(
        tenant_id=tenant_id, status=GuardrailStatus.ACTIVE
    ).all()

    matrix = []
    for guardrail in guardrails:
        # Get events for this guardrail
        events = GuardrailEvent.query.filter(
            GuardrailEvent.tenant_id == tenant_id,
            GuardrailEvent.guardrail_id == guardrail.id,
            GuardrailEvent.timestamp >= cutoff,
        ).all()

        total = len(events)
        blocked = sum(1 for e in events if e.action == "block")
        false_positives = sum(1 for e in events if e.is_false_positive is True)

        matrix.append({
            "guardrail_id": str(guardrail.id),
            "guardrail_name": guardrail.name,
            "guardrail_type": guardrail.type.value if guardrail.type else None,
            "mechanism": guardrail.mechanism.value if guardrail.mechanism else None,
            "total_events": total,
            "blocked_events": blocked,
            "block_rate": round(blocked / total, 4) if total > 0 else 0,
            "false_positive_count": false_positives,
            "false_positive_rate": round(false_positives / total, 4) if total > 0 else 0,
        })

    return jsonify({"guardrails": matrix, "period_hours": hours}), 200
