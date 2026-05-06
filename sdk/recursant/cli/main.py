"""Recursant CLI — entry point."""

from __future__ import annotations

import typer

from recursant.cli.commands.apply import apply
from recursant.cli.commands.deploy_cmd import deploy_cmd
from recursant.cli.commands.init_cmd import init
from recursant.cli.commands.status import status
from recursant.cli.commands.validate import validate

app = typer.Typer(
    name="recursant",
    help="Recursant Agent Registry CLI",
    no_args_is_help=True,
)

app.command("init")(init)
app.command("validate")(validate)
app.command("apply")(apply)
app.command("deploy")(deploy_cmd)
app.command("status")(status)

if __name__ == "__main__":
    app()
