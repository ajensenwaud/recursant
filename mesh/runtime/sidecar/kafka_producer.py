"""Kafka event producer for sidecar observability events.

Wraps confluent_kafka.Producer with JSON serialization, delivery callbacks,
and graceful shutdown. Falls back to no-op mode when KAFKA_BOOTSTRAP_SERVERS
is not configured (HTTP fallback remains in registry_client.py).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

logger = structlog.get_logger()

# Topic constants
TOPIC_AUDIT = "mesh.audit"
TOPIC_GUARDRAILS = "mesh.guardrails"
TOPIC_REGISTRATIONS = "mesh.registrations"
TOPIC_ALERTS = "mesh.alerts"
TOPIC_COST = "mesh.cost"


class KafkaEventProducer:
    """Produce observability events to Kafka topics.

    If Kafka is not configured (no KAFKA_BOOTSTRAP_SERVERS env var),
    all produce calls are silently skipped and kafka_available returns False.
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        client_id: str = "sidecar",
    ):
        self._bootstrap_servers = bootstrap_servers or os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", ""
        )
        self._producer = None
        self._client_id = client_id

        if self._bootstrap_servers:
            try:
                from confluent_kafka import Producer

                self._producer = Producer(
                    {
                        "bootstrap.servers": self._bootstrap_servers,
                        "client.id": client_id,
                        "acks": "1",
                        "linger.ms": 50,
                        "batch.num.messages": 100,
                        "compression.type": "lz4",
                        "retries": 3,
                        "retry.backoff.ms": 100,
                    }
                )
                logger.info(
                    "kafka_producer_initialized",
                    bootstrap_servers=self._bootstrap_servers,
                    client_id=client_id,
                )
            except ImportError:
                logger.warning("confluent_kafka not installed, Kafka producer disabled")
            except Exception as exc:
                logger.error("kafka_producer_init_failed", error=str(exc))

    @property
    def kafka_available(self) -> bool:
        return self._producer is not None

    def produce(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
    ) -> None:
        """Produce a JSON-serialized event to a Kafka topic.

        Args:
            topic: Kafka topic name.
            value: Dict to serialize as JSON.
            key: Optional partition key (e.g., sidecar_id, agent_name).
        """
        if not self._producer:
            return

        try:
            serialized = json.dumps(value, default=str).encode("utf-8")
            key_bytes = key.encode("utf-8") if key else None
            self._producer.produce(
                topic,
                value=serialized,
                key=key_bytes,
                callback=self._delivery_callback,
            )
            # Trigger delivery report callbacks without blocking
            self._producer.poll(0)
        except Exception as exc:
            logger.error(
                "kafka_produce_failed",
                topic=topic,
                key=key,
                error=str(exc),
            )

    def produce_audit(self, record_dict: dict[str, Any], sidecar_id: str | None = None) -> None:
        """Produce an audit record to mesh.audit topic."""
        self.produce(TOPIC_AUDIT, record_dict, key=sidecar_id)

    def produce_guardrail_event(self, event_dict: dict[str, Any], agent_name: str | None = None) -> None:
        """Produce a guardrail event to mesh.guardrails topic."""
        self.produce(TOPIC_GUARDRAILS, event_dict, key=agent_name)

    def produce_registration(self, event_dict: dict[str, Any], agent_name: str | None = None) -> None:
        """Produce a registration/deregistration event to mesh.registrations topic."""
        self.produce(TOPIC_REGISTRATIONS, event_dict, key=agent_name)

    def flush(self, timeout: float = 5.0) -> int:
        """Flush pending messages. Returns number of messages still in queue."""
        if not self._producer:
            return 0
        return self._producer.flush(timeout)

    def close(self) -> None:
        """Gracefully shut down: flush all pending messages."""
        if self._producer:
            remaining = self._producer.flush(10.0)
            if remaining > 0:
                logger.warning("kafka_producer_close_incomplete", remaining=remaining)
            logger.info("kafka_producer_closed")

    @staticmethod
    def _delivery_callback(err, msg) -> None:
        if err is not None:
            logger.error(
                "kafka_delivery_failed",
                topic=msg.topic(),
                partition=msg.partition(),
                error=str(err),
            )
