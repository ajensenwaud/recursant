"""Tests for the Ingress Gateway."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runtime.gateway.config import GatewayConfig
from runtime.gateway.app import create_gateway_app
from runtime.gateway.router import GatewayRouter


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestGatewayConfig:
    def test_defaults(self):
        config = GatewayConfig()
        assert config.port == 8080
        assert config.registry_url == "http://localhost:5000"
        assert config.rate_limit_rpm == 600
        assert config.auth_api_key is None
        assert config.jwt_secret is None

    def test_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "gw.yaml"
        yaml_file.write_text(
            "gateway:\n"
            "  port: 9090\n"
            "  registry_url: http://reg:5000\n"
            "  auth_api_key: test-key\n"
            "  rate_limit_rpm: 120\n"
        )
        config = GatewayConfig.from_yaml(str(yaml_file))
        assert config.port == 9090
        assert config.registry_url == "http://reg:5000"
        assert config.auth_api_key == "test-key"
        assert config.rate_limit_rpm == 120

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("GATEWAY_PORT", "7070")
        monkeypatch.setenv("GATEWAY_REGISTRY_URL", "http://r:5000")
        config = GatewayConfig.from_env()
        assert config.port == 7070
        assert config.registry_url == "http://r:5000"


# ---------------------------------------------------------------------------
# App / route tests
# ---------------------------------------------------------------------------

class TestGatewayApp:
    @pytest.fixture
    def config(self):
        return GatewayConfig(auth_api_key="test-key")

    @pytest.fixture
    def app(self, config):
        return create_gateway_app(config)

    @pytest.fixture
    def client(self, app):
        app.config["TESTING"] = True
        return app.test_client()

    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_a2a_requires_auth(self, client):
        resp = client.post(
            "/a2a/research",
            json={"message": "hello"},
        )
        assert resp.status_code == 401

    def test_a2a_rejects_invalid_json(self, client):
        resp = client.post(
            "/a2a/research",
            data="not json",
            content_type="application/json",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 400

    def test_a2a_rejects_missing_message(self, client):
        resp = client.post(
            "/a2a/research",
            json={"other": "data"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 400

    def test_a2a_routes_to_skill(self, client, app):
        """Test that a valid request routes through the router."""
        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(
            return_value={"result": {"status": "completed", "text": "answer"}}
        )
        app.config["ROUTER"] = mock_router

        resp = client.post(
            "/a2a/research",
            json={"message": "What is AI?"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "result" in data
        mock_router.route_to_skill.assert_called_once()

    def test_a2a_returns_502_on_error(self, client, app):
        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(
            return_value={"error": "No agent found for skill 'xyz'"}
        )
        app.config["ROUTER"] = mock_router

        resp = client.post(
            "/a2a/xyz",
            json={"message": "test"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 502

    def test_agents_list_requires_auth(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 401

    def test_agents_list_returns_skills(self, client, app):
        mock_router = MagicMock()
        mock_router.list_skills.return_value = [
            {"skill": "fact-checking"},
            {"skill": "research"},
        ]
        app.config["ROUTER"] = mock_router

        resp = client.get("/agents", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["skills"]) == 2

    def test_rate_limiting(self, client, app):
        """Test that rate limiting kicks in after burst."""
        config = GatewayConfig(auth_api_key="test-key", rate_limit_rpm=6)
        rate_app = create_gateway_app(config)
        rate_app.config["TESTING"] = True

        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(return_value={"result": "ok"})
        rate_app.config["ROUTER"] = mock_router

        rate_client = rate_app.test_client()

        # Burst capacity is rate_limit_rpm / 60 * 2 = 6/60 * 2 = 0.2
        # With rate 0.1 tokens/sec and capacity 0.2, first request may succeed
        # but rapid subsequent requests should eventually fail
        statuses = []
        for _ in range(10):
            r = rate_client.post(
                "/a2a/test",
                json={"message": "hi"},
                headers={"X-API-Key": "test-key"},
            )
            statuses.append(r.status_code)

        # At least one should be rate limited (429)
        assert 429 in statuses


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestGatewayAuth:
    def test_api_key_auth(self):
        config = GatewayConfig(auth_api_key="secret-key")
        app = create_gateway_app(config)
        app.config["TESTING"] = True

        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(return_value={"result": "ok"})
        app.config["ROUTER"] = mock_router

        client = app.test_client()

        # Wrong key
        resp = client.post(
            "/a2a/test",
            json={"message": "hi"},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 401

        # Correct key
        resp = client.post(
            "/a2a/test",
            json={"message": "hi"},
            headers={"X-API-Key": "secret-key"},
        )
        assert resp.status_code == 200

    def test_no_auth_configured_allows_all(self):
        """Dev mode: no auth configured allows anonymous access."""
        config = GatewayConfig()
        app = create_gateway_app(config)
        app.config["TESTING"] = True

        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(return_value={"result": "ok"})
        app.config["ROUTER"] = mock_router

        client = app.test_client()
        resp = client.post(
            "/a2a/test",
            json={"message": "hi"},
        )
        assert resp.status_code == 200

    def test_jwt_auth(self):
        import jwt as pyjwt

        config = GatewayConfig(jwt_secret="my-jwt-secret-that-is-at-least-32bytes")
        app = create_gateway_app(config)
        app.config["TESTING"] = True

        mock_router = MagicMock()
        mock_router.route_to_skill = AsyncMock(return_value={"result": "ok"})
        app.config["ROUTER"] = mock_router

        client = app.test_client()

        token = pyjwt.encode({"sub": "test-client"}, "my-jwt-secret-that-is-at-least-32bytes", algorithm="HS256")
        resp = client.post(
            "/a2a/test",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_jwt_auth_invalid_token(self):
        config = GatewayConfig(jwt_secret="my-jwt-secret-that-is-at-least-32bytes")
        app = create_gateway_app(config)
        app.config["TESTING"] = True

        client = app.test_client()
        resp = client.post(
            "/a2a/test",
            json={"message": "hi"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------

class TestGatewayRouter:
    @pytest.fixture
    def mock_registry(self):
        return MagicMock()

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def mock_lb(self):
        lb = MagicMock()
        lb.select.side_effect = lambda dests, ctx: dests
        return lb

    @pytest.fixture
    def router(self, mock_registry, mock_client, mock_lb):
        return GatewayRouter(
            registry_client=mock_registry,
            outbound_client=mock_client,
            load_balancer=mock_lb,
        )

    @pytest.mark.asyncio
    async def test_route_to_skill_success(self, router, mock_registry, mock_client):
        mock_registry.discover.return_value = [
            {"name": "agent-a", "sidecar_url": "https://sidecar-a:8443", "skills": ["research"]},
        ]
        mock_client.send_a2a_request = AsyncMock(
            return_value={"result": {"status": "completed"}}
        )

        result = await router.route_to_skill("research", "test query")
        assert "result" in result
        mock_client.send_a2a_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_no_agents(self, router, mock_registry):
        mock_registry.discover.return_value = []
        result = await router.route_to_skill("unknown-skill", "test")
        assert "error" in result
        assert "No agent found" in result["error"]

    @pytest.mark.asyncio
    async def test_route_failover(self, router, mock_registry, mock_client):
        """When first destination fails, try next."""
        mock_registry.discover.return_value = [
            {"name": "agent-a", "sidecar_url": "https://sidecar-a:8443", "skills": ["research"]},
            {"name": "agent-b", "sidecar_url": "https://sidecar-b:8443", "skills": ["research"]},
        ]
        mock_client.send_a2a_request = AsyncMock(
            side_effect=[Exception("connection refused"), {"result": "ok"}]
        )

        result = await router.route_to_skill("research", "test")
        assert "result" in result
        assert mock_client.send_a2a_request.call_count == 2

    @pytest.mark.asyncio
    async def test_route_all_destinations_exhausted(self, router, mock_registry, mock_client):
        mock_registry.discover.return_value = [
            {"name": "agent-a", "sidecar_url": "https://sidecar-a:8443", "skills": ["research"]},
        ]
        mock_client.send_a2a_request = AsyncMock(
            side_effect=Exception("connection refused")
        )

        result = await router.route_to_skill("research", "test")
        assert "error" in result
        assert "All destinations exhausted" in result["error"]

    def test_list_skills(self, router, mock_registry):
        mock_registry.discover.return_value = [
            {"name": "a", "skills": ["research", "analysis"]},
            {"name": "b", "skills": ["fact-checking", "research"]},
        ]
        skills = router.list_skills()
        skill_names = [s["skill"] for s in skills]
        assert sorted(skill_names) == ["analysis", "fact-checking", "research"]

    def test_list_skills_registry_error(self, router, mock_registry):
        from runtime.sidecar.registry_client import RegistryClientError
        mock_registry.discover.side_effect = RegistryClientError("connection failed")
        skills = router.list_skills()
        assert skills == []
