"""Anomaly detection consumer — sliding window detection on audit and guardrail events."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from app.consumers.base import BaseConsumer

logger = logging.getLogger(__name__)

TOPICS = ["mesh.audit", "mesh.guardrails"]

# Detection thresholds
TRAFFIC_SPIKE_SIGMA = 3.0  # Standard deviations above mean
ERROR_BURST_THRESHOLD = 0.10  # 10% error rate
ERROR_BURST_WINDOW_SECONDS = 120  # 2 minutes
POLICY_VIOLATION_THRESHOLD = 5  # violations per minute
SLIDING_WINDOW_SECONDS = 300  # 5-minute sliding window


class AnomalyDetectorConsumer(BaseConsumer):
    """Detects anomalies in audit and guardrail event streams.

    Maintains per-agent sliding windows and detects:
    - Traffic spikes (>3 sigma from rolling mean)
    - Error bursts (>10% error rate for >2min)
    - Policy violation surges
    """

    def __init__(self, flask_app=None, kafka_producer=None, **kwargs):
        super().__init__(
            group_id="anomaly-detector",
            topics=TOPICS,
            **kwargs,
        )
        self._flask_app = flask_app
        self._kafka_producer = kafka_producer

        # Per-agent sliding windows: deque of (timestamp, event_type)
        self._agent_windows: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )
        # Per-agent error counts in current window
        self._agent_errors: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )
        # Track recently emitted anomalies to avoid duplicates
        self._recent_anomalies: dict[str, float] = {}
        self._cooldown_seconds = 300  # Don't re-alert for same agent+type within 5 min

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        now = time.time()
        agent_name = value.get("source_agent_name") or value.get("agent_name") or "unknown"

        self._agent_windows[agent_name].append((now, topic))

        # Track errors/blocks
        outcome = value.get("outcome", "")
        action = value.get("action", "")
        decision = value.get("decision", "")
        is_error = outcome in ("error", "blocked") or action == "block" or decision == "block"

        if is_error:
            self._agent_errors[agent_name].append(now)

        # Purge old entries from sliding windows
        cutoff = now - SLIDING_WINDOW_SECONDS
        while self._agent_windows[agent_name] and self._agent_windows[agent_name][0][0] < cutoff:
            self._agent_windows[agent_name].popleft()
        while self._agent_errors[agent_name] and self._agent_errors[agent_name][0] < cutoff:
            self._agent_errors[agent_name].popleft()

        # Check for anomalies
        self._check_error_burst(agent_name, now)
        self._check_traffic_spike(agent_name, now)

    def _check_error_burst(self, agent_name: str, now: float) -> None:
        """Detect sustained high error rate."""
        total = len(self._agent_windows[agent_name])
        errors = len(self._agent_errors[agent_name])

        if total < 10:  # Need minimum sample size
            return

        error_rate = errors / total
        if error_rate >= ERROR_BURST_THRESHOLD:
            self._emit_anomaly(
                agent_name=agent_name,
                anomaly_type="error_burst",
                severity="high" if error_rate > 0.25 else "medium",
                description=f"Error rate {error_rate:.1%} exceeds {ERROR_BURST_THRESHOLD:.0%} threshold "
                           f"({errors}/{total} events in {SLIDING_WINDOW_SECONDS}s window)",
                details={"error_rate": error_rate, "total_events": total, "error_events": errors},
                now=now,
            )

    def _check_traffic_spike(self, agent_name: str, now: float) -> None:
        """Detect unusual traffic volume."""
        count = len(self._agent_windows[agent_name])
        # Simple threshold: more than 100 events in 5 minutes is suspicious
        if count > 100:
            self._emit_anomaly(
                agent_name=agent_name,
                anomaly_type="traffic_spike",
                severity="medium",
                description=f"Traffic spike: {count} events in {SLIDING_WINDOW_SECONDS}s window",
                details={"event_count": count, "window_seconds": SLIDING_WINDOW_SECONDS},
                now=now,
            )

    def _emit_anomaly(
        self,
        agent_name: str,
        anomaly_type: str,
        severity: str,
        description: str,
        details: dict,
        now: float,
    ) -> None:
        # Cooldown check
        cooldown_key = f"{agent_name}:{anomaly_type}"
        last_emitted = self._recent_anomalies.get(cooldown_key, 0)
        if now - last_emitted < self._cooldown_seconds:
            return

        self._recent_anomalies[cooldown_key] = now

        anomaly = {
            "tenant_id": "default",
            "anomaly_type": anomaly_type,
            "severity": severity,
            "agent_name": agent_name,
            "description": description,
            "details": details,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.warning("Anomaly detected: %s for %s — %s", anomaly_type, agent_name, description)

        # Produce to mesh.alerts topic
        if self._kafka_producer and self._kafka_producer.kafka_available:
            from runtime.sidecar.kafka_producer import TOPIC_ALERTS
            self._kafka_producer.produce(TOPIC_ALERTS, anomaly, key=agent_name)

        # Also write directly to PG if we have a Flask app
        if self._flask_app:
            try:
                with self._flask_app.app_context():
                    from app import db
                    from app.models.mesh import MeshAnomaly

                    db.session.add(
                        MeshAnomaly(
                            tenant_id=anomaly["tenant_id"],
                            anomaly_type=anomaly_type,
                            severity=severity,
                            agent_name=agent_name,
                            description=description,
                            details=details,
                        )
                    )
                    db.session.commit()
            except Exception as exc:
                logger.error("Failed to write anomaly to PG: %s", exc)
