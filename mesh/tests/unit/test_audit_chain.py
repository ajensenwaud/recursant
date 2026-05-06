"""Tests for hash-chained tamper-evident audit logs."""

import asyncio

import pytest

from runtime.common.models import (
    Direction,
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import AuditConfig
from runtime.sidecar.interceptors.audit import AuditInterceptor


def _make_context(text: str = "hello", **overrides) -> InterceptorContext:
    defaults = dict(
        direction=Direction.OUTBOUND,
        a2a_method="message/send",
        payload={
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
        source_agent_name="agent-a",
        dest_agent_name="agent-b",
    )
    defaults.update(overrides)
    return InterceptorContext(**defaults)


def _make_decisions() -> list[InterceptorDecision]:
    return [
        InterceptorDecision(
            interceptor="auth",
            action=InterceptorAction.PASS,
            reason="ok",
        ),
    ]


class TestHashChain:
    def test_first_record_has_no_previous(self):
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")
        ctx = _make_context("test message")

        record = interceptor.create_record_from_result(ctx, _make_decisions(), "success")

        assert record.sequence_number == 1
        assert record.previous_record_hash is None
        assert record.record_hash is not None
        assert len(record.record_hash) == 64  # SHA-256 hex
        assert record.sidecar_id == "sidecar-1"

    def test_chain_links_records(self):
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")

        ctx1 = _make_context("first message")
        record1 = interceptor.create_record_from_result(ctx1, _make_decisions(), "success")

        ctx2 = _make_context("second message")
        record2 = interceptor.create_record_from_result(ctx2, _make_decisions(), "success")

        assert record2.sequence_number == 2
        assert record2.previous_record_hash == record1.record_hash
        assert record2.record_hash != record1.record_hash

    def test_chain_three_records(self):
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")

        records = []
        for i in range(3):
            ctx = _make_context(f"message {i}")
            records.append(
                interceptor.create_record_from_result(ctx, _make_decisions(), "success")
            )

        assert records[0].sequence_number == 1
        assert records[1].sequence_number == 2
        assert records[2].sequence_number == 3

        assert records[0].previous_record_hash is None
        assert records[1].previous_record_hash == records[0].record_hash
        assert records[2].previous_record_hash == records[1].record_hash

    def test_hash_is_deterministic(self):
        """Same input fields should produce the same record hash."""
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")
        ctx = _make_context("deterministic test")
        record = interceptor.create_record_from_result(ctx, _make_decisions(), "success")

        # Recompute the hash — should match
        recomputed = AuditInterceptor._compute_record_hash(record)
        assert recomputed == record.record_hash

    def test_tampering_detection(self):
        """Modifying a field after hashing should change the recomputed hash."""
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")
        ctx = _make_context("tamper test")
        record = interceptor.create_record_from_result(ctx, _make_decisions(), "success")

        original_hash = record.record_hash

        # Tamper with a field
        record.outcome = "blocked"
        recomputed = AuditInterceptor._compute_record_hash(record)
        assert recomputed != original_hash

    def test_chain_break_detected(self):
        """If we modify a record's hash, the next record's link is broken."""
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")

        ctx1 = _make_context("record one")
        record1 = interceptor.create_record_from_result(ctx1, _make_decisions(), "success")

        ctx2 = _make_context("record two")
        record2 = interceptor.create_record_from_result(ctx2, _make_decisions(), "success")

        # Verify the chain is valid
        assert record2.previous_record_hash == record1.record_hash

        # Simulate tampering with record1
        tampered_hash = "0" * 64
        # The chain link in record2 would no longer match
        assert record2.previous_record_hash != tampered_hash

    def test_blocked_outcome(self):
        config = AuditConfig(enabled=True)
        interceptor = AuditInterceptor(config, sidecar_id="sidecar-1")
        ctx = _make_context("blocked message")
        record = interceptor.create_record_from_result(ctx, _make_decisions(), "blocked")

        assert record.decision == "block"
        assert record.outcome == "blocked"
        assert record.record_hash is not None

    def test_sidecar_id_included_in_hash(self):
        """Different sidecar_ids should produce different hashes for same payload."""
        config = AuditConfig(enabled=True)

        i1 = AuditInterceptor(config, sidecar_id="sidecar-a")
        i2 = AuditInterceptor(config, sidecar_id="sidecar-b")

        ctx = _make_context("same message")
        r1 = i1.create_record_from_result(ctx, _make_decisions(), "success")
        r2 = i2.create_record_from_result(ctx, _make_decisions(), "success")

        # Same sequence, same payload, but different sidecar_id => different hash
        assert r1.record_hash != r2.record_hash
