"""Entry point for running the sidecar as a standalone process.

Usage:
    python -m runtime.sidecar --config /path/to/recursant-sidecar.yaml

Or via environment variables:
    SIDECAR_PORT=9901 SIDECAR_REGISTRY_URL=http://registry:5000 python -m runtime.sidecar
"""

from __future__ import annotations

import argparse
import os
import ssl
import sys
import threading
from typing import Optional

import structlog
from werkzeug.serving import make_server, WSGIRequestHandler

from runtime.sidecar.app import create_app
from runtime.sidecar.config import SidecarConfig
from runtime.sidecar.lifecycle import LifecycleManager
from runtime.sidecar.registry_client import RegistryClient


class _PeerCertHandler(WSGIRequestHandler):
    """Custom WSGI handler that injects the client TLS certificate into environ.

    When the server uses mTLS (ssl_context with CERT_REQUIRED), the peer
    certificate is available on the raw socket. This handler copies it into
    the WSGI ``environ`` dict as ``peercert`` so that
    ``_extract_client_cert_cn()`` can read it.
    """

    def make_environ(self):
        environ = super().make_environ()
        if hasattr(self.request, "getpeercert"):
            peer_cert = self.request.getpeercert()
            if peer_cert:
                environ["peercert"] = peer_cert
        return environ


def _setup_registry_and_lifecycle(app, config, logger):
    """Wire up the registry client + lifecycle once config.agent_id is known.

    Extracted so the background agent_id resolver can complete startup once
    the agent finally appears in the registry, without restarting the pod.
    """
    registry_urls = config.registry_urls or [config.registry_url]
    registry_client = RegistryClient(
        registry_url=config.registry_url,
        registry_urls=registry_urls,
        api_key=config.registry_api_key,
        cache_ttl=config.discovery_cache_ttl_seconds,
        failover_timeout=config.registry_failover_timeout,
    )

    lifecycle = LifecycleManager(
        config=config,
        registry_client=registry_client,
        authz_interceptor=app.config["AUTHZ_INTERCEPTOR"],
        audit_interceptor=app.config["AUDIT_INTERCEPTOR"],
        agent_card_json=app.config["AGENT_CARD_JSON"],
        compliance_interceptor=app.config.get("COMPLIANCE_INTERCEPTOR"),
        pre_guardrail_interceptor=app.config.get("PRE_GUARDRAIL_INTERCEPTOR"),
        post_guardrail_interceptor=app.config.get("POST_GUARDRAIL_INTERCEPTOR"),
    )

    app.config["RESOLVE_DESTINATION"] = registry_client.resolve_destination
    app.config["RESOLVE_DESTINATIONS"] = registry_client.resolve_destinations
    app.config["REGISTRY_CLIENT"] = registry_client

    lifecycle.install_signal_handlers()

    try:
        lifecycle.startup()
        logger.info("lifecycle_ready", agent_id=config.agent_id)
    except Exception as e:
        logger.error("lifecycle_startup_failed", error=str(e))
        logger.info("starting_registration_retry_loop")
        lifecycle.start_retry_loop()

    app.config["LIFECYCLE"] = lifecycle

    import atexit
    atexit.register(lifecycle.shutdown)


def main():
    parser = argparse.ArgumentParser(description="Recursant Sidecar")
    parser.add_argument("--config", help="Path to recursant-sidecar.yaml")
    args = parser.parse_args()

    # Load config from file or environment
    if args.config:
        config = SidecarConfig.from_yaml(args.config)
    else:
        config = SidecarConfig.from_env()

    # Apply overrides from env vars (these take precedence)
    if os.environ.get("SIDECAR_REGISTRY_URL"):
        config.registry_url = os.environ["SIDECAR_REGISTRY_URL"]
    if os.environ.get("SIDECAR_AGENT_ID"):
        config.agent_id = os.environ["SIDECAR_AGENT_ID"]
    if os.environ.get("SIDECAR_REGISTRY_API_KEY"):
        config.registry_api_key = os.environ["SIDECAR_REGISTRY_API_KEY"]
    if os.environ.get("SIDECAR_AGENT_HOST"):
        config.agent_host = os.environ["SIDECAR_AGENT_HOST"]

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            {"debug": 10, "info": 20, "warn": 30, "error": 40}.get(
                config.log_level.value, 20
            )
        ),
    )

    logger = structlog.get_logger()
    logger.info(
        "sidecar_starting",
        port=config.port,
        a2a_port=config.a2a_port,
        agent_port=config.agent_port,
        registry_url=config.registry_url,
    )

    app = create_app(config)

    # Resolve agent_id from name if not directly provided. The agent may be
    # seeded into the registry AFTER the sidecar starts (race condition during
    # cluster bootstrap or rolling deploys), so retry with backoff. Capping at
    # ~30s of synchronous retries keeps startup fast for the happy path; if it
    # still fails, a background thread keeps trying so the sidecar self-heals
    # once the agent appears, no pod restart needed.
    agent_name = os.environ.get("SIDECAR_AGENT_NAME")
    if not config.agent_id and agent_name and config.registry_url:
        from runtime.sidecar.registry_client import RegistryClient as _RC
        _lookup_client = _RC(
            registry_url=config.registry_url,
            api_key=config.registry_api_key,
        )

        def _resolve_agent_id_sync(max_attempts: int) -> Optional[str]:
            import time as _time
            for attempt in range(max_attempts):
                try:
                    rid = _lookup_client.lookup_agent_id_by_name(agent_name)
                    if rid:
                        return rid
                except Exception as exc:
                    logger.debug("agent_id_lookup_exception", error=str(exc))
                if attempt < max_attempts - 1:
                    _time.sleep(min(2 ** attempt, 8))
            return None

        logger.info("looking_up_agent_id", agent_name=agent_name)
        resolved_id = _resolve_agent_id_sync(max_attempts=6)  # ~31s total
        if resolved_id:
            config.agent_id = resolved_id
            logger.info("agent_id_resolved", agent_id=resolved_id)
        else:
            logger.warning(
                "agent_id_lookup_failed_starting_background_retry",
                agent_name=agent_name,
            )

            import threading as _threading
            import time as _time

            def _background_resolve_and_setup():
                """Keep retrying until the agent appears in the registry, then
                complete the registry_client + lifecycle wiring that the main
                startup path skipped."""
                attempt = 0
                while True:
                    try:
                        rid = _lookup_client.lookup_agent_id_by_name(agent_name)
                        if rid:
                            config.agent_id = rid
                            logger.info(
                                "agent_id_resolved_background",
                                agent_id=rid,
                                attempts=attempt + 1,
                            )
                            try:
                                _setup_registry_and_lifecycle(app, config, logger)
                            except Exception as exc:
                                logger.error(
                                    "background_lifecycle_setup_failed",
                                    error=str(exc),
                                )
                            return
                    except Exception as exc:
                        logger.debug(
                            "background_agent_id_lookup_exception",
                            error=str(exc),
                        )
                    attempt += 1
                    _time.sleep(min(2 ** min(attempt, 5), 30))

            _threading.Thread(
                target=_background_resolve_and_setup,
                daemon=True,
                name="agent-id-resolver",
            ).start()

    # Set up registry client and lifecycle if agent_id is configured.
    # If it's not, the background resolver thread (started above) will call
    # _setup_registry_and_lifecycle() once the agent appears in the registry.
    if config.agent_id:
        _setup_registry_and_lifecycle(app, config, logger)

    # Start mTLS listener on A2A port (if TLS is configured)
    if config.tls:
        from runtime.sidecar.cert_rotation import CertRotationManager, ReloadableSSLContext

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(config.tls.cert_path, config.tls.key_path)
        ctx.load_verify_locations(config.tls.ca_path)
        ctx.verify_mode = ssl.CERT_REQUIRED

        ssl_holder = ReloadableSSLContext(ctx)

        tls_server = make_server(
            "0.0.0.0",
            config.a2a_port,
            app,
            ssl_context=ssl_holder.context,
            request_handler=_PeerCertHandler,
        )
        tls_thread = threading.Thread(
            target=tls_server.serve_forever,
            daemon=True,
            name="a2a-tls",
        )
        tls_thread.start()
        logger.info(
            "a2a_tls_listener_started",
            port=config.a2a_port,
            cert=config.tls.cert_path,
        )

        # Start certificate auto-rotation if enabled
        if config.tls.rotation_enabled:
            rotation_manager = CertRotationManager(
                tls_config=config.tls,
                ssl_holder=ssl_holder,
                registry_url=config.registry_url,
                api_key=config.registry_api_key,
                agent_id=config.agent_id,
            )
            rotation_manager.start()
            app.config["CERT_ROTATION_MANAGER"] = rotation_manager

            import atexit
            atexit.register(rotation_manager.stop)

    # Run Flask (plain HTTP proxy port — local agent ↔ sidecar)
    app.run(
        host="0.0.0.0",
        port=config.port,
        debug=False,
    )


if __name__ == "__main__":
    main()
