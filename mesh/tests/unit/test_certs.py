"""Tests for mTLS dev certificate generation."""

import os
import ssl
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "docker" / "certs" / "generate-certs.sh"


@pytest.fixture(scope="module")
def cert_dir():
    """Generate certs in a temp directory once for all tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["bash", str(SCRIPT), tmpdir],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        yield Path(tmpdir)


class TestCertGeneration:
    def test_ca_cert_exists(self, cert_dir):
        assert (cert_dir / "ca.pem").exists()
        assert (cert_dir / "ca-key.pem").exists()

    def test_sidecar_a_cert_exists(self, cert_dir):
        assert (cert_dir / "sidecar-a.pem").exists()
        assert (cert_dir / "sidecar-a-key.pem").exists()

    def test_sidecar_b_cert_exists(self, cert_dir):
        assert (cert_dir / "sidecar-b.pem").exists()
        assert (cert_dir / "sidecar-b-key.pem").exists()

    def test_no_intermediate_files(self, cert_dir):
        """CSR and ext files should be cleaned up."""
        assert not list(cert_dir.glob("*.csr"))
        assert not list(cert_dir.glob("*.ext"))

    def test_sidecar_a_verifies_against_ca(self, cert_dir):
        result = subprocess.run(
            ["openssl", "verify", "-CAfile", str(cert_dir / "ca.pem"),
             str(cert_dir / "sidecar-a.pem")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_sidecar_b_verifies_against_ca(self, cert_dir):
        result = subprocess.run(
            ["openssl", "verify", "-CAfile", str(cert_dir / "ca.pem"),
             str(cert_dir / "sidecar-b.pem")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_sidecar_a_cn(self, cert_dir):
        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_dir / "sidecar-a.pem"),
             "-noout", "-subject"],
            capture_output=True, text=True,
        )
        assert "CN=sidecar-a" in result.stdout or "CN = sidecar-a" in result.stdout

    def test_sidecar_b_cn(self, cert_dir):
        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_dir / "sidecar-b.pem"),
             "-noout", "-subject"],
            capture_output=True, text=True,
        )
        assert "CN=sidecar-b" in result.stdout or "CN = sidecar-b" in result.stdout

    def test_sidecar_a_has_san(self, cert_dir):
        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_dir / "sidecar-a.pem"),
             "-noout", "-ext", "subjectAltName"],
            capture_output=True, text=True,
        )
        assert "localhost" in result.stdout
        assert "host-a" in result.stdout

    def test_sidecar_b_has_san(self, cert_dir):
        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_dir / "sidecar-b.pem"),
             "-noout", "-ext", "subjectAltName"],
            capture_output=True, text=True,
        )
        assert "localhost" in result.stdout
        assert "host-b" in result.stdout

    def test_certs_have_client_and_server_auth(self, cert_dir):
        """Both certs should support serverAuth and clientAuth for mTLS."""
        for name in ["sidecar-a.pem", "sidecar-b.pem"]:
            result = subprocess.run(
                ["openssl", "x509", "-in", str(cert_dir / name),
                 "-noout", "-ext", "extendedKeyUsage"],
                capture_output=True, text=True,
            )
            assert "TLS Web Server Authentication" in result.stdout
            assert "TLS Web Client Authentication" in result.stdout

    def test_ssl_context_loads_certs(self, cert_dir):
        """Verify Python's ssl module can load the certs."""
        ctx = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH,
            cafile=str(cert_dir / "ca.pem"),
        )
        ctx.load_cert_chain(
            certfile=str(cert_dir / "sidecar-a.pem"),
            keyfile=str(cert_dir / "sidecar-a-key.pem"),
        )
        # If we get here without error, the certs are valid for Python SSL

    def test_idempotent_regeneration(self, cert_dir):
        """Running the script again overwrites cleanly."""
        result = subprocess.run(
            ["bash", str(SCRIPT), str(cert_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert (cert_dir / "ca.pem").exists()
