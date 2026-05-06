"""Sidecar lifecycle manager — handles startup, heartbeat, and shutdown.

Manages the sidecar's relationship with the registry control plane:
- On startup: register with registry, fetch policies
- While running: periodic heartbeat, policy sync, audit flush
- On shutdown: flush audit records, deregister from registry
"""

from __future__ import annotations

import asyncio
import signal
import threading
from typing import Any, Optional

import structlog

from runtime.common.models import AuditRecord
from runtime.sidecar.config import SidecarConfig
from runtime.sidecar.interceptors.audit import AuditInterceptor
from runtime.sidecar.interceptors.authentication import AuthenticationInterceptor
from runtime.sidecar.interceptors.authorisation import AuthorisationInterceptor
from runtime.sidecar.interceptors.compliance import ComplianceInterceptor
from runtime.sidecar.registry_client import RegistryClient, RegistryClientError

logger = structlog.get_logger()


class LifecycleManager:
    """Manages the sidecar's lifecycle with the registry control plane.

    Handles registration, periodic heartbeat, policy sync, audit flushing,
    and graceful deregistration on shutdown.
    """

    def __init__(
        self,
        config: SidecarConfig,
        registry_client: RegistryClient,
        authz_interceptor: AuthorisationInterceptor,
        audit_interceptor: AuditInterceptor,
        agent_card_json: dict[str, Any],
        compliance_interceptor: ComplianceInterceptor | None = None,
        auth_interceptor: AuthenticationInterceptor | None = None,
        pre_guardrail_interceptor=None,
        post_guardrail_interceptor=None,
    ):
        self._config = config
        self._registry = registry_client
        self._authz = authz_interceptor
        self._audit = audit_interceptor
        self._compliance = compliance_interceptor
        self._auth = auth_interceptor
        self._pre_guardrail = pre_guardrail_interceptor
        self._post_guardrail = post_guardrail_interceptor
        self._agent_card_json = agent_card_json
        self._sidecar_url: str | None = None

        self._running = False
        self._registered = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._policy_thread: Optional[threading.Thread] = None
        self._audit_thread: Optional[threading.Thread] = None
        self._tool_sync_thread: Optional[threading.Thread] = None
        self._retry_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    def startup(self) -> dict[str, Any]:
        """Perform startup sequence: register and start background tasks.

        Returns the registration response from the registry.
        No-ops if already registered.

        Raises:
            RegistryClientError: If registration fails.
        """
        if self._registered:
            return {"status": "already_registered"}

        if not self._config.agent_id:
            logger.warning("no_agent_id_configured", msg="Skipping mesh registration")
            return {"status": "skipped", "reason": "no agent_id configured"}

        import os
        advertise_host = os.environ.get("SIDECAR_ADVERTISE_HOST", "localhost")
        default_port = str(self._config.a2a_port if self._config.tls else self._config.port)
        advertise_port = os.environ.get("SIDECAR_ADVERTISE_PORT", default_port)
        default_scheme = "https" if self._config.tls else "http"
        advertise_scheme = os.environ.get("SIDECAR_ADVERTISE_SCHEME", default_scheme)
        sidecar_url = f"{advertise_scheme}://{advertise_host}:{advertise_port}"
        self._sidecar_url = sidecar_url

        # Register with registry (all registries in multi-cluster mode)
        if len(self._registry.all_registry_urls) > 1:
            result = self._registry.register_all(
                agent_id=self._config.agent_id,
                sidecar_url=sidecar_url,
                agent_card=self._agent_card_json,
                sovereignty_zone=None,
            )
        else:
            result = self._registry.register(
                agent_id=self._config.agent_id,
                sidecar_url=sidecar_url,
                agent_card=self._agent_card_json,
                sovereignty_zone=None,
            )

        # Wire registry client into authz interceptor for governance checks
        self._authz.set_registry_client(self._registry)

        # Apply policies from registration response
        policies = self._registry.cached_policies
        if policies:
            self._authz.update_policies(policies)
            logger.info("policies_applied", count=len(policies))

        # Sync registered agents for identity verification
        self._sync_registered_agents()

        # Mark as registered and start background tasks
        self._registered = True
        self._running = True
        self._stop_event.clear()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat"
        )
        self._heartbeat_thread.start()

        self._policy_thread = threading.Thread(
            target=self._policy_sync_loop, daemon=True, name="policy-sync"
        )
        self._policy_thread.start()

        self._audit_thread = threading.Thread(
            target=self._audit_flush_loop, daemon=True, name="audit-flush"
        )
        self._audit_thread.start()

        self._tool_sync_thread = threading.Thread(
            target=self._tool_sync_loop, daemon=True, name="tool-sync"
        )
        self._tool_sync_thread.start()

        logger.info("lifecycle_started", agent_id=self._config.agent_id)
        return result

    def start_retry_loop(self) -> None:
        """Start a background thread that retries registration periodically.

        Called when initial startup() fails (e.g. agent not yet ACTIVE).
        The loop retries every heartbeat_interval_seconds until successful.
        """
        if self._registered or self._retry_thread is not None:
            return

        logger.info("registration_retry_starting",
                     interval=self._config.heartbeat_interval_seconds)
        self._retry_thread = threading.Thread(
            target=self._registration_retry_loop, daemon=True, name="reg-retry"
        )
        self._retry_thread.start()

    def _registration_retry_loop(self) -> None:
        """Periodically retry startup() until registration succeeds."""
        interval = self._config.heartbeat_interval_seconds
        while not self._stop_event.wait(timeout=interval):
            if self._registered:
                break
            try:
                self.startup()
                logger.info("registration_retry_succeeded",
                            agent_id=self._config.agent_id)
                break
            except Exception as exc:
                logger.debug("registration_retry_failed", error=str(exc))

    def shutdown(self) -> None:
        """Perform graceful shutdown: flush audit, stop tasks, deregister."""
        if not self._running and not self._retry_thread:
            return

        logger.info("lifecycle_shutdown_starting")
        self._running = False
        self._stop_event.set()

        # Wait for background threads to finish
        for thread in [self._heartbeat_thread, self._policy_thread,
                       self._audit_thread, self._tool_sync_thread,
                       self._retry_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)

        # Flush pending audit records
        self._flush_audit()

        # Deregister from registry (all registries in multi-cluster mode)
        # Pass our sidecar_url so the registry only deletes if it matches,
        # preventing a terminating pod from removing a replacement pod's registration.
        if self._config.agent_id:
            try:
                if len(self._registry.all_registry_urls) > 1:
                    self._registry.deregister_all(self._config.agent_id, sidecar_url=self._sidecar_url)
                else:
                    self._registry.deregister(self._config.agent_id, sidecar_url=self._sidecar_url)
            except RegistryClientError:
                logger.warning("deregister_failed_on_shutdown")

        # Stop registry client background threads
        self._registry.stop()

        logger.info("lifecycle_shutdown_complete")

    def install_signal_handlers(self) -> None:
        """Install SIGTERM and SIGINT handlers for graceful shutdown."""
        def _handler(signum, frame):
            logger.info("signal_received", signal=signum)
            self.shutdown()

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

    # -----------------------------------------------------------------
    # Background loops
    # -----------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to registry (all registries in multi-cluster).

        If the heartbeat gets a 404 (registration lost — e.g. due to a rolling
        update race), automatically re-register.
        """
        interval = self._config.heartbeat_interval_seconds
        while not self._stop_event.wait(timeout=interval):
            if not self._config.agent_id:
                continue
            try:
                if len(self._registry.all_registry_urls) > 1:
                    self._registry.heartbeat_all(self._config.agent_id)
                else:
                    self._registry.heartbeat(self._config.agent_id)
            except RegistryClientError as e:
                logger.warning("heartbeat_failed")
                # Re-register if heartbeat failed (registration may have been
                # removed by a terminating pod during a rolling update)
                if self._sidecar_url and self._config.agent_id:
                    try:
                        self._registry.register(
                            agent_id=self._config.agent_id,
                            sidecar_url=self._sidecar_url,
                            agent_card=self._agent_card_json,
                        )
                        logger.info("re_registered_after_heartbeat_failure",
                                    agent_id=self._config.agent_id)
                    except RegistryClientError:
                        logger.warning("re_registration_failed")

    def _policy_sync_loop(self) -> None:
        """Periodically fetch policies, compliance rules, and registered agents."""
        interval = self._config.policy_sync_interval_seconds
        while not self._stop_event.wait(timeout=interval):
            try:
                policies = self._registry.fetch_policies()
                self._authz.update_policies(policies)
            except RegistryClientError:
                logger.warning("policy_sync_failed")

            # Sync compliance rules
            if self._compliance:
                try:
                    rules = self._registry.fetch_compliance_rules()
                    self._compliance.update_rules(
                        sovereignty_rules=rules.get("sovereignty_rules"),
                        classification_rules=rules.get("classification_rules"),
                    )
                except RegistryClientError:
                    logger.warning("compliance_rules_sync_failed")

            # Sync registered agents for identity verification
            self._sync_registered_agents()

    def _sync_registered_agents(self) -> None:
        """Fetch registered agent names and update the auth interceptor."""
        if not self._auth:
            return
        try:
            names = self._registry.fetch_registered_agents()
            if names:
                self._auth.update_registered_agents(names)
                logger.debug("registered_agents_synced", count=len(names))
        except Exception:
            logger.warning("registered_agents_sync_failed")

    def _tool_sync_loop(self) -> None:
        """Periodically fetch tool assignments and egress rules from registry."""
        interval = self._config.tool_sync_interval_seconds
        agent_name = self._agent_card_json.get("name")
        if not agent_name:
            logger.warning("tool_sync_skipped_no_agent_name")
            return

        while not self._stop_event.wait(timeout=interval):
            try:
                self._registry.fetch_tools_for_agent(agent_name)
            except Exception:
                logger.warning("tool_sync_failed")
            try:
                self._registry.fetch_egress_rules_for_agent(agent_name)
            except Exception:
                logger.warning("egress_rules_sync_failed")
            # Sync guardrails
            try:
                guardrails = self._registry.fetch_guardrails_for_agent(agent_name)
                if self._pre_guardrail:
                    self._pre_guardrail.update_guardrails(guardrails)
                if self._post_guardrail:
                    self._post_guardrail.update_guardrails(guardrails)
            except Exception:
                logger.warning("guardrail_sync_failed")
            # Ship guardrail evaluation events to registry
            self._flush_guardrail_events(agent_name)

    def _flush_guardrail_events(self, agent_name: str) -> None:
        """Drain guardrail evaluator event buffer and ship to registry."""
        evaluator = None
        if self._pre_guardrail:
            evaluator = getattr(self._pre_guardrail, '_evaluator', None)
        if evaluator is None and self._post_guardrail:
            evaluator = getattr(self._post_guardrail, '_evaluator', None)
        if evaluator is None:
            return

        events = evaluator.drain_events()
        if not events:
            return

        try:
            self._registry.ship_guardrail_events(events, agent_name)
        except Exception:
            logger.warning("guardrail_events_flush_failed", count=len(events))

    def _audit_flush_loop(self) -> None:
        """Periodically flush buffered audit records to registry."""
        interval = self._audit._config.flush_interval_seconds
        while not self._stop_event.wait(timeout=interval):
            self._flush_audit()

    def _flush_audit(self) -> None:
        """Flush buffered audit records to the registry."""
        records = self._audit.drain_buffer()
        if not records:
            return

        serialized = [self._serialize_audit_record(r) for r in records]
        try:
            self._registry.ship_audit_records(serialized)
        except RegistryClientError:
            logger.warning("audit_flush_failed", count=len(records))
            # Re-buffer the records (best effort — some may be lost if buffer is full)
            for r in records:
                self._audit._buffer.append(r)

    @staticmethod
    def _serialize_audit_record(record: AuditRecord) -> dict[str, Any]:
        """Serialize an AuditRecord for shipping to the registry."""
        return {
            "timestamp": record.timestamp.isoformat(),
            "source_agent_id": record.source_agent_id,
            "source_agent_name": record.source_agent_name,
            "dest_agent_id": record.dest_agent_id,
            "dest_agent_name": record.dest_agent_name,
            "task_id": record.task_id,
            "a2a_method": record.a2a_method,
            "message_hash": record.message_hash,
            "direction": record.direction.value,
            "decision": record.decision,
            "outcome": record.outcome,
            "details": (
                [
                    {
                        "interceptor": d.interceptor,
                        "action": d.action.value,
                        "reason": d.reason,
                    }
                    for d in record.interceptor_decisions
                ]
                if record.interceptor_decisions
                else None
            ),
            "sidecar_id": record.sidecar_id,
            "record_hash": record.record_hash,
            "previous_record_hash": record.previous_record_hash,
            "sequence_number": record.sequence_number,
            **({"details": record.details} if record.details else {}),
        }
