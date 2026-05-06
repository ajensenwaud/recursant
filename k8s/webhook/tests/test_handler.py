"""Unit tests for the Recursant sidecar injection webhook."""

import base64
import json
import sys
import os

import pytest

# Add parent directory to path so we can import handler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handler import (
    _build_sidecar_container,
    _build_volumes,
    _get_existing_container_names,
    _get_existing_volume_names,
    _is_already_injected,
    _inject_single_sidecar,
    _inject_multiple_sidecars,
    app,
)


def _make_pod_spec(containers=None, volumes=None):
    """Create a minimal pod spec for testing."""
    return {
        "containers": containers or [
            {"name": "main-app", "image": "test:latest"}
        ],
        "volumes": volumes or [],
    }


def _make_annotations(**kwargs):
    """Create annotations dict with common sidecar injection fields."""
    base = {
        "recursant.io/inject-sidecar": "true",
        "recursant.io/agent-name": "Test Agent",
        "recursant.io/agent-port": "5010",
        "recursant.io/sidecar-port": "9901",
        "recursant.io/a2a-port": "8443",
        "recursant.io/sidecar-config": "test-config",
        "recursant.io/cert-secret": "test-certs",
    }
    base.update(kwargs)
    return base


def _make_admission_review(annotations=None, containers=None, volumes=None):
    """Create a minimal AdmissionReview request."""
    return {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "request": {
            "uid": "test-uid-123",
            "object": {
                "metadata": {
                    "name": "test-pod",
                    "annotations": annotations or {},
                },
                "spec": _make_pod_spec(containers, volumes),
            },
        },
    }


class TestBuildSidecarContainer:
    def test_builds_correct_container(self):
        container = _build_sidecar_container(
            name="recursant-sidecar",
            agent_name="Test Agent",
            agent_port=5010,
            sidecar_port=9901,
            a2a_port=8443,
            config_map="test-config",
            cert_secret="test-certs",
            secret_name="recursant-secrets",
        )
        assert container["name"] == "recursant-sidecar"
        assert container["image"] == "recursant-sidecar:latest"
        assert len(container["ports"]) == 2
        assert container["ports"][0]["containerPort"] == 9901
        assert container["ports"][1]["containerPort"] == 8443

        env_map = {e["name"]: e for e in container["env"]}
        assert env_map["SIDECAR_PORT"]["value"] == "9901"
        assert env_map["SIDECAR_A2A_PORT"]["value"] == "8443"
        assert env_map["SIDECAR_AGENT_PORT"]["value"] == "5010"
        assert env_map["SIDECAR_AGENT_HOST"]["value"] == "localhost"
        assert env_map["SIDECAR_AGENT_NAME"]["value"] == "Test Agent"
        assert env_map["SIDECAR_REGISTRY_URL"]["value"].startswith("http://")

        assert len(container["volumeMounts"]) == 3

    def test_custom_ports(self):
        container = _build_sidecar_container(
            name="recursant-sidecar-custom",
            agent_name="Custom",
            agent_port=5020,
            sidecar_port=9910,
            a2a_port=8450,
            config_map="custom-config",
            cert_secret="custom-certs",
            secret_name="my-secrets",
        )
        assert container["ports"][0]["containerPort"] == 9910
        assert container["ports"][1]["containerPort"] == 8450
        env_map = {e["name"]: e for e in container["env"]}
        assert env_map["SIDECAR_AGENT_PORT"]["value"] == "5020"

    def test_advertise_host_not_set_by_default(self):
        container = _build_sidecar_container(
            name="recursant-sidecar",
            agent_name="Test",
            agent_port=5010,
            sidecar_port=9901,
            a2a_port=8443,
            config_map="cfg",
            cert_secret="certs",
            secret_name="secrets",
        )
        env_names = {e["name"] for e in container["env"]}
        assert "SIDECAR_ADVERTISE_HOST" not in env_names

    def test_advertise_host_set_when_provided(self):
        container = _build_sidecar_container(
            name="recursant-sidecar",
            agent_name="Test",
            agent_port=5010,
            sidecar_port=9901,
            a2a_port=8443,
            config_map="cfg",
            cert_secret="certs",
            secret_name="secrets",
            advertise_host="my-service.default.svc",
        )
        env_map = {e["name"]: e for e in container["env"]}
        assert env_map["SIDECAR_ADVERTISE_HOST"]["value"] == "my-service.default.svc"
        assert env_map["SIDECAR_ADVERTISE_PORT"]["value"] == "8443"


class TestBuildVolumes:
    def test_builds_config_and_cert_volumes(self):
        volumes = _build_volumes("recursant-sidecar", "my-config", "my-certs")
        assert len(volumes) == 2
        assert volumes[0]["name"] == "recursant-sidecar-config"
        assert volumes[0]["configMap"]["name"] == "my-config"
        assert volumes[1]["name"] == "recursant-sidecar-certs"
        assert volumes[1]["secret"]["secretName"] == "my-certs"


class TestHelpers:
    def test_get_existing_container_names(self):
        pod_spec = _make_pod_spec(
            containers=[
                {"name": "app", "image": "x"},
                {"name": "sidecar", "image": "y"},
            ]
        )
        assert _get_existing_container_names(pod_spec) == {"app", "sidecar"}

    def test_get_existing_volume_names(self):
        pod_spec = _make_pod_spec(volumes=[{"name": "vol1"}, {"name": "vol2"}])
        assert _get_existing_volume_names(pod_spec) == {"vol1", "vol2"}

    def test_is_already_injected_false(self):
        assert not _is_already_injected({})

    def test_is_already_injected_true(self):
        assert _is_already_injected(
            {"recursant.io/sidecar-injected": "true"}
        )


class TestInjectSingleSidecar:
    def test_injects_single_sidecar(self):
        annotations = _make_annotations()
        pod_spec = _make_pod_spec()
        patches = _inject_single_sidecar(pod_spec, annotations)

        assert len(patches) > 0
        # Should have: add container, add volumes init, add 2 volumes, mark injected
        ops = [p["op"] for p in patches]
        assert all(op == "add" for op in ops)

        # Find container patch
        container_patches = [
            p for p in patches if p["path"].startswith("/spec/containers/")
        ]
        assert len(container_patches) == 1
        assert container_patches[0]["value"]["name"] == "recursant-sidecar"

        # Find injected annotation patch
        anno_patches = [
            p for p in patches if "sidecar-injected" in p["path"]
        ]
        assert len(anno_patches) == 1
        assert anno_patches[0]["value"] == "true"

    def test_skips_when_already_injected(self):
        annotations = _make_annotations(
            **{"recursant.io/sidecar-injected": "true"}
        )
        # _inject_single_sidecar doesn't check already-injected, that's done in mutate()
        # But it should still work - just test the mutate endpoint
        pod_spec = _make_pod_spec()
        # Already-injected check is at the mutate level, not here

    def test_skips_missing_required_annotations(self):
        annotations = {"recursant.io/inject-sidecar": "true"}
        pod_spec = _make_pod_spec()
        patches = _inject_single_sidecar(pod_spec, annotations)
        assert patches == []

    def test_skips_missing_config_annotations(self):
        annotations = {
            "recursant.io/inject-sidecar": "true",
            "recursant.io/agent-name": "Test",
            "recursant.io/agent-port": "5010",
        }
        pod_spec = _make_pod_spec()
        patches = _inject_single_sidecar(pod_spec, annotations)
        assert patches == []

    def test_single_sidecar_with_advertise_host(self):
        annotations = _make_annotations(
            **{"recursant.io/advertise-host": "my-svc"}
        )
        pod_spec = _make_pod_spec()
        patches = _inject_single_sidecar(pod_spec, annotations)
        container_patches = [
            p for p in patches if p["path"].startswith("/spec/containers/")
        ]
        assert len(container_patches) == 1
        env_map = {e["name"]: e for e in container_patches[0]["value"]["env"]}
        assert env_map["SIDECAR_ADVERTISE_HOST"]["value"] == "my-svc"
        assert env_map["SIDECAR_ADVERTISE_PORT"]["value"] == "8443"

    def test_idempotent_container_exists(self):
        annotations = _make_annotations()
        pod_spec = _make_pod_spec(
            containers=[
                {"name": "main-app", "image": "test:latest"},
                {"name": "recursant-sidecar", "image": "recursant-sidecar:latest"},
            ]
        )
        patches = _inject_single_sidecar(pod_spec, annotations)
        assert patches == []


class TestInjectMultipleSidecars:
    def _two_sidecars(self):
        return [
            {
                "name": "customer",
                "agentName": "Customer Agent",
                "agentPort": 5020,
                "sidecarPort": 9910,
                "a2aPort": 8450,
                "config": "sidecar-customer-config",
                "certs": "mortgage-certs",
            },
            {
                "name": "auth",
                "agentName": "Auth Agent",
                "agentPort": 5021,
                "sidecarPort": 9911,
                "a2aPort": 8451,
                "config": "sidecar-auth-config",
                "certs": "mortgage-certs",
            },
        ]

    def test_injects_two_sidecars(self):
        sidecars = self._two_sidecars()
        annotations = {
            "recursant.io/inject-sidecars": json.dumps(sidecars)
        }
        pod_spec = _make_pod_spec()
        patches = _inject_multiple_sidecars(pod_spec, annotations)

        assert len(patches) > 0

        # Find container patches
        container_patches = [
            p for p in patches if p["path"].startswith("/spec/containers/")
        ]
        assert len(container_patches) == 2
        names = [p["value"]["name"] for p in container_patches]
        assert "recursant-sidecar-customer" in names
        assert "recursant-sidecar-auth" in names

        # Check ports are distinct
        customer_patch = next(
            p for p in container_patches
            if p["value"]["name"] == "recursant-sidecar-customer"
        )
        auth_patch = next(
            p for p in container_patches
            if p["value"]["name"] == "recursant-sidecar-auth"
        )
        assert customer_patch["value"]["ports"][0]["containerPort"] == 9910
        assert customer_patch["value"]["ports"][1]["containerPort"] == 8450
        assert auth_patch["value"]["ports"][0]["containerPort"] == 9911
        assert auth_patch["value"]["ports"][1]["containerPort"] == 8451

    def test_multi_sidecar_with_advertise_host(self):
        sidecars = [
            {
                "name": "customer",
                "agentName": "Customer Agent",
                "agentPort": 5020,
                "sidecarPort": 9910,
                "a2aPort": 8450,
                "config": "cfg-customer",
                "certs": "certs",
                "advertiseHost": "agents-customer-svc",
            },
        ]
        annotations = {
            "recursant.io/inject-sidecars": json.dumps(sidecars)
        }
        pod_spec = _make_pod_spec()
        patches = _inject_multiple_sidecars(pod_spec, annotations)
        container_patches = [
            p for p in patches if p["path"].startswith("/spec/containers/")
        ]
        assert len(container_patches) == 1
        env_map = {e["name"]: e for e in container_patches[0]["value"]["env"]}
        assert env_map["SIDECAR_ADVERTISE_HOST"]["value"] == "agents-customer-svc"
        assert env_map["SIDECAR_ADVERTISE_PORT"]["value"] == "8450"

    def test_skips_invalid_json(self):
        annotations = {"recursant.io/inject-sidecars": "not-json"}
        pod_spec = _make_pod_spec()
        patches = _inject_multiple_sidecars(pod_spec, annotations)
        assert patches == []

    def test_skips_empty_list(self):
        annotations = {"recursant.io/inject-sidecars": "[]"}
        pod_spec = _make_pod_spec()
        patches = _inject_multiple_sidecars(pod_spec, annotations)
        assert patches == []

    def test_skips_sidecar_with_missing_config(self):
        sidecars = [
            {
                "name": "incomplete",
                "agentName": "Test",
                "agentPort": 5010,
            }
        ]
        annotations = {
            "recursant.io/inject-sidecars": json.dumps(sidecars)
        }
        pod_spec = _make_pod_spec()
        patches = _inject_multiple_sidecars(pod_spec, annotations)
        assert patches == []


class TestMutateEndpoint:
    @pytest.fixture
    def client(self):
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json["status"] == "ok"

    def test_mutate_no_annotations(self, client):
        review = _make_admission_review()
        resp = client.post("/mutate", json=review)
        assert resp.status_code == 200
        data = resp.json
        assert data["response"]["uid"] == "test-uid-123"
        assert data["response"]["allowed"] is True
        assert "patch" not in data["response"]

    def test_mutate_single_sidecar(self, client):
        annotations = _make_annotations()
        review = _make_admission_review(annotations=annotations)
        resp = client.post("/mutate", json=review)
        assert resp.status_code == 200
        data = resp.json
        assert data["response"]["allowed"] is True
        assert data["response"]["patchType"] == "JSONPatch"
        patches = json.loads(base64.b64decode(data["response"]["patch"]))
        container_patches = [
            p for p in patches if p["path"].startswith("/spec/containers/")
        ]
        assert len(container_patches) == 1
        assert container_patches[0]["value"]["name"] == "recursant-sidecar"

    def test_mutate_already_injected(self, client):
        annotations = _make_annotations(
            **{"recursant.io/sidecar-injected": "true"}
        )
        review = _make_admission_review(annotations=annotations)
        resp = client.post("/mutate", json=review)
        assert resp.status_code == 200
        data = resp.json
        assert data["response"]["allowed"] is True
        assert "patch" not in data["response"]

    def test_mutate_empty_body(self, client):
        resp = client.post("/mutate", data="", content_type="application/json")
        assert resp.status_code == 400
