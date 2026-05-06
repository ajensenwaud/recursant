"""Certificate auto-rotation manager.

Monitors TLS certificate expiry, generates CSRs, requests renewal
from the registry CA, and hot-swaps the SSL context.
"""

from __future__ import annotations

import ssl
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import structlog

from runtime.sidecar.config import TLSConfig

logger = structlog.get_logger()


class ReloadableSSLContext:
    """Thread-safe holder for an SSL context that can be atomically swapped.

    The TLS listener reads from this holder. On rotation, a new SSLContext
    is built and swapped in atomically.
    """

    def __init__(self, ctx: ssl.SSLContext):
        self._lock = threading.Lock()
        self._ctx = ctx

    @property
    def context(self) -> ssl.SSLContext:
        with self._lock:
            return self._ctx

    def swap(self, new_ctx: ssl.SSLContext) -> None:
        with self._lock:
            self._ctx = new_ctx
        logger.info("ssl_context_swapped")


class CertRotationManager:
    """Background thread that monitors cert expiry and triggers rotation.

    Workflow:
    1. Periodically read the cert file and check expiry
    2. If within ``renewal_days_before_expiry``, generate a CSR
    3. Send CSR to registry ``POST /v1/mesh/certificates/renew``
    4. Write new cert/key to disk
    5. Rebuild SSL context and swap into ReloadableSSLContext
    """

    def __init__(
        self,
        tls_config: TLSConfig,
        ssl_holder: ReloadableSSLContext,
        registry_url: str,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        self._tls_config = tls_config
        self._ssl_holder = ssl_holder
        self._registry_url = registry_url.rstrip("/")
        self._api_key = api_key
        self._agent_id = agent_id

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the rotation monitoring thread."""
        if not self._tls_config.rotation_enabled:
            return

        self._thread = threading.Thread(
            target=self._rotation_loop,
            daemon=True,
            name="cert-rotation",
        )
        self._thread.start()
        logger.info(
            "cert_rotation_started",
            interval=self._tls_config.rotation_check_interval_seconds,
            renewal_days=self._tls_config.renewal_days_before_expiry,
        )

    def stop(self) -> None:
        """Stop the rotation thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _rotation_loop(self) -> None:
        """Periodically check cert expiry and rotate if needed."""
        interval = self._tls_config.rotation_check_interval_seconds

        while not self._stop_event.wait(timeout=interval):
            try:
                self._check_and_rotate()
            except Exception as e:
                logger.error("cert_rotation_error", error=str(e))

    def _check_and_rotate(self) -> None:
        """Check current cert expiry and rotate if within threshold."""
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        cert_path = Path(self._tls_config.cert_path)
        if not cert_path.exists():
            logger.warning("cert_file_missing", path=str(cert_path))
            return

        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)

        now = datetime.now(timezone.utc)
        days_until_expiry = (cert.not_valid_after_utc - now).days

        logger.info(
            "cert_expiry_check",
            days_until_expiry=days_until_expiry,
            not_after=cert.not_valid_after_utc.isoformat(),
        )

        if days_until_expiry > self._tls_config.renewal_days_before_expiry:
            return  # Not yet time to renew

        logger.info("cert_rotation_triggered", days_until_expiry=days_until_expiry)

        # Generate CSR
        csr_pem, new_key_pem = self._generate_csr(cert)

        # Request signed cert from registry
        new_cert_pem = self._request_signed_cert(csr_pem)
        if not new_cert_pem:
            logger.error("cert_rotation_failed", reason="no cert returned from registry")
            return

        # Write new cert and key to disk
        cert_path.write_bytes(new_cert_pem)
        key_path = Path(self._tls_config.key_path)
        key_path.write_bytes(new_key_pem)

        # Rebuild and swap SSL context
        new_ctx = self._build_ssl_context()
        self._ssl_holder.swap(new_ctx)

        logger.info("cert_rotation_complete")

    def _generate_csr(self, current_cert: Any) -> tuple[bytes, bytes]:
        """Generate a CSR reusing the subject from the current cert.

        Returns (csr_pem, new_private_key_pem).
        """
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate new key pair
        new_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Build CSR with same subject as current cert
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(current_cert.subject)

        # Carry over SANs if present
        try:
            san_ext = current_cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            builder = builder.add_extension(san_ext.value, critical=False)
        except x509.ExtensionNotFound:
            pass

        csr = builder.sign(new_key, hashes.SHA256())

        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        key_pem = new_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )

        return csr_pem, key_pem

    def _request_signed_cert(self, csr_pem: bytes) -> bytes | None:
        """Send CSR to registry for signing."""
        import httpx

        headers: dict[str, str] = {"X-Tenant-ID": "default"}
        if self._api_key:
            headers["X-Mesh-API-Key"] = self._api_key

        try:
            resp = httpx.post(
                f"{self._registry_url}/v1/mesh/certificates/renew",
                json={
                    "agent_id": self._agent_id,
                    "csr_pem": csr_pem.decode(),
                },
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["certificate_pem"].encode()

        except Exception as e:
            logger.error("cert_renewal_request_failed", error=str(e))
            return None

    def _build_ssl_context(self) -> ssl.SSLContext:
        """Build a new SSL context from the (rotated) cert files on disk."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self._tls_config.cert_path, self._tls_config.key_path)
        ctx.load_verify_locations(self._tls_config.ca_path)
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx
