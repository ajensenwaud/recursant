"""Base Kafka consumer with config, deserialization, and graceful shutdown."""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BaseConsumer:
    """Base class for Kafka consumers in the observability pipeline.

    Handles consumer config, JSON deserialization, polling loop,
    graceful shutdown on SIGTERM/SIGINT, and offset commit.
    """

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        bootstrap_servers: str | None = None,
        auto_offset_reset: str = "earliest",
        poll_timeout: float = 1.0,
    ):
        self._group_id = group_id
        self._topics = topics
        self._bootstrap_servers = bootstrap_servers or os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self._auto_offset_reset = auto_offset_reset
        self._poll_timeout = poll_timeout
        self._running = False
        self._consumer = None

    def _create_consumer(self):
        from confluent_kafka import Consumer

        self._consumer = Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers,
                "group.id": self._group_id,
                "auto.offset.reset": self._auto_offset_reset,
                "enable.auto.commit": True,
                "auto.commit.interval.ms": 5000,
                "session.timeout.ms": 30000,
                "max.poll.interval.ms": 300000,
            }
        )
        self._consumer.subscribe(self._topics)
        logger.info(
            "Consumer %s subscribed to %s (bootstrap: %s)",
            self._group_id,
            self._topics,
            self._bootstrap_servers,
        )

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        """Process a single deserialized message. Override in subclasses."""
        raise NotImplementedError

    def on_batch_complete(self) -> None:
        """Called after processing a batch of messages. Override for flush logic."""
        pass

    def run(self) -> None:
        """Main polling loop. Runs until SIGTERM/SIGINT."""
        self._running = True
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

        self._create_consumer()
        logger.info("Consumer %s starting polling loop", self._group_id)

        batch_count = 0
        while self._running:
            msg = self._consumer.poll(self._poll_timeout)
            if msg is None:
                self.on_batch_complete()
                batch_count = 0
                continue

            if msg.error():
                from confluent_kafka import KafkaError

                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Consumer error: %s", msg.error())
                continue

            try:
                key = msg.key().decode("utf-8") if msg.key() else None
                value = json.loads(msg.value().decode("utf-8"))
                self.process_message(msg.topic(), key, value)
                batch_count += 1
            except json.JSONDecodeError as exc:
                logger.error("Failed to deserialize message: %s", exc)
            except Exception as exc:
                logger.error(
                    "Error processing message from %s: %s",
                    msg.topic(),
                    exc,
                    exc_info=True,
                )

        self._consumer.close()
        logger.info("Consumer %s shut down", self._group_id)

    def _shutdown_handler(self, signum, frame) -> None:
        logger.info("Consumer %s received signal %s, shutting down", self._group_id, signum)
        self._running = False
