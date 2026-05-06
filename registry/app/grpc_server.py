"""gRPC server for push-based config sync to sidecars.

Runs alongside Flask on port 50051. Maintains a set of connected
sidecar subscribers and pushes config updates when policies or
compliance rules change.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent import futures
from typing import Any

logger = logging.getLogger(__name__)

# Will be populated if grpcio is available
_server = None
_subscribers: dict[str, Any] = {}  # agent_id -> subscriber context
_config_version = 0
_lock = threading.Lock()


def increment_config_version() -> int:
    """Increment and return the global config version.

    Call this when policies or compliance rules change to trigger
    push notifications to subscribed sidecars.
    """
    global _config_version
    with _lock:
        _config_version += 1
        return _config_version


def push_update(update_type: str, payload: dict) -> int:
    """Push a config update to all subscribed sidecars.

    Args:
        update_type: "policies", "compliance_rules", or "full_sync"
        payload: JSON-serializable config data

    Returns:
        Number of subscribers notified.
    """
    version = increment_config_version()

    with _lock:
        for agent_id, sub in list(_subscribers.items()):
            try:
                sub["queue"].append({
                    "version": version,
                    "update_type": update_type,
                    "payload": json.dumps(payload).encode(),
                    "timestamp": int(time.time()),
                })
            except Exception as e:
                logger.warning(f"Failed to queue update for {agent_id}: {e}")

    return len(_subscribers)


def start_grpc_server(port: int = 50051) -> None:
    """Start the gRPC ConfigSync server in a background thread."""
    try:
        import grpc
    except ImportError:
        logger.warning("grpcio not installed, skipping gRPC server")
        return

    # Import proto modules — these must be generated first
    import sys
    import os
    proto_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'mesh', 'proto')
    if proto_dir not in sys.path:
        sys.path.insert(0, proto_dir)

    try:
        from proto import config_sync_pb2, config_sync_pb2_grpc
    except ImportError:
        logger.warning("Proto modules not found, skipping gRPC server")
        return

    class ConfigSyncServicer(config_sync_pb2_grpc.ConfigSyncServicer):
        def Subscribe(self, request, context):
            agent_id = request.agent_id
            queue: list[dict] = []

            with _lock:
                _subscribers[agent_id] = {"queue": queue, "context": context}

            logger.info(f"Sidecar subscribed: {agent_id}")

            try:
                while context.is_active():
                    if queue:
                        update_data = queue.pop(0)
                        yield config_sync_pb2.ConfigUpdate(**update_data)
                    else:
                        time.sleep(0.5)
            finally:
                with _lock:
                    _subscribers.pop(agent_id, None)
                logger.info(f"Sidecar unsubscribed: {agent_id}")

        def ReportStatus(self, request, context):
            logger.info(
                f"Status report from {request.agent_id}: {request.status}"
            )
            return config_sync_pb2.StatusResponse(acknowledged=True)

    global _server
    _server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    config_sync_pb2_grpc.add_ConfigSyncServicer_to_server(
        ConfigSyncServicer(), _server
    )
    _server.add_insecure_port(f"[::]:{port}")
    _server.start()
    logger.info(f"gRPC ConfigSync server started on port {port}")


def stop_grpc_server() -> None:
    """Stop the gRPC server."""
    global _server
    if _server:
        _server.stop(grace=5)
        _server = None
