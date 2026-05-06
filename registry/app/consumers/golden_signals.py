"""Golden signals consumer — maintains real-time request rate, error rate, and latency per agent."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from app.consumers.base import BaseConsumer

logger = logging.getLogger(__name__)

TOPICS = ["mesh.audit", "mesh.guardrails"]

# 5-minute sliding window
WINDOW_SECONDS = 300
CHECKPOINT_INTERVAL = 10  # Write to Redis every 10s for near-real-time


class GoldenSignalsConsumer(BaseConsumer):
    """Maintains in-memory sliding-window counters for golden signals.

    Per agent pair (or per agent):
    - Request rate (requests/sec over window)
    - Error rate (errors/total over window)
    - Latency p50/p95/p99

    State is exposed via Redis hashes for the golden signals REST endpoint.
    """

    def __init__(self, flask_app=None, **kwargs):
        super().__init__(
            group_id="golden-signals",
            topics=TOPICS,
            **kwargs,
        )
        self._flask_app = flask_app

        # Per-agent event timestamps: deque of (timestamp, is_error, latency_ms)
        self._agent_events: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=50000)
        )
        self._last_checkpoint = time.monotonic()

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        now = time.time()
        agent_name = value.get("source_agent_name") or value.get("agent_name") or "unknown"

        outcome = value.get("outcome", "success")
        action = value.get("action", "pass")
        is_error = outcome in ("error", "blocked") or action == "block"

        # Extract latency from details if available
        details = value.get("details") or {}
        latency_ms = details.get("latency_ms") or value.get("latency_ms")

        self._agent_events[agent_name].append((now, is_error, latency_ms))

        # Purge old entries
        cutoff = now - WINDOW_SECONDS
        while self._agent_events[agent_name] and self._agent_events[agent_name][0][0] < cutoff:
            self._agent_events[agent_name].popleft()

        # Periodic checkpoint to Redis
        if (time.monotonic() - self._last_checkpoint) >= CHECKPOINT_INTERVAL:
            self._checkpoint()

    def on_batch_complete(self) -> None:
        if (time.monotonic() - self._last_checkpoint) >= CHECKPOINT_INTERVAL:
            self._checkpoint()

    def _compute_signals(self, agent_name: str) -> dict:
        """Compute golden signals for a single agent."""
        events = self._agent_events.get(agent_name)
        if not events or len(events) == 0:
            return {
                "request_rate": 0,
                "error_rate": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0,
                "total_requests": 0,
                "total_errors": 0,
            }

        total = len(events)
        errors = sum(1 for _, is_err, _ in events if is_err)
        latencies = sorted(lat for _, _, lat in events if lat is not None)

        # Request rate: events per second over the window
        if total > 1:
            time_span = events[-1][0] - events[0][0]
            request_rate = total / max(time_span, 1)
        else:
            request_rate = 0

        error_rate = errors / total if total > 0 else 0

        def percentile(data, pct):
            if not data:
                return 0
            idx = int(len(data) * pct / 100)
            return data[min(idx, len(data) - 1)]

        return {
            "request_rate": round(request_rate, 3),
            "error_rate": round(error_rate, 4),
            "p50_latency_ms": round(percentile(latencies, 50), 1) if latencies else 0,
            "p95_latency_ms": round(percentile(latencies, 95), 1) if latencies else 0,
            "p99_latency_ms": round(percentile(latencies, 99), 1) if latencies else 0,
            "total_requests": total,
            "total_errors": errors,
        }

    def _checkpoint(self) -> None:
        """Write golden signals to Redis for API access."""
        if not self._flask_app:
            self._last_checkpoint = time.monotonic()
            return

        try:
            with self._flask_app.app_context():
                import redis as redis_lib

                redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
                r = redis_lib.from_url(redis_url)

                all_signals = {}
                for agent_name in list(self._agent_events.keys()):
                    signals = self._compute_signals(agent_name)
                    all_signals[agent_name] = signals
                    # Per-agent hash
                    hash_key = f"golden:{agent_name}"
                    r.hset(hash_key, mapping={k: str(v) for k, v in signals.items()})
                    r.expire(hash_key, WINDOW_SECONDS * 2)

                # Global summary
                r.set(
                    "golden:summary",
                    json.dumps(all_signals, default=str),
                    ex=WINDOW_SECONDS * 2,
                )

        except Exception as exc:
            logger.error("Golden signals checkpoint failed: %s", exc)

        self._last_checkpoint = time.monotonic()
