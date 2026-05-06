"""Test configuration — reads credentials from environment."""

import os
import uuid

import pytest


def get_registry_url():
    return os.environ.get("RECURSANT_REGISTRY_URL", "http://localhost:5000")


def get_username():
    return os.environ.get("RECURSANT_USERNAME", os.environ.get("ADMIN_USERNAME", "admin"))


def get_password():
    return os.environ.get("RECURSANT_PASSWORD", os.environ.get("ADMIN_PASSWORD", ""))


def get_tenant_id():
    return os.environ.get("RECURSANT_TENANT_ID", "default")


def get_mesh_api_key():
    return os.environ.get("MESH_API_KEY", "mesh-dev-key")


def unique_name(prefix: str) -> str:
    """Generate a unique name with a UUID suffix to avoid test collisions."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def client():
    """Authenticated RecursantClient (JWT) for integration tests."""
    from recursant.client import RecursantClient

    c = RecursantClient(
        get_registry_url(),
        username=get_username(),
        password=get_password(),
        tenant_id=get_tenant_id(),
    )
    yield c
    c.close()


@pytest.fixture
def mesh_client():
    """Authenticated RecursantClient (mesh API key) for mesh/sidecar endpoint tests."""
    from recursant.client import RecursantClient

    c = RecursantClient(
        get_registry_url(),
        api_key=get_mesh_api_key(),
        tenant_id=get_tenant_id(),
    )
    yield c
    c.close()
