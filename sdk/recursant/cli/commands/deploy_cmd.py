"""recursant deploy — register + submit agent."""

from __future__ import annotations

import os

import typer
from rich.console import Console

from recursant.agent import Agent
from recursant.deploy import deploy
from recursant.exceptions import RecursantError

console = Console()


def deploy_cmd(
    file: str = typer.Option(
        "recursant.yaml",
        "--file",
        "-f",
        help="Path to recursant.yaml config file",
    ),
    registry: str = typer.Option(
        None,
        "--registry",
        "-r",
        help="Registry URL (or RECURSANT_REGISTRY_URL env var)",
    ),
) -> None:
    """Register and submit an agent through the governance pipeline."""
    url = registry or os.environ.get("RECURSANT_REGISTRY_URL", "http://localhost:5000")

    try:
        agent = Agent.from_config(file)
    except RecursantError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        result = deploy(
            agent,
            url,
            username=os.environ.get("RECURSANT_USERNAME"),
            password=os.environ.get("RECURSANT_PASSWORD"),
            api_key=os.environ.get("RECURSANT_API_KEY"),
            tenant_id=os.environ.get("RECURSANT_TENANT_ID"),
        )
    except RecursantError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(code=1)

    if result.created:
        console.print(f"[green]Created:[/green] Agent '{agent.name}' ({result.agent.id})")
    elif result.updated:
        console.print(f"[blue]Updated:[/blue] Agent '{agent.name}' ({result.agent.id})")

    if result.submitted:
        console.print(f"[green]Submitted:[/green] Agent '{agent.name}' for governance review")

    if result.errors:
        for err in result.errors:
            console.print(f"[yellow]WARNING:[/yellow] {err}")

    console.print(f"Status: {result.agent.status}")
