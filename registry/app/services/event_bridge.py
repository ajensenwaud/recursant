"""Cross-cluster event bridge for multi-cluster HA.

Connects to a remote registry's SSE event stream and re-broadcasts
received events to the local Socket.IO instance, so the mesh
visualiser on either cluster shows events from both clusters.

Runs as a background daemon thread, started automatically when
CLUSTER_ID and REMOTE_REGISTRY_URL are both configured.
"""

import json
import logging
import threading
import time

import httpx

logger = logging.getLogger(__name__)

# Maximum backoff between reconnection attempts (seconds)
_MAX_BACKOFF = 60


class EventBridge:
    """Bridges mesh events from a remote registry to the local Socket.IO."""

    def __init__(
        self,
        remote_registry_url: str,
        mesh_api_key: str | None,
        socketio,
        local_cluster_id: str = "default",
    ):
        self._remote_url = remote_registry_url.rstrip("/")
        self._api_key = mesh_api_key
        self._socketio = socketio
        self._cluster_id = local_cluster_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the bridge background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="event-bridge",
        )
        self._thread.start()
        logger.info("Event bridge started: remote=%s", self._remote_url)

    def stop(self) -> None:
        """Signal the bridge to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Main loop: connect to remote SSE stream, process events, reconnect on failure."""
        backoff = 1
        while not self._stop_event.is_set():
            try:
                self._stream_events()
                backoff = 1  # reset on clean exit
            except Exception as e:
                logger.warning("Event bridge connection lost: %s (retry in %ds)", e, backoff)
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

    def _stream_events(self) -> None:
        """Connect to the remote /v1/mesh/events/stream SSE endpoint."""
        url = f"{self._remote_url}/v1/mesh/events/stream"
        headers = {}
        if self._api_key:
            headers["X-Mesh-API-Key"] = self._api_key

        with httpx.stream("GET", url, headers=headers, timeout=None) as resp:
            resp.raise_for_status()
            buffer = ""
            for chunk in resp.iter_text():
                if self._stop_event.is_set():
                    return
                buffer += chunk
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    self._process_sse_event(event_text)

    def _process_sse_event(self, raw: str) -> None:
        """Parse a single SSE event and re-broadcast via local Socket.IO."""
        event_type = None
        data_lines = []

        for line in raw.strip().split("\n"):
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())

        if not event_type or not data_lines:
            return

        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            logger.debug("Event bridge: invalid JSON in SSE data")
            return

        # Tag event with remote origin to avoid echo loops
        data["_remote_cluster"] = True

        if event_type in ("registration", "audit"):
            self._socketio.emit(event_type, data, namespace="/mesh")
            logger.debug("Event bridge relayed %s event", event_type)
