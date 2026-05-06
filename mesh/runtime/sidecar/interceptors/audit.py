"""Audit logging interceptor — creates immutable audit records.

Records are written to structured logs (stdout + optional file) and
buffered for shipping to the registry control plane.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

import structlog

from runtime.common.models import (
    AuditRecord,
    Direction,
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import AuditConfig
from runtime.sidecar.interceptors.base import Interceptor

logger = structlog.get_logger()


class AuditInterceptor(Interceptor):
    """Creates audit records for every A2A interaction.

    This interceptor always passes — it observes but never blocks.
    It should be the last interceptor in the pipeline so it captures
    the decisions of all preceding interceptors.

    Records form a per-sidecar hash chain for tamper-evidence:
    each record's ``record_hash`` is a SHA-256 of all its fields
    including the previous record's hash.
    """

    def __init__(self, config: AuditConfig, sidecar_id: str | None = None):
        self._config = config
        self._sidecar_id = sidecar_id
        # Buffer for records pending shipment to registry
        self._buffer: deque[AuditRecord] = deque(maxlen=10000)
        # All records created (for testing / local query)
        self._records: list[AuditRecord] = []
        # Hash chain state
        self._sequence_number: int = 0
        self._last_record_hash: str | None = None
        # Optional Kafka producer for streaming audit events
        self._kafka_producer = None

    def set_kafka_producer(self, producer) -> None:
        """Attach a KafkaEventProducer for streaming audit events."""
        self._kafka_producer = producer

    @property
    def name(self) -> str:
        return "audit"

    @property
    def pending_records(self) -> list[AuditRecord]:
        """Records buffered for shipping to the registry."""
        return list(self._buffer)

    @property
    def all_records(self) -> list[AuditRecord]:
        """All audit records created by this interceptor."""
        return list(self._records)

    def drain_buffer(self) -> list[AuditRecord]:
        """Remove and return all pending records from the buffer."""
        records = list(self._buffer)
        self._buffer.clear()
        return records

    def buffer_record(self, record: AuditRecord) -> None:
        """Add a pre-built audit record to the buffer for shipping.

        Used by tool/egress handlers that create their own AuditRecord
        instances outside the interceptor pipeline.
        """
        # Apply hash chain
        self._sequence_number += 1
        record.sidecar_id = self._sidecar_id
        record.previous_record_hash = self._last_record_hash
        record.sequence_number = self._sequence_number
        record.record_hash = self._compute_record_hash(record)
        self._last_record_hash = record.record_hash

        self._records.append(record)
        self._buffer.append(record)
        self._log_record(record)
        self._produce_to_kafka(record)

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="audit disabled",
            )

        # The audit interceptor always passes — it observes only.
        # No record is created here; records are created by
        # create_record_from_result() after the pipeline completes
        # with actual outcome data.

        # Log message text flowing through the mesh
        text = self._extract_message_text(context.payload)
        if text:
            logger.info(
                "mesh_intercept",
                direction=context.direction.value,
                source=context.source_agent_name,
                destination=context.dest_agent_name,
                message_text=text,
            )

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="audit record created",
        )

    def create_record_from_result(
        self,
        context: InterceptorContext,
        decisions: list[InterceptorDecision],
        outcome: str,
        cot_analysis: dict[str, Any] | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Create a complete audit record after the pipeline has run.

        Called externally by the pipeline runner to produce a final
        record that includes all interceptor decisions and the outcome.
        Each record is linked to its predecessor via hash chain.

        Args:
            context: The interceptor context from the pipeline.
            decisions: Decisions from all interceptors.
            outcome: The final outcome (success/blocked/error).
            cot_analysis: Optional chain-of-thought analysis result dict.
                Stored in record.details but NOT included in the hash chain.
            extra_details: Additional details to merge into record.details
                (e.g. routing: "local" for intra-pod governed calls).
        """
        self._sequence_number += 1

        record = AuditRecord(
            source_agent_id=context.source_agent_id,
            source_agent_name=context.source_agent_name,
            dest_agent_id=context.dest_agent_id,
            dest_agent_name=context.dest_agent_name,
            task_id=context.task_id,
            a2a_method=context.a2a_method,
            message_hash=self._hash_payload(context.payload),
            direction=context.direction,
            interceptor_decisions=decisions,
            decision="pass" if outcome == "success" else "block",
            outcome=outcome,
            sidecar_id=self._sidecar_id,
            previous_record_hash=self._last_record_hash,
            sequence_number=self._sequence_number,
        )

        # Attach CoT analysis as supplementary data (not in hash chain)
        if cot_analysis:
            if not hasattr(record, 'details') or record.details is None:
                record.details = {}
            record.details['cot_analysis'] = cot_analysis
            # Extract top-level fields for indexing/filtering
            record.cot_risk_level = cot_analysis.get('risk_level')
            record.cot_flags = cot_analysis.get('flags')

        # Attach extra details (e.g. routing type for local governance)
        if extra_details:
            if not hasattr(record, 'details') or record.details is None:
                record.details = {}
            record.details.update(extra_details)

        # Compute and set the record hash (covers all fields)
        record.record_hash = self._compute_record_hash(record)
        self._last_record_hash = record.record_hash

        self._records.append(record)
        self._buffer.append(record)
        self._log_record(record)
        self._produce_to_kafka(record)
        return record

    def _produce_to_kafka(self, record: AuditRecord) -> None:
        """Produce an audit record to Kafka if a producer is configured."""
        if not self._kafka_producer or not self._kafka_producer.kafka_available:
            return
        record_dict = {
            "timestamp": record.timestamp.isoformat(),
            "source_agent_id": record.source_agent_id,
            "source_agent_name": record.source_agent_name,
            "dest_agent_id": record.dest_agent_id,
            "dest_agent_name": record.dest_agent_name,
            "task_id": record.task_id,
            "a2a_method": record.a2a_method,
            "message_hash": record.message_hash,
            "direction": record.direction.value if hasattr(record.direction, 'value') else str(record.direction),
            "decision": record.decision,
            "outcome": record.outcome,
            "sidecar_id": record.sidecar_id,
            "record_hash": record.record_hash,
            "previous_record_hash": record.previous_record_hash,
            "sequence_number": record.sequence_number,
            "details": getattr(record, 'details', None),
            "cot_risk_level": getattr(record, 'cot_risk_level', None),
            "cot_flags": getattr(record, 'cot_flags', None),
        }
        self._kafka_producer.produce_audit(record_dict, sidecar_id=self._sidecar_id)

    @staticmethod
    def _compute_record_hash(record: AuditRecord) -> str:
        """Compute a deterministic SHA-256 hash covering all record fields.

        The hash includes the previous record's hash, forming a chain.
        """
        parts = [
            record.timestamp.isoformat(),
            record.source_agent_id or "",
            record.source_agent_name or "",
            record.dest_agent_id or "",
            record.dest_agent_name or "",
            record.task_id or "",
            record.a2a_method,
            record.message_hash,
            record.direction.value,
            record.decision,
            record.outcome,
            record.sidecar_id or "",
            record.previous_record_hash or "",
            str(record.sequence_number or 0),
        ]
        canonical = "|".join(parts)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _extract_message_text(payload: dict[str, Any]) -> str | None:
        """Extract the human-readable message text from an A2A payload."""
        message = payload.get("message", {})
        if isinstance(message, dict):
            for part in message.get("parts", []):
                if isinstance(part, dict) and part.get("kind") == "text":
                    return part.get("text")
        return None

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        """SHA-256 hash of the message payload."""
        # Exclude internal fields (prefixed with _) from hash
        clean = {k: v for k, v in payload.items() if not k.startswith("_")}
        serialised = json.dumps(clean, sort_keys=True, default=str)
        return hashlib.sha256(serialised.encode()).hexdigest()

    @staticmethod
    def _log_record(record: AuditRecord) -> None:
        """Emit a structured log entry for the audit record."""
        logger.info(
            "audit_record",
            source_agent=record.source_agent_name,
            dest_agent=record.dest_agent_name,
            a2a_method=record.a2a_method,
            direction=record.direction.value,
            decision=record.decision,
            outcome=record.outcome,
            message_hash=record.message_hash,
            task_id=record.task_id,
        )
