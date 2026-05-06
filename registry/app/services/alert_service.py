"""Alert service — CRUD for mesh anomalies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import db
from app.models.mesh import MeshAnomaly


class AlertService:
    """Manages anomaly alerts from the observability pipeline."""

    @staticmethod
    def list_active(tenant_id: str = "default") -> list[dict]:
        """List unresolved anomalies."""
        anomalies = (
            MeshAnomaly.query.filter_by(tenant_id=tenant_id, resolved_at=None)
            .order_by(MeshAnomaly.detected_at.desc())
            .all()
        )
        return [AlertService._to_dict(a) for a in anomalies]

    @staticmethod
    def list_recent(
        tenant_id: str = "default",
        limit: int = 100,
        include_resolved: bool = True,
    ) -> list[dict]:
        """List recent anomalies (resolved and unresolved)."""
        query = MeshAnomaly.query.filter_by(tenant_id=tenant_id)
        if not include_resolved:
            query = query.filter(MeshAnomaly.resolved_at.is_(None))
        anomalies = query.order_by(MeshAnomaly.detected_at.desc()).limit(limit).all()
        return [AlertService._to_dict(a) for a in anomalies]

    @staticmethod
    def acknowledge(anomaly_id: str, tenant_id: str = "default") -> dict | None:
        """Acknowledge an anomaly."""
        anomaly = MeshAnomaly.query.filter_by(
            id=anomaly_id, tenant_id=tenant_id
        ).first()
        if not anomaly:
            return None
        anomaly.is_acknowledged = True
        db.session.commit()
        return AlertService._to_dict(anomaly)

    @staticmethod
    def resolve(anomaly_id: str, tenant_id: str = "default") -> dict | None:
        """Resolve an anomaly."""
        anomaly = MeshAnomaly.query.filter_by(
            id=anomaly_id, tenant_id=tenant_id
        ).first()
        if not anomaly:
            return None
        anomaly.resolved_at = datetime.now(timezone.utc)
        db.session.commit()
        return AlertService._to_dict(anomaly)

    @staticmethod
    def get(anomaly_id: str, tenant_id: str = "default") -> dict | None:
        anomaly = MeshAnomaly.query.filter_by(
            id=anomaly_id, tenant_id=tenant_id
        ).first()
        return AlertService._to_dict(anomaly) if anomaly else None

    @staticmethod
    def _to_dict(a: MeshAnomaly) -> dict:
        return {
            "id": str(a.id),
            "anomaly_type": a.anomaly_type,
            "severity": a.severity,
            "agent_name": a.agent_name,
            "description": a.description,
            "details": a.details,
            "detected_at": a.detected_at.isoformat() if a.detected_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "is_acknowledged": a.is_acknowledged,
        }
