"""gRPC client for push-based config sync with the registry control plane.

Connects to the registry's gRPC ConfigSync service, subscribes to config
updates, and applies them to interceptors. Falls back to REST polling
if the gRPC connection drops.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

import structlog

from runtime.sidecar.config import GrpcConfig

logger = structlog.get_logger()


class GrpcConfigClient:
    """gRPC streaming client for receiving config updates from the registry.

    Connects on startup, subscribes with agent_id, and receives a stream
    of ConfigUpdate messages. Falls back to REST polling on disconnect.
    """

    def __init__(
        self,
        config: GrpcConfig,
        agent_id: str,
        tenant_id: str = "default",
        on_policies_update: Optional[Callable] = None,
        on_compliance_update: Optional[Callable] = None,
    ):
        self._config = config
        self._agent_id = agent_id
        self._tenant_id = tenant_id
        self._on_policies_update = on_policies_update
        self._on_compliance_update = on_compliance_update

        self._last_config_version: int = 0
        self._connected = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_config_version(self) -> int:
        return self._last_config_version

    def start(self) -> None:
        """Start the gRPC client in a background thread."""
        if not self._config.enabled:
            logger.info("grpc_disabled")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="grpc-config-sync"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the gRPC client."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        """Main loop: connect, subscribe, process updates, reconnect on failure."""
        backoff = 1.0
        max_backoff = 30.0

        while not self._stop_event.is_set():
            try:
                self._connect_and_subscribe()
                backoff = 1.0  # Reset on successful connection
            except Exception as e:
                self._connected = False
                logger.warning(
                    "grpc_connection_failed",
                    error=str(e),
                    retry_in=f"{backoff:.1f}s",
                )
                if self._stop_event.wait(timeout=backoff):
                    break
                backoff = min(backoff * 2, max_backoff)

    def _connect_and_subscribe(self) -> None:
        """Connect to the gRPC server and process the config update stream."""
        try:
            import grpc
            from proto import config_sync_pb2, config_sync_pb2_grpc
        except ImportError:
            logger.error("grpc_import_failed", msg="grpcio or proto modules not available")
            raise

        channel = grpc.insecure_channel(self._config.control_plane_url)
        stub = config_sync_pb2_grpc.ConfigSyncStub(channel)

        request = config_sync_pb2.SubscribeRequest(
            agent_id=self._agent_id,
            sidecar_id=f"sidecar-{self._agent_id}",
            tenant_id=self._tenant_id,
            last_config_version=self._last_config_version,
        )

        logger.info("grpc_subscribing", url=self._config.control_plane_url)
        self._connected = True

        try:
            for update in stub.Subscribe(request):
                if self._stop_event.is_set():
                    break

                # Skip stale updates
                if update.version <= self._last_config_version:
                    logger.debug("grpc_stale_update", version=update.version)
                    continue

                self._process_update(update)
                self._last_config_version = update.version
        finally:
            self._connected = False
            channel.close()

    def _process_update(self, update: Any) -> None:
        """Process a config update from the gRPC stream."""
        try:
            payload = json.loads(update.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.error("grpc_invalid_payload", version=update.version)
            return

        logger.info(
            "grpc_config_update",
            version=update.version,
            update_type=update.update_type,
        )

        if update.update_type in ("policies", "full_sync"):
            if self._on_policies_update and "policies" in payload:
                self._on_policies_update(payload["policies"])

        if update.update_type in ("compliance_rules", "full_sync"):
            if self._on_compliance_update:
                self._on_compliance_update(payload)

    def report_status(self, status: str = "healthy", metrics: dict[str, str] | None = None) -> bool:
        """Report sidecar status to the control plane via gRPC."""
        if not self._connected:
            return False

        try:
            import grpc
            from proto import config_sync_pb2, config_sync_pb2_grpc

            channel = grpc.insecure_channel(self._config.control_plane_url)
            stub = config_sync_pb2_grpc.ConfigSyncStub(channel)

            report = config_sync_pb2.StatusReport(
                agent_id=self._agent_id,
                sidecar_id=f"sidecar-{self._agent_id}",
                status=status,
                metrics=metrics or {},
            )

            response = stub.ReportStatus(report, timeout=5)
            channel.close()
            return response.acknowledged

        except Exception as e:
            logger.warning("grpc_status_report_failed", error=str(e))
            return False
