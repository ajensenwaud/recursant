"""Security posture service — composite security score for the mesh."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func

from app import db
from app.models.mesh import MeshAnomaly, MeshAuditLog, MeshRegistration
from app.models.guardrail import Guardrail, GuardrailAssignment, GuardrailEvent, GuardrailStatus


class SecurityPostureService:
    """Computes a composite security posture score (0-100) for the mesh."""

    @staticmethod
    def compute_posture(tenant_id: str = "default") -> dict[str, Any]:
        """Compute composite security posture score.

        Components:
        - mTLS coverage (% of registered agents with valid certs)
        - Guardrail coverage (% of agents with assigned guardrails)
        - Recent guardrail pass rate
        - Open anomaly count
        - Policy violation rate
        """
        scores = {}

        # 1. mTLS coverage — count registrations (all use mTLS in production)
        total_registrations = MeshRegistration.query.filter_by(tenant_id=tenant_id).count()
        healthy_registrations = MeshRegistration.query.filter_by(
            tenant_id=tenant_id, status="healthy"
        ).count()
        if total_registrations > 0:
            scores["mtls_coverage"] = round(healthy_registrations / total_registrations * 100, 1)
        else:
            scores["mtls_coverage"] = 100.0  # No agents, perfect score

        # 2. Guardrail coverage — % of agents with at least one guardrail
        from app.models.agent import Agent, AgentStatus
        active_agents = Agent.query.filter_by(
            tenant_id=tenant_id, status=AgentStatus.ACTIVE
        ).filter(Agent.deleted_at.is_(None)).count()

        agents_with_guardrails = (
            db.session.query(func.count(func.distinct(GuardrailAssignment.agent_name)))
            .filter(GuardrailAssignment.tenant_id == tenant_id)
            .scalar()
        ) or 0

        if active_agents > 0:
            scores["guardrail_coverage"] = round(
                min(agents_with_guardrails / active_agents * 100, 100), 1
            )
        else:
            scores["guardrail_coverage"] = 100.0

        # 3. Recent guardrail pass rate (last 24h)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        total_events = GuardrailEvent.query.filter(
            GuardrailEvent.tenant_id == tenant_id,
            GuardrailEvent.timestamp >= cutoff,
        ).count()
        blocked_events = GuardrailEvent.query.filter(
            GuardrailEvent.tenant_id == tenant_id,
            GuardrailEvent.timestamp >= cutoff,
            GuardrailEvent.action == "block",
        ).count()

        if total_events > 0:
            # Lower block rate is better (means fewer threats)
            # But a very high block rate (>50%) suggests attacks in progress
            block_rate = blocked_events / total_events
            if block_rate > 0.5:
                scores["guardrail_effectiveness"] = 40.0  # Under attack
            elif block_rate > 0.2:
                scores["guardrail_effectiveness"] = 70.0
            else:
                scores["guardrail_effectiveness"] = 95.0
        else:
            scores["guardrail_effectiveness"] = 80.0  # No data, neutral

        # 4. Open anomalies
        open_anomalies = MeshAnomaly.query.filter_by(
            tenant_id=tenant_id, resolved_at=None
        ).count()
        if open_anomalies == 0:
            scores["anomaly_score"] = 100.0
        elif open_anomalies <= 2:
            scores["anomaly_score"] = 80.0
        elif open_anomalies <= 5:
            scores["anomaly_score"] = 60.0
        else:
            scores["anomaly_score"] = max(20.0, 100 - open_anomalies * 10)

        # 5. Policy violation rate (last 24h)
        total_audit = MeshAuditLog.query.filter(
            MeshAuditLog.tenant_id == tenant_id,
            MeshAuditLog.timestamp >= cutoff,
        ).count()
        violations = MeshAuditLog.query.filter(
            MeshAuditLog.tenant_id == tenant_id,
            MeshAuditLog.timestamp >= cutoff,
            MeshAuditLog.decision == "block",
        ).count()

        if total_audit > 0:
            violation_rate = violations / total_audit
            scores["policy_compliance"] = round(max(0, (1 - violation_rate * 5) * 100), 1)
        else:
            scores["policy_compliance"] = 90.0

        # Composite score (weighted average)
        weights = {
            "mtls_coverage": 0.20,
            "guardrail_coverage": 0.20,
            "guardrail_effectiveness": 0.20,
            "anomaly_score": 0.20,
            "policy_compliance": 0.20,
        }
        composite = sum(scores[k] * weights[k] for k in weights)

        return {
            "composite_score": round(composite, 1),
            "components": scores,
            "open_anomalies": open_anomalies,
            "total_registrations": total_registrations,
            "active_agents": active_agents,
        }
