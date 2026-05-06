"""Integration tests for Recursant CLI — real HTTP calls to running registry.

Run inside the Kind cluster via kubectl exec.
"""

import uuid

import pytest
from typer.testing import CliRunner

from recursant.cli.main import app
from tests.conftest import get_mesh_api_key, get_password, get_registry_url, get_tenant_id, get_username

runner = CliRunner()

REGISTRY_URL = get_registry_url()
USERNAME = get_username()
PASSWORD = get_password()
TENANT = get_tenant_id()
MESH_API_KEY = get_mesh_api_key()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _agent_yaml(name: str) -> str:
    return f"""\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: {name}
  version: "1.0.0"
spec:
  classification: internal
  data_sensitivity: none
  risk_tier: low
  description: CLI integration test agent
  endpoint:
    url: http://test-agent:8001
    type: custom
    auth_method: api_key
  capabilities:
    - name: default
      description: Default capability
"""


def _guardrail_only_yaml(guardrail_name: str) -> str:
    return f"""\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
guardrails:
  - name: {guardrail_name}
    type: pre_processing
    mechanism: regex
    enforcement: block
    config:
      patterns:
        - pattern: "\\\\d{{3}}-\\\\d{{2}}-\\\\d{{4}}"
          label: ssn
"""


def _policy_only_yaml(source: str, dest: str) -> str:
    return f"""\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
mesh_policies:
  - source: {source}
    destination: {dest}
    action: allow
"""


def _set_env(monkeypatch, include_api_key=False):
    """Set registry credentials in env for CLI commands."""
    monkeypatch.setenv("RECURSANT_REGISTRY_URL", REGISTRY_URL)
    monkeypatch.setenv("RECURSANT_USERNAME", USERNAME)
    monkeypatch.setenv("RECURSANT_PASSWORD", PASSWORD)
    monkeypatch.setenv("RECURSANT_TENANT_ID", TENANT)
    if include_api_key:
        monkeypatch.setenv("RECURSANT_API_KEY", MESH_API_KEY)


@pytest.mark.integration
class TestApplyIntegration:
    """Test `recursant apply` against the real registry."""

    def test_apply_creates_agent(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-apply")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        result = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        assert "Created" in result.output
        assert name in result.output

    def test_apply_updates_existing(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-update")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))

        r1 = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert r1.exit_code == 0, r1.output
        assert "Created" in r1.output

        r2 = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert r2.exit_code == 0, r2.output
        assert "Updated" in r2.output

    def test_apply_with_submit(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-submit")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        result = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL, "--submit"])
        assert result.exit_code == 0, result.output
        assert "Created" in result.output or "Updated" in result.output
        assert "Submitted" in result.output

    def test_apply_registry_config_guardrails(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        gr_name = _unique("cli-gr")
        cfg = tmp_path / "registry.yaml"
        cfg.write_text(_guardrail_only_yaml(gr_name))
        result = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        assert gr_name in result.output

    def test_apply_registry_config_policies(self, tmp_path, monkeypatch):
        _set_env(monkeypatch, include_api_key=True)
        src = _unique("src")
        dst = _unique("dst")
        cfg = tmp_path / "registry.yaml"
        cfg.write_text(_policy_only_yaml(src, dst))
        result = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        assert "Applied" in result.output


@pytest.mark.integration
class TestDeployIntegration:
    """Test `recursant deploy` against the real registry."""

    def test_deploy_creates_and_submits(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-deploy")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        result = runner.invoke(app, ["deploy", "-f", str(cfg), "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        assert "Created" in result.output or "Updated" in result.output
        assert "Submitted" in result.output

    def test_deploy_idempotent(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-deploy-idem")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))

        r1 = runner.invoke(app, ["deploy", "-f", str(cfg), "-r", REGISTRY_URL])
        assert r1.exit_code == 0, r1.output

        r2 = runner.invoke(app, ["deploy", "-f", str(cfg), "-r", REGISTRY_URL])
        assert r2.exit_code == 0, r2.output
        assert "Updated" in r2.output

    def test_deploy_explicit_registry_flag(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-deploy-flag")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        result = runner.invoke(app, ["deploy", "-f", str(cfg), "--registry", REGISTRY_URL])
        assert result.exit_code == 0, result.output


@pytest.mark.integration
class TestStatusIntegration:
    """Test `recursant status` against the real registry."""

    def test_status_shows_agent_info(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-status")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        # First create the agent
        r_create = runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])
        assert r_create.exit_code == 0, r_create.output

        # Then check its status
        result = runner.invoke(app, ["status", name, "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        assert name in result.output

    def test_status_not_found(self, monkeypatch):
        _set_env(monkeypatch)
        result = runner.invoke(app, ["status", "nonexistent-agent-xyz", "-r", REGISTRY_URL])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_status_shows_key_fields(self, tmp_path, monkeypatch):
        _set_env(monkeypatch)
        name = _unique("cli-fields")
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(_agent_yaml(name))
        runner.invoke(app, ["apply", "-f", str(cfg), "-r", REGISTRY_URL])

        result = runner.invoke(app, ["status", name, "-r", REGISTRY_URL])
        assert result.exit_code == 0, result.output
        # Rich table should contain key fields
        output = result.output.lower()
        assert "version" in output or "1.0.0" in output
        assert "status" in output or "draft" in output
