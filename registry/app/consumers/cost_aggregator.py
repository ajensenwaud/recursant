"""Cost aggregation consumer — tracks token usage and cost per agent/model."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.consumers.base import BaseConsumer

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL_SECONDS = 60  # Flush to PG/Redis every minute

# Approximate per-token costs (USD) — configurable via env
DEFAULT_COST_PER_INPUT_TOKEN = 0.000003
DEFAULT_COST_PER_OUTPUT_TOKEN = 0.000015


class CostAggregatorConsumer(BaseConsumer):
    """Subscribes to mesh.audit and aggregates token/cost data per agent/model.

    Maintains running totals in memory and checkpoints to Redis
    periodically for fast retrieval by the cost dashboard API.
    """

    def __init__(self, flask_app=None, kafka_producer=None, **kwargs):
        super().__init__(
            group_id="cost-aggregator",
            topics=["mesh.audit"],
            **kwargs,
        )
        self._flask_app = flask_app
        self._kafka_producer = kafka_producer

        # In-memory running totals: {(agent_name, model_name): {input_tokens, output_tokens, cost_usd}}
        self._totals: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "request_count": 0}
        )
        self._last_checkpoint = time.monotonic()

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        details = value.get("details") or {}
        input_tokens = details.get("input_tokens", 0)
        output_tokens = details.get("output_tokens", 0)

        if not input_tokens and not output_tokens:
            return

        agent_name = value.get("source_agent_name") or "unknown"
        model_name = details.get("model_name", "unknown")
        estimated_cost = details.get("estimated_cost_usd")

        if estimated_cost is None:
            estimated_cost = (
                input_tokens * DEFAULT_COST_PER_INPUT_TOKEN
                + output_tokens * DEFAULT_COST_PER_OUTPUT_TOKEN
            )

        bucket = self._totals[(agent_name, model_name)]
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["cost_usd"] += estimated_cost
        bucket["request_count"] += 1

        # Periodic checkpoint
        if (time.monotonic() - self._last_checkpoint) >= CHECKPOINT_INTERVAL_SECONDS:
            self._checkpoint()

    def on_batch_complete(self) -> None:
        if (time.monotonic() - self._last_checkpoint) >= CHECKPOINT_INTERVAL_SECONDS:
            self._checkpoint()

    def _checkpoint(self) -> None:
        """Write running totals to Redis for fast API access."""
        if not self._flask_app:
            self._last_checkpoint = time.monotonic()
            return

        try:
            with self._flask_app.app_context():
                import redis as redis_lib
                import os
                import json

                redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
                r = redis_lib.from_url(redis_url)

                for (agent_name, model_name), totals in self._totals.items():
                    hash_key = f"cost:{agent_name}:{model_name}"
                    r.hset(hash_key, mapping={
                        "input_tokens": str(totals["input_tokens"]),
                        "output_tokens": str(totals["output_tokens"]),
                        "cost_usd": str(totals["cost_usd"]),
                        "request_count": str(totals["request_count"]),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
                    r.expire(hash_key, 86400 * 7)  # 7-day TTL

                # Store the full summary
                summary = {
                    "totals": {
                        f"{agent}:{model}": data
                        for (agent, model), data in self._totals.items()
                    },
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                r.set("cost:summary", json.dumps(summary, default=str), ex=86400)

                logger.info(
                    "Cost checkpoint: %d agent/model buckets written to Redis",
                    len(self._totals),
                )
        except Exception as exc:
            logger.error("Cost checkpoint failed: %s", exc)

        self._last_checkpoint = time.monotonic()
