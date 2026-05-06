"""recursant status — show agent status."""

from __future__ import annotations

import os

import typer
from rich.console import Console
from rich.table import Table

from recursant.client import RecursantClient
from recursant.exceptions import RecursantError

console = Console()


def status(
    agent_name: str = typer.Argument(help="Agent name to check"),
    registry: str = typer.Option(
        None,
        "--registry",
        "-r",
        help="Registry URL (or RECURSANT_REGISTRY_URL env var)",
    ),
) -> None:
    """Show agent status and pipeline progress."""
    url = registry or os.environ.get("RECURSANT_REGISTRY_URL", "http://localhost:5000")

    try:
        with RecursantClient(
            url,
            username=os.environ.get("RECURSANT_USERNAME"),
            password=os.environ.get("RECURSANT_PASSWORD"),
            api_key=os.environ.get("RECURSANT_API_KEY"),
            tenant_id=os.environ.get("RECURSANT_TENANT_ID", "default"),
        ) as client:
            paginated = client.agents.list(name=agent_name)
            match = None
            for a in paginated.agents:
                if a.name == agent_name:
                    match = a
                    break

            if not match:
                console.print(f"[red]Agent '{agent_name}' not found[/red]")
                raise typer.Exit(code=1)

            # Get full details
            agent = client.agents.get(str(match.id))

            table = Table(title=f"Agent: {agent.name}")
            table.add_column("Field", style="bold")
            table.add_column("Value")

            table.add_row("ID", str(agent.id))
            table.add_row("Version", agent.version)
            table.add_row("Status", agent.status)
            table.add_row("Classification", agent.classification)
            table.add_row("Risk Tier", agent.risk_tier or "-")
            table.add_row("Team", agent.team_id or "-")
            table.add_row("Owner", agent.owner_id or "-")
            if agent.endpoint:
                table.add_row("Endpoint", agent.endpoint.get("url", "-"))
                table.add_row("Type", agent.endpoint.get("type", "-"))
            if agent.created_at:
                table.add_row("Created", str(agent.created_at))
            if agent.updated_at:
                table.add_row("Updated", str(agent.updated_at))

            console.print(table)

    except RecursantError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(code=1)
