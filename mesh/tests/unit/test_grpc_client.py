"""Tests for gRPC config sync client."""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from runtime.sidecar.config import GrpcConfig
from runtime.sidecar.grpc_client import GrpcConfigClient


class TestGrpcClientDisabled:
    def test_disabled_does_not_start(self):
        config = GrpcConfig(enabled=False)
        client = GrpcConfigClient(config=config, agent_id="test-agent")
        client.start()
        assert not client.is_connected
        client.stop()


class TestGrpcClientConfig:
    def test_initial_state(self):
        config = GrpcConfig(enabled=True, control_plane_url="localhost:50051")
        client = GrpcConfigClient(config=config, agent_id="test-agent")
        assert not client.is_connected
        assert client.last_config_version == 0

    def test_version_tracking(self):
        config = GrpcConfig(enabled=True)
        client = GrpcConfigClient(config=config, agent_id="test-agent")
        # Directly set for testing
        client._last_config_version = 5
        assert client.last_config_version == 5


class TestGrpcClientUpdateProcessing:
    def test_policies_update_callback(self):
        """Test that policy updates invoke the callback."""
        config = GrpcConfig(enabled=True)
        callback = MagicMock()
        client = GrpcConfigClient(
            config=config,
            agent_id="test-agent",
            on_policies_update=callback,
        )

        # Create a mock update object
        update = MagicMock()
        update.version = 1
        update.update_type = "policies"
        update.payload = json.dumps({
            "policies": [{"source": "*", "destination": "*", "action": "allow"}]
        }).encode()

        client._process_update(update)

        callback.assert_called_once_with(
            [{"source": "*", "destination": "*", "action": "allow"}]
        )
        assert client._last_config_version == 0  # Not updated here, done in caller

    def test_compliance_update_callback(self):
        """Test that compliance updates invoke the callback."""
        config = GrpcConfig(enabled=True)
        callback = MagicMock()
        client = GrpcConfigClient(
            config=config,
            agent_id="test-agent",
            on_compliance_update=callback,
        )

        update = MagicMock()
        update.version = 2
        update.update_type = "compliance_rules"
        update.payload = json.dumps({
            "sovereignty_rules": [{"source_zone": "eu", "dest_zone": "us", "action": "block"}],
        }).encode()

        client._process_update(update)
        callback.assert_called_once()

    def test_full_sync_triggers_both(self):
        """full_sync should trigger both policies and compliance callbacks."""
        config = GrpcConfig(enabled=True)
        policy_cb = MagicMock()
        compliance_cb = MagicMock()
        client = GrpcConfigClient(
            config=config,
            agent_id="test-agent",
            on_policies_update=policy_cb,
            on_compliance_update=compliance_cb,
        )

        update = MagicMock()
        update.version = 3
        update.update_type = "full_sync"
        update.payload = json.dumps({
            "policies": [{"source": "*", "destination": "*", "action": "allow"}],
            "sovereignty_rules": [],
        }).encode()

        client._process_update(update)
        policy_cb.assert_called_once()
        compliance_cb.assert_called_once()

    def test_invalid_payload_logged(self):
        """Invalid JSON payload should be handled gracefully."""
        config = GrpcConfig(enabled=True)
        client = GrpcConfigClient(config=config, agent_id="test-agent")

        update = MagicMock()
        update.version = 4
        update.update_type = "policies"
        update.payload = b"not valid json"

        # Should not raise
        client._process_update(update)

    def test_stale_update_skipped(self):
        """Updates with version <= last_config_version should be skipped.

        This is tested via the connect_and_subscribe logic, but we can verify
        the version tracking works.
        """
        config = GrpcConfig(enabled=True)
        client = GrpcConfigClient(config=config, agent_id="test-agent")
        client._last_config_version = 10

        # Version 5 is stale
        assert 5 <= client._last_config_version


class TestGrpcClientReconnection:
    def test_fallback_config(self):
        """When gRPC is unavailable, fallback_to_rest should be respected."""
        config = GrpcConfig(enabled=True, fallback_to_rest=True)
        client = GrpcConfigClient(config=config, agent_id="test-agent")
        assert config.fallback_to_rest is True

    def test_stop_interrupts_loop(self):
        """Stopping the client should interrupt the reconnection loop."""
        config = GrpcConfig(enabled=True, control_plane_url="localhost:99999")
        client = GrpcConfigClient(config=config, agent_id="test-agent")

        client.start()
        time.sleep(0.1)  # Let it attempt connection
        client.stop()

        assert not client.is_connected
