"""Tests for Docker Compose and Dockerfile configuration (Step 10).

These tests validate the structure and correctness of Docker configuration
files without actually running Docker. They check:
- docker-compose.yaml structure and service definitions
- Dockerfile.sidecar and Dockerfile.agent content
- Service dependencies and health checks
- Certificate files exist
- Sidecar entry point is importable
"""

from pathlib import Path

import yaml
import pytest

MESH_DIR = Path(__file__).parent.parent.parent
DOCKER_DIR = MESH_DIR / "docker"
PROJECT_DIR = MESH_DIR.parent  # recursant/ root


# ===========================================================================
# docker-compose.yaml (lives in project root, not mesh/)
# ===========================================================================


class TestDockerCompose:
    @pytest.fixture
    def compose(self):
        path = PROJECT_DIR / "docker-compose.yaml"
        assert path.exists(), "docker-compose.yaml not found in project root"
        with open(path) as f:
            return yaml.safe_load(f)

    def test_compose_has_services(self, compose):
        assert "services" in compose

    def test_required_services_present(self, compose):
        services = set(compose["services"].keys())
        expected = {
            "registry-db",
            "registry-redis",
            "registry",
            "seed",
            "agent-a",
            "sidecar-a",
            "agent-b",
            "sidecar-b",
        }
        assert expected.issubset(services)

    def test_registry_db_is_postgres(self, compose):
        db = compose["services"]["registry-db"]
        assert "postgres" in db["image"]

    def test_registry_depends_on_db_and_redis(self, compose):
        deps = compose["services"]["registry"]["depends_on"]
        assert "registry-db" in deps
        assert "registry-redis" in deps

    def test_registry_has_healthcheck(self, compose):
        assert "healthcheck" in compose["services"]["registry"]

    def test_seed_depends_on_registry(self, compose):
        deps = compose["services"]["seed"]["depends_on"]
        assert "registry" in deps

    def test_agents_depend_on_seed(self, compose):
        for name in ["agent-a", "agent-b"]:
            deps = compose["services"][name]["depends_on"]
            assert "seed" in deps

    def test_sidecars_depend_on_pipeline(self, compose):
        deps_a = compose["services"]["sidecar-a"]["depends_on"]
        assert "pipeline" in deps_a

        deps_b = compose["services"]["sidecar-b"]["depends_on"]
        assert "pipeline" in deps_b

    def test_agent_a_port(self, compose):
        env = compose["services"]["agent-a"]["environment"]
        assert env.get("AGENT_PORT") == "5010"

    def test_agent_b_port(self, compose):
        env = compose["services"]["agent-b"]["environment"]
        assert env.get("AGENT_PORT") == "5011"

    def test_sidecar_a_ports(self, compose):
        env = compose["services"]["sidecar-a"]["environment"]
        assert env.get("SIDECAR_PORT") == "9901"
        assert env.get("SIDECAR_A2A_PORT") == "8443"

    def test_sidecar_b_ports(self, compose):
        env = compose["services"]["sidecar-b"]["environment"]
        assert env.get("SIDECAR_PORT") == "9902"
        assert env.get("SIDECAR_A2A_PORT") == "8444"

    def test_sidecars_mount_certs(self, compose):
        for name in ["sidecar-a", "sidecar-b"]:
            volumes = compose["services"][name].get("volumes", [])
            cert_mounts = [v for v in volumes if "/certs" in v]
            assert len(cert_mounts) >= 1, f"{name} must mount certs volume"

    def test_sidecars_point_to_registry(self, compose):
        for name in ["sidecar-a", "sidecar-b"]:
            env = compose["services"][name]["environment"]
            assert env.get("SIDECAR_REGISTRY_URL") == "http://registry:5000"

    def test_agent_a_uses_sidecar_url(self, compose):
        env = compose["services"]["agent-a"]["environment"]
        assert env.get("SIDECAR_URL") == "http://sidecar-a:9901"

    def test_has_volumes_section(self, compose):
        assert "volumes" in compose


# ===========================================================================
# Dockerfiles
# ===========================================================================


class TestDockerfiles:
    def test_sidecar_dockerfile_exists(self):
        path = DOCKER_DIR / "Dockerfile.sidecar"
        assert path.exists()

    def test_sidecar_dockerfile_uses_python311(self):
        content = (DOCKER_DIR / "Dockerfile.sidecar").read_text()
        assert "python:3.11" in content

    def test_sidecar_dockerfile_copies_runtime(self):
        content = (DOCKER_DIR / "Dockerfile.sidecar").read_text()
        assert "runtime/" in content

    def test_sidecar_dockerfile_installs_package(self):
        content = (DOCKER_DIR / "Dockerfile.sidecar").read_text()
        assert "pip install" in content

    def test_agent_dockerfile_exists(self):
        path = DOCKER_DIR / "Dockerfile.agent"
        assert path.exists()

    def test_agent_dockerfile_uses_python311(self):
        content = (DOCKER_DIR / "Dockerfile.agent").read_text()
        assert "python:3.11" in content

    def test_agent_dockerfile_installs_flask(self):
        content = (DOCKER_DIR / "Dockerfile.agent").read_text()
        assert "flask" in content


# ===========================================================================
# Dev certificates
# ===========================================================================


class TestDevCerts:
    def test_generate_script_exists(self):
        path = DOCKER_DIR / "certs" / "generate-certs.sh"
        assert path.exists()

    def test_ca_cert_exists(self):
        assert (DOCKER_DIR / "certs" / "ca.pem").exists()

    def test_sidecar_a_cert_exists(self):
        assert (DOCKER_DIR / "certs" / "sidecar-a.pem").exists()
        assert (DOCKER_DIR / "certs" / "sidecar-a-key.pem").exists()

    def test_sidecar_b_cert_exists(self):
        assert (DOCKER_DIR / "certs" / "sidecar-b.pem").exists()
        assert (DOCKER_DIR / "certs" / "sidecar-b-key.pem").exists()


# ===========================================================================
# Sidecar entry point
# ===========================================================================


class TestSidecarEntryPoint:
    def test_main_module_exists(self):
        path = MESH_DIR / "runtime" / "sidecar" / "__main__.py"
        assert path.exists()

    def test_main_importable(self):
        from runtime.sidecar.__main__ import main
        assert callable(main)


# ===========================================================================
# .dockerignore
# ===========================================================================


class TestDockerIgnore:
    def test_dockerignore_exists(self):
        path = MESH_DIR / ".dockerignore"
        assert path.exists()

    def test_dockerignore_excludes_venv(self):
        content = (MESH_DIR / ".dockerignore").read_text()
        assert ".venv" in content

    def test_dockerignore_excludes_tests(self):
        content = (MESH_DIR / ".dockerignore").read_text()
        assert "tests/" in content
