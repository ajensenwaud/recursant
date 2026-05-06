"""Kafka consumer services for the observability pipeline.

Each consumer runs as a separate process/deployment, subscribing to Kafka
topics and processing events independently (fan-out pattern).
"""

from app.consumers.base import BaseConsumer
from app.consumers.pg_writer import PGWriterConsumer
from app.consumers.ws_broadcaster import WSBroadcasterConsumer
from app.consumers.anomaly_detector import AnomalyDetectorConsumer
from app.consumers.cost_aggregator import CostAggregatorConsumer
from app.consumers.golden_signals import GoldenSignalsConsumer

__all__ = [
    "BaseConsumer",
    "PGWriterConsumer",
    "WSBroadcasterConsumer",
    "AnomalyDetectorConsumer",
    "CostAggregatorConsumer",
    "GoldenSignalsConsumer",
]
