"""Unit tests for the Recursant CLI — uses typer.testing.CliRunner, no live registry.

Tests init, validate, apply (dry-run), deploy (error cases), and status (error cases).
"""

import os

import pytest
from typer.testing import CliRunner

from recursant.cli.main import app

runner = CliRunner()

VALID_AGENT_YAML = """\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: cli-test-agent
  version: "1.0.0"
spec:
  classification: internal
  data_sensitivity: none
  risk_tier: low
  description: CLI test agent
  endpoint:
    url: http://localhost:8001
    type: custom
    auth_method: api_key
  capabilities:
    - name: default
      description: Default capability
"""

VALID_REGISTRY_YAML = """\
apiVersion: recursant/v1
kind: RegistryConfig
metadata:
  tenant: default
guardrails:
  - name: test-guardrail
    type: pre_processing
    mechanism: regex
    enforcement: block
    config:
      patterns:
        - pattern: "\\\\d{3}-\\\\d{2}-\\\\d{4}"
          label: ssn
mesh_policies:
  - source: agent-a
    destination: agent-b
    action: allow
"""

INVALID_YAML = """\
kind: Agent
metadata:
  name: missing-spec
"""


class TestInit:
    """Test `recursant init` command."""

    def test_init_creates_default_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Created" in result.output
        content = (tmp_path / "recursant.yaml").read_text()
        assert "kind: Agent" in content

    def test_init_custom_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = str(tmp_path / "custom.yaml")
        result = runner.invoke(app, ["init", "--output", out])
        assert result.exit_code == 0
        assert os.path.exists(out)
        content = open(out).read()
        assert "kind: Agent" in content

    def test_init_custom_type(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = str(tmp_path / "langgraph.yaml")
        result = runner.invoke(app, ["init", "--type", "langgraph", "--output", out])
        assert result.exit_code == 0
        content = open(out).read()
        assert "type: langgraph" in content

    def test_init_overwrite_aborted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / "recursant.yaml"
        existing.write_text("original content")
        result = runner.invoke(app, ["init"], input="n\n")
        assert result.exit_code != 0  # typer.Abort sets non-zero exit
        assert existing.read_text() == "original content"

    def test_init_overwrite_confirmed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / "recursant.yaml"
        existing.write_text("original content")
        result = runner.invoke(app, ["init"], input="y\n")
        assert result.exit_code == 0
        assert existing.read_text() != "original content"
        assert "kind: Agent" in existing.read_text()


class TestValidate:
    """Test `recursant validate` command."""

    def test_validate_valid_agent_config(self, tmp_path):
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(VALID_AGENT_YAML)
        result = runner.invoke(app, ["validate", "-f", str(cfg)])
        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_validate_valid_registry_config(self, tmp_path):
        cfg = tmp_path / "registry.yaml"
        cfg.write_text(VALID_REGISTRY_YAML)
        result = runner.invoke(app, ["validate", "-f", str(cfg)])
        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_validate_invalid_config(self, tmp_path):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text(INVALID_YAML)
        result = runner.invoke(app, ["validate", "-f", str(cfg)])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_validate_missing_file(self):
        result = runner.invoke(app, ["validate", "-f", "/nonexistent/file.yaml"])
        assert result.exit_code == 1
        assert "ERROR" in result.output


class TestApplyDryRun:
    """Test `recursant apply --dry-run` (no live registry needed)."""

    def test_apply_agent_dry_run(self, tmp_path):
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(VALID_AGENT_YAML)
        result = runner.invoke(app, ["apply", "-f", str(cfg), "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "cli-test-agent" in result.output

    def test_apply_agent_dry_run_with_submit(self, tmp_path):
        cfg = tmp_path / "agent.yaml"
        cfg.write_text(VALID_AGENT_YAML)
        result = runner.invoke(app, ["apply", "-f", str(cfg), "--dry-run", "--submit"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "governance" in result.output.lower()

    def test_apply_registry_config_dry_run(self, tmp_path):
        cfg = tmp_path / "registry.yaml"
        cfg.write_text(VALID_REGISTRY_YAML)
        result = runner.invoke(app, ["apply", "-f", str(cfg), "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "guardrails:" in result.output

    def test_apply_invalid_file(self, tmp_path):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text(INVALID_YAML)
        result = runner.invoke(app, ["apply", "-f", str(cfg)])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_apply_missing_file(self):
        result = runner.invoke(app, ["apply", "-f", "/nonexistent/file.yaml"])
        assert result.exit_code == 1
        assert "ERROR" in result.output


class TestDeployErrors:
    """Test `recursant deploy` error paths (no live registry)."""

    def test_deploy_missing_config_file(self):
        result = runner.invoke(app, ["deploy", "-f", "/nonexistent/recursant.yaml"])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_deploy_invalid_config(self, tmp_path):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text(INVALID_YAML)
        result = runner.invoke(app, ["deploy", "-f", str(cfg)])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_deploy_wrong_kind(self, tmp_path):
        cfg = tmp_path / "registry.yaml"
        cfg.write_text(VALID_REGISTRY_YAML)
        result = runner.invoke(app, ["deploy", "-f", str(cfg)])
        assert result.exit_code == 1
        assert "ERROR" in result.output


class TestStatusErrors:
    """Test `recursant status` error paths (no live registry)."""

    def test_status_unreachable_registry(self, monkeypatch):
        monkeypatch.setenv("RECURSANT_REGISTRY_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("RECURSANT_USERNAME", "admin")
        monkeypatch.setenv("RECURSANT_PASSWORD", "fake")
        result = runner.invoke(app, ["status", "nonexistent-agent"])
        assert result.exit_code == 1

    def test_status_missing_agent_argument(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code != 0
