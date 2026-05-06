"""Simple Certificate Authority service.

Signs CSRs using a root CA cert/key for sidecar certificate renewal.
Tracks issued certificates for audit.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)


class CAService:
    """Signs CSRs using a configured CA key pair."""

    def __init__(
        self,
        ca_cert_path: str | None = None,
        ca_key_path: str | None = None,
        cert_validity_days: int = 365,
    ):
        self._ca_cert_path = ca_cert_path or os.environ.get(
            "CA_CERT_PATH", "docker/certs/ca.pem"
        )
        self._ca_key_path = ca_key_path or os.environ.get(
            "CA_KEY_PATH", "docker/certs/ca-key.pem"
        )
        self._cert_validity_days = cert_validity_days
        self._ca_cert = None
        self._ca_key = None

    def _load_ca(self) -> None:
        """Lazy-load CA cert and key."""
        if self._ca_cert is not None:
            return

        ca_cert_path = Path(self._ca_cert_path)
        ca_key_path = Path(self._ca_key_path)

        if not ca_cert_path.exists() or not ca_key_path.exists():
            raise FileNotFoundError(
                f"CA cert/key not found at {ca_cert_path} / {ca_key_path}"
            )

        self._ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        self._ca_key = serialization.load_pem_private_key(
            ca_key_path.read_bytes(), password=None,
        )

    def sign_csr(self, csr_pem: str) -> dict:
        """Sign a CSR and return the new certificate.

        Args:
            csr_pem: PEM-encoded CSR string.

        Returns:
            Dict with 'certificate_pem', 'serial_number', 'expires_at', 'fingerprint'.
        """
        self._load_ca()

        csr = x509.load_pem_x509_csr(csr_pem.encode())

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self._cert_validity_days)

        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(expires_at)
        )

        # Carry over SANs from CSR
        try:
            san_ext = csr.extensions.get_extension_for_class(
                x509.SubjectAlternativeName,
            )
            builder = builder.add_extension(san_ext.value, critical=False)
        except x509.ExtensionNotFound:
            pass

        cert = builder.sign(self._ca_key, hashes.SHA256())

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()

        logger.info(
            "certificate_signed",
            subject=str(cert.subject),
            serial=cert.serial_number,
            expires=expires_at.isoformat(),
        )

        return {
            "certificate_pem": cert_pem.decode(),
            "serial_number": str(cert.serial_number),
            "expires_at": expires_at.isoformat(),
            "fingerprint": fingerprint,
        }
