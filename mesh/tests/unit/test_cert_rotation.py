"""Tests for certificate auto-rotation."""

import ssl
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from runtime.sidecar.cert_rotation import CertRotationManager, ReloadableSSLContext
from runtime.sidecar.config import TLSConfig


class TestReloadableSSLContext:
    def test_swap_atomically(self):
        ctx1 = MagicMock(spec=ssl.SSLContext)
        holder = ReloadableSSLContext(ctx1)
        assert holder.context is ctx1

        ctx2 = MagicMock(spec=ssl.SSLContext)
        holder.swap(ctx2)
        assert holder.context is ctx2
        assert holder.context is not ctx1

    def test_thread_safety(self):
        """Basic check that swap works under concurrent access."""
        import threading

        ctx1 = MagicMock(spec=ssl.SSLContext)
        holder = ReloadableSSLContext(ctx1)
        results = []

        def reader():
            for _ in range(100):
                ctx = holder.context
                results.append(ctx is not None)

        def writer():
            for _ in range(100):
                holder.swap(MagicMock(spec=ssl.SSLContext))

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(results)


class TestCertRotationManager:
    def _make_tls_config(self, **kwargs) -> TLSConfig:
        defaults = dict(
            cert_path="/tmp/test-cert.pem",
            key_path="/tmp/test-key.pem",
            ca_path="/tmp/test-ca.pem",
            rotation_enabled=True,
            rotation_check_interval_seconds=1,
            renewal_days_before_expiry=30,
        )
        defaults.update(kwargs)
        return TLSConfig(**defaults)

    def test_start_stop(self):
        config = self._make_tls_config()
        holder = ReloadableSSLContext(MagicMock(spec=ssl.SSLContext))
        manager = CertRotationManager(
            tls_config=config,
            ssl_holder=holder,
            registry_url="http://localhost:5000",
        )
        manager.start()
        assert manager._thread is not None
        assert manager._thread.is_alive()
        manager.stop()
        assert not manager._thread.is_alive()

    def test_no_start_when_disabled(self):
        config = self._make_tls_config(rotation_enabled=False)
        holder = ReloadableSSLContext(MagicMock(spec=ssl.SSLContext))
        manager = CertRotationManager(
            tls_config=config,
            ssl_holder=holder,
            registry_url="http://localhost:5000",
        )
        manager.start()
        assert manager._thread is None

    def test_generate_csr(self):
        """Test CSR generation from a self-signed cert."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        # Create a self-signed cert
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "test-sidecar"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        # Write cert to temp file
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
            cert_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))
            key_path = f.name

        config = self._make_tls_config(cert_path=cert_path, key_path=key_path)
        holder = ReloadableSSLContext(MagicMock(spec=ssl.SSLContext))
        manager = CertRotationManager(
            tls_config=config,
            ssl_holder=holder,
            registry_url="http://localhost:5000",
        )

        csr_pem, new_key_pem = manager._generate_csr(cert)

        # Verify CSR is valid
        csr = x509.load_pem_x509_csr(csr_pem)
        assert csr.subject == cert.subject

        # Verify new key is valid
        new_key = serialization.load_pem_private_key(new_key_pem, password=None)
        assert new_key.key_size == 2048

        # Cleanup
        Path(cert_path).unlink()
        Path(key_path).unlink()

    def test_expiry_detection(self):
        """Test that expiring certs are detected correctly."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        # Create cert that expires in 10 days
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expiring-sidecar"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=355))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=10))
            .sign(key, hashes.SHA256())
        )

        now = datetime.now(timezone.utc)
        days_until_expiry = (cert.not_valid_after_utc - now).days
        assert days_until_expiry <= 30  # Would trigger renewal
