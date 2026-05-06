"""WebSocket broadcaster consumer — emits events to Socket.IO clients."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.consumers.base import BaseConsumer

logger = logging.getLogger(__name__)

ALL_TOPICS = ["mesh.audit", "mesh.guardrails", "mesh.registrations", "mesh.alerts", "mesh.cost"]

# Map Kafka topics to Socket.IO event names
TOPIC_TO_EVENT = {
    "mesh.audit": "audit",
    "mesh.guardrails": "guardrail-event",
    "mesh.registrations": "registration",
    "mesh.alerts": "alert",
    "mesh.cost": "cost-event",
}


class WSBroadcasterConsumer(BaseConsumer):
    """Subscribes to all mesh topics and broadcasts to Socket.IO /mesh namespace.

    Uses the external Redis message queue (already configured for Socket.IO)
    so events reach all connected frontend clients regardless of which
    registry replica they're connected to.
    """

    def __init__(self, flask_app=None, **kwargs):
        super().__init__(
            group_id="ws-broadcaster",
            topics=ALL_TOPICS,
            **kwargs,
        )
        self._flask_app = flask_app
        self._socketio = None

    def _get_socketio(self):
        if self._socketio is None and self._flask_app:
            from app.services.mesh_events import socketio
            self._socketio = socketio
        return self._socketio

    def process_message(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        socketio = self._get_socketio()
        if not socketio:
            return

        event_name = TOPIC_TO_EVENT.get(topic)
        if not event_name:
            return

        try:
            socketio.emit(event_name, value, namespace="/mesh")
        except Exception as exc:
            logger.error("Failed to emit %s event: %s", event_name, exc)
