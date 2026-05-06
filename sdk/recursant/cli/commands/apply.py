"""recursant apply — idempotent create/update from config."""

from __future__ import annotations

import os

import typer
from rich.console import Console

from recursant.client import RecursantClient
from recursant.config import AgentConfig, RegistryConfig, load_config
from recursant.exceptions import NotFoundError, RecursantError

console = Console()


def _get_client(registry: str | None) -> RecursantClient:
    url = registry or os.environ.get("RECURSANT_REGISTRY_URL", "http://localhost:5000")
    return RecursantClient(
        url,
        username=os.environ.get("RECURSANT_USERNAME"),
        password=os.environ.get("RECURSANT_PASSWORD"),
        api_key=os.environ.get("RECURSANT_API_KEY"),
        tenant_id=os.environ.get("RECURSANT_TENANT_ID", "default"),
    )


def apply(
    file: str = typer.Option(..., "--file", "-f", help="Path to YAML config file"),
    registry: str = typer.Option(None, "--registry", "-r", help="Registry URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without making changes"),
    submit: bool = typer.Option(False, "--submit", help="Submit agent after apply (Agent configs only)"),
) -> None:
    """Apply a config file to the registry (idempotent create/update)."""
    try:
        cfg = load_config(file)
    except RecursantError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(code=1)

    if isinstance(cfg, AgentConfig):
        _apply_agent(cfg, registry, dry_run, submit)
    elif isinstance(cfg, RegistryConfig):
        _apply_registry_config(cfg, registry, dry_run)
    else:
        console.print(f"[red]ERROR:[/red] Unknown config kind")
        raise typer.Exit(code=1)


def _apply_agent(
    cfg: AgentConfig, registry: str | None, dry_run: bool, submit: bool
) -> None:
    payload = cfg.to_api_payload()
    name = cfg.metadata.name

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would apply Agent '{name}'")
        console.print(f"  version: {cfg.metadata.version}")
        console.print(f"  endpoint: {cfg.spec.endpoint.url}")
        if submit:
            console.print(f"  [yellow]Would submit for governance review[/yellow]")
        return

    with _get_client(registry) as client:
        # Check if agent exists by name
        existing_id = None
        try:
            paginated = client.agents.list(name=name)
            for a in paginated.agents:
                if a.name == name:
                    existing_id = str(a.id)
                    break
        except Exception:
            pass

        if existing_id:
            update_payload = {k: v for k, v in payload.items()
                              if k not in ("name", "tenant_id")}
            agent_resp = client.agents.update(existing_id, **update_payload)
            console.print(f"[blue]Updated:[/blue] Agent '{name}' ({agent_resp.id})")
        else:
            agent_resp = client.agents.create(**payload)
            console.print(f"[green]Created:[/green] Agent '{name}' ({agent_resp.id})")

        if submit and agent_resp.status == "draft":
            agent_resp = client.agents.submit(str(agent_resp.id))
            console.print(f"[green]Submitted:[/green] Agent '{name}' for governance review")


def _apply_registry_config(
    cfg: RegistryConfig, registry: str | None, dry_run: bool
) -> None:
    tenant = cfg.metadata.tenant

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would apply RegistryConfig for tenant '{tenant}'")
        console.print(f"  guardrails: {len(cfg.guardrails)}")
        console.print(f"  mesh_policies: {len(cfg.mesh_policies)}")
        console.print(f"  compliance_rules: {len(cfg.compliance_rules)}")
        return

    with _get_client(registry) as client:
        # Apply guardrails
        for g in cfg.guardrails:
            existing = _find_guardrail_by_name(client, g.name)
            if existing:
                client.guardrails.update(
                    str(existing.id),
                    name=g.name,
                    type=g.type,
                    mechanism=g.mechanism,
                    enforcement_mode=g.enforcement,
                    config=g.config,
                    description=g.description,
                )
                console.print(f"[blue]Updated:[/blue] Guardrail '{g.name}'")
            else:
                client.guardrails.create(
                    name=g.name,
                    type=g.type,
                    mechanism=g.mechanism,
                    enforcement_mode=g.enforcement,
                    config=g.config,
                    description=g.description,
                )
                console.print(f"[green]Created:[/green] Guardrail '{g.name}'")

        # Apply mesh policies
        for p in cfg.mesh_policies:
            client.mesh.create_policy(
                source_agent_name=p.source,
                dest_agent_name=p.destination,
                action=p.action,
                priority=p.priority,
            )
            console.print(f"[green]Applied:[/green] Policy {p.source} -> {p.destination} ({p.action})")

        # Apply compliance rules
        for r in cfg.compliance_rules:
            client.mesh.create_compliance_rule(
                rule_type=r.rule_type,
                source_value=r.source,
                dest_value=r.destination,
                action=r.action,
                priority=r.priority,
            )
            console.print(f"[green]Applied:[/green] Compliance rule '{r.name}'")


def _find_guardrail_by_name(client: RecursantClient, name: str):
    """Find a guardrail by name, return None if not found."""
    try:
        guardrails = client.guardrails.list()
        for g in guardrails:
            if g.name == name:
                return g
    except Exception:
        pass
    return None
