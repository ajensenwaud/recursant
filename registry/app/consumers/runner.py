"""Consumer runner entrypoint — starts a specific Kafka consumer by name.

Usage:
    python -m app.consumers.runner --consumer pg-writer
    python -m app.consumers.runner --consumer ws-broadcaster
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run a Kafka consumer")
    parser.add_argument(
        "--consumer",
        required=True,
        choices=["pg-writer", "ws-broadcaster", "anomaly-detector", "cost-aggregator", "golden-signals"],
        help="Consumer to run",
    )
    args = parser.parse_args()

    # Import Flask app for consumers that need DB/Redis/SocketIO
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from app import create_app

    flask_app = create_app()

    if args.consumer == "pg-writer":
        from app.consumers.pg_writer import PGWriterConsumer
        consumer = PGWriterConsumer(flask_app=flask_app)
    elif args.consumer == "ws-broadcaster":
        from app.consumers.ws_broadcaster import WSBroadcasterConsumer
        consumer = WSBroadcasterConsumer(flask_app=flask_app)
    elif args.consumer == "anomaly-detector":
        from app.consumers.anomaly_detector import AnomalyDetectorConsumer
        consumer = AnomalyDetectorConsumer(flask_app=flask_app)
    elif args.consumer == "cost-aggregator":
        from app.consumers.cost_aggregator import CostAggregatorConsumer
        consumer = CostAggregatorConsumer(flask_app=flask_app)
    elif args.consumer == "golden-signals":
        from app.consumers.golden_signals import GoldenSignalsConsumer
        consumer = GoldenSignalsConsumer(flask_app=flask_app)
    else:
        logger.error("Unknown consumer: %s", args.consumer)
        sys.exit(1)

    logger.info("Starting consumer: %s", args.consumer)
    consumer.run()


if __name__ == "__main__":
    main()
