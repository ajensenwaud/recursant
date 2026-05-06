"""Trace service — query and analyze multi-hop request traces."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime
from typing import Any

from sqlalchemy import func

from app import db
from app.models.mesh import MeshAuditLog, MeshReasoningSpan


class TraceService:
    """Service for querying traces (multi-hop request chains) from audit logs."""

    @staticmethod
    def get_trace(task_id: str, tenant_id: str = "default", include_spans: bool = False) -> dict[str, Any]:
        """Get a complete trace by task_id with per-hop latency."""
        records = (
            MeshAuditLog.query.filter_by(task_id=task_id, tenant_id=tenant_id)
            .order_by(MeshAuditLog.timestamp)
            .all()
        )

        if not records:
            return {"task_id": task_id, "hops": [], "total_duration_ms": 0}

        hops = []
        prev_ts = None
        for rec in records:
            hop = {
                "id": str(rec.id),
                "timestamp": rec.timestamp.isoformat(),
                "source_agent_name": rec.source_agent_name,
                "dest_agent_name": rec.dest_agent_name,
                "a2a_method": rec.a2a_method,
                "direction": rec.direction,
                "decision": rec.decision,
                "outcome": rec.outcome,
                "sidecar_id": rec.sidecar_id,
                "details": rec.details,
                "cot_analysis": rec.cot_analysis,
                "cot_risk_level": rec.cot_risk_level,
            }

            # Compute per-hop latency as delta between consecutive records
            if prev_ts:
                delta_ms = (rec.timestamp - prev_ts).total_seconds() * 1000
                hop["latency_ms"] = round(delta_ms, 1)
            else:
                hop["latency_ms"] = 0

            prev_ts = rec.timestamp
            hops.append(hop)

        # Total duration
        total_ms = (records[-1].timestamp - records[0].timestamp).total_seconds() * 1000

        result = {
            "task_id": task_id,
            "hops": hops,
            "total_duration_ms": round(total_ms, 1),
            "agent_count": len({h["source_agent_name"] for h in hops} | {h["dest_agent_name"] for h in hops}),
            "start_time": records[0].timestamp.isoformat(),
            "end_time": records[-1].timestamp.isoformat(),
            "status": records[-1].outcome,
        }

        if include_spans:
            result["reasoning_spans"] = TraceService.get_trace_spans(
                task_id, tenant_id
            )

        return result

    @staticmethod
    def list_traces(
        tenant_id: str = "default",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        agent_name: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """List distinct task_ids with summary info."""
        query = db.session.query(
            MeshAuditLog.task_id,
            func.count(MeshAuditLog.id).label("hop_count"),
            func.min(MeshAuditLog.timestamp).label("start_time"),
            func.max(MeshAuditLog.timestamp).label("end_time"),
        ).filter(
            MeshAuditLog.tenant_id == tenant_id,
            MeshAuditLog.task_id.isnot(None),
        )

        if date_from:
            query = query.filter(MeshAuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(MeshAuditLog.timestamp <= date_to)
        if agent_name:
            query = query.filter(
                db.or_(
                    MeshAuditLog.source_agent_name == agent_name,
                    MeshAuditLog.dest_agent_name == agent_name,
                )
            )

        query = query.group_by(MeshAuditLog.task_id)
        total = query.count()

        traces = (
            query.order_by(func.max(MeshAuditLog.timestamp).desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return {
            "traces": [
                {
                    "task_id": t.task_id,
                    "hop_count": t.hop_count,
                    "start_time": t.start_time.isoformat() if t.start_time else None,
                    "end_time": t.end_time.isoformat() if t.end_time else None,
                    "duration_ms": round(
                        (t.end_time - t.start_time).total_seconds() * 1000, 1
                    )
                    if t.start_time and t.end_time
                    else 0,
                }
                for t in traces
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    @staticmethod
    def submit_spans(
        spans: list[dict[str, Any]], tenant_id: str = "default"
    ) -> list[str]:
        """Validate and bulk-insert reasoning spans. Returns list of created span IDs."""
        created_ids = []
        for span_data in spans:
            span = MeshReasoningSpan(
                id=uuid_mod.uuid4(),
                tenant_id=tenant_id,
                task_id=span_data["task_id"],
                trace_id=span_data.get("trace_id"),
                agent_name=span_data["agent_name"],
                span_type=span_data["span_type"],
                span_name=span_data["span_name"],
                input_data=span_data.get("input_data"),
                output_data=span_data.get("output_data"),
                start_time=span_data["start_time"],
                end_time=span_data.get("end_time"),
                duration_ms=span_data.get("duration_ms"),
                parent_span_id=span_data.get("parent_span_id"),
                metadata_=span_data.get("metadata"),
            )
            db.session.add(span)
            created_ids.append(str(span.id))
        db.session.commit()
        return created_ids

    @staticmethod
    def get_trace_spans(
        task_id: str, tenant_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Get all reasoning spans for a given task_id."""
        spans = (
            MeshReasoningSpan.query.filter_by(
                task_id=task_id, tenant_id=tenant_id
            )
            .order_by(MeshReasoningSpan.start_time)
            .all()
        )
        return [
            {
                "id": str(s.id),
                "task_id": s.task_id,
                "trace_id": s.trace_id,
                "agent_name": s.agent_name,
                "span_type": s.span_type,
                "span_name": s.span_name,
                "input_data": s.input_data,
                "output_data": s.output_data,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "duration_ms": s.duration_ms,
                "parent_span_id": str(s.parent_span_id) if s.parent_span_id else None,
                "metadata": s.metadata_,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in spans
        ]
