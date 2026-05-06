"""PostgreSQL writer consumer — batch-inserts events from all topics into PG."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.consumers.base import BaseConsumer

logger = logging.getLogger(__name__)

# Topic to model mapping
TOPIC_AUDIT = "mesh.audit"
TOPIC_GUARDRAILS = "mesh.guardrails"
TOPIC_REGISTRATIONS = "mesh.registrations"
TOPIC_ALERTS = "mesh.alerts"
TOPIC_COST = "mesh.cost"

ALL_TOPICS = [TOPIC_AUDIT, TOPIC_GUARDRAILS, TOPIC_REGISTRATIONS, TOPIC_ALERTS, TOPIC_COST]

# Batch settings
BATCH_SIZE = 100
FLUSH_INTERVAL_SECONDS = 1.0


class PGWriterConsumer(BaseConsumer):
    """Subscribes to all mesh topics and batch-writes to PostgreSQL.

    Records are buffered and flushed when the batch reaches BATCH_SIZE
    or FLUSH_INTERVAL_SECONDS elapses, whichever comes first.
    """

    def __init__(self, flask_app=None, **kwargs):
        super().__init__(
            group_id="pg-writer",
            topics=ALL_TOPICS,
            **kwargs,
        )
        self._flask_app = flask_app
        self._audit_buffer: list[dict] = []
        self._guardrail_buffer: list[dict] = []
        self._anomaly_buffer: list[dict] = []
        self._last_flush = time.monotonic()

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if topic == TOPIC_AUDIT:
            self._audit_buffer.append(value)
        elif topic == TOPIC_GUARDRAILS:
            self._guardrail_buffer.append(value)
        elif topic == TOPIC_ALERTS:
            self._anomaly_buffer.append(value)
        # TOPIC_REGISTRATIONS and TOPIC_COST are handled by other consumers

        total = len(self._audit_buffer) + len(self._guardrail_buffer) + len(self._anomaly_buffer)
        if total >= BATCH_SIZE or (time.monotonic() - self._last_flush) >= FLUSH_INTERVAL_SECONDS:
            self._flush()

    def on_batch_complete(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if not self._audit_buffer and not self._guardrail_buffer and not self._anomaly_buffer:
            self._last_flush = time.monotonic()
            return

        if not self._flask_app:
            logger.warning("No Flask app configured, dropping %d records",
                           len(self._audit_buffer) + len(self._guardrail_buffer))
            self._audit_buffer.clear()
            self._guardrail_buffer.clear()
            self._anomaly_buffer.clear()
            return

        with self._flask_app.app_context():
            from app import db
            from app.models.mesh import MeshAuditLog, MeshAnomaly
            from app.models.guardrail import GuardrailEvent

            try:
                if self._audit_buffer:
                    self._bulk_insert_audit(db, self._audit_buffer)
                    logger.info("Flushed %d audit records to PG", len(self._audit_buffer))
                    self._audit_buffer.clear()

                if self._guardrail_buffer:
                    self._bulk_insert_guardrail_events(db, self._guardrail_buffer)
                    logger.info("Flushed %d guardrail events to PG", len(self._guardrail_buffer))
                    self._guardrail_buffer.clear()

                if self._anomaly_buffer:
                    self._bulk_insert_anomalies(db, self._anomaly_buffer)
                    logger.info("Flushed %d anomalies to PG", len(self._anomaly_buffer))
                    self._anomaly_buffer.clear()

                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                logger.error("PG flush failed: %s", exc, exc_info=True)

        self._last_flush = time.monotonic()

    @staticmethod
    def _bulk_insert_audit(db, records: list[dict]) -> None:
        from app.models.mesh import MeshAuditLog

        def _cot_analysis_dict(rec):
            """Return cot_analysis only if it's a dict; some sidecars emit
            a list (per-step analyses) which would crash .get() lookups."""
            cot = rec.get("cot_analysis")
            if isinstance(cot, dict):
                return cot
            details = rec.get("details") or {}
            cot = details.get("cot_analysis") if isinstance(details, dict) else None
            return cot if isinstance(cot, dict) else None

        objects = []
        for rec in records:
            ts = rec.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

            objects.append(
                MeshAuditLog(
                    timestamp=ts or datetime.now(timezone.utc),
                    source_agent_id=rec.get("source_agent_id"),
                    source_agent_name=rec.get("source_agent_name"),
                    dest_agent_id=rec.get("dest_agent_id"),
                    dest_agent_name=rec.get("dest_agent_name"),
                    task_id=rec.get("task_id"),
                    a2a_method=rec.get("a2a_method", "unknown"),
                    message_hash=rec.get("message_hash", ""),
                    direction=rec.get("direction", "inbound"),
                    decision=rec.get("decision", "pass"),
                    outcome=rec.get("outcome", "success"),
                    details=rec.get("details"),
                    sidecar_id=rec.get("sidecar_id"),
                    tenant_id=rec.get("tenant_id", "default"),
                    record_hash=rec.get("record_hash"),
                    previous_record_hash=rec.get("previous_record_hash"),
                    sequence_number=rec.get("sequence_number"),
                    cot_analysis=_cot_analysis_dict(rec),
                    cot_risk_level=rec.get("cot_risk_level") or (_cot_analysis_dict(rec) or {}).get("risk_level"),
                    cot_flags=rec.get("cot_flags") or (_cot_analysis_dict(rec) or {}).get("flags"),
                )
            )
        db.session.bulk_save_objects(objects)

    @staticmethod
    def _bulk_insert_guardrail_events(db, records: list[dict]) -> None:
        from app.models.guardrail import GuardrailEvent

        objects = []
        for rec in records:
            ts = rec.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

            objects.append(
                GuardrailEvent(
                    tenant_id=rec.get("tenant_id", "default"),
                    guardrail_id=rec.get("guardrail_id"),
                    guardrail_name=rec.get("guardrail_name"),
                    guardrail_type=rec.get("guardrail_type"),
                    mechanism=rec.get("mechanism"),
                    agent_name=rec.get("agent_name"),
                    sidecar_id=rec.get("sidecar_id"),
                    action=rec.get("action", "pass"),
                    reasoning=rec.get("reasoning"),
                    latency_ms=rec.get("latency_ms"),
                    matched_pattern=rec.get("matched_pattern"),
                    input_hash=rec.get("input_hash"),
                    is_error=rec.get("is_error", False),
                    error_message=rec.get("error_message"),
                    timestamp=ts or datetime.now(timezone.utc),
                )
            )
        db.session.bulk_save_objects(objects)

    @staticmethod
    def _bulk_insert_anomalies(db, records: list[dict]) -> None:
        from app.models.mesh import MeshAnomaly

        objects = []
        for rec in records:
            ts = rec.get("detected_at")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

            objects.append(
                MeshAnomaly(
                    tenant_id=rec.get("tenant_id", "default"),
                    anomaly_type=rec.get("anomaly_type", "unknown"),
                    severity=rec.get("severity", "medium"),
                    agent_name=rec.get("agent_name"),
                    description=rec.get("description", ""),
                    details=rec.get("details"),
                    detected_at=ts or datetime.now(timezone.utc),
                )
            )
        db.session.bulk_save_objects(objects)
