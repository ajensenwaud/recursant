"""recursant validate — validate config files locally."""

from __future__ import annotations

import typer
from rich.console import Console

from recursant.config import validate_config

console = Console()


def validate(
    file: str = typer.Option(
        ...,
        "--file",
        "-f",
        help="Path to YAML config file",
    ),
) -> None:
    """Validate a recursant.yaml or registry-config.yaml file."""
    errors = validate_config(file)
    if errors:
        for err in errors:
            console.print(f"[red]ERROR:[/red] {err}")
        raise typer.Exit(code=1)
    console.print(f"[green]Valid:[/green] {file}")
