"""recursant init — generate skeleton config."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()

SKELETON = """\
apiVersion: recursant/v1
kind: Agent
metadata:
  name: my-agent
  version: "0.1.0"
  tenant: default
spec:
  classification: internal
  data_sensitivity: none
  risk_tier: low
  description: "My agent description"
  owner_id: my-team
  team_id: my-team
  contact_email: team@example.com
  endpoint:
    url: http://localhost:8001
    type: {endpoint_type}
    auth_method: api_key
    timeout_seconds: 30
    protocol: A2A
  capabilities:
    - name: default
      description: "Default capability"
  quotas:
    max_tokens_per_request: 4096
    max_requests_per_minute: 100
    max_cost_per_day_usd: 50.0
"""


def init(
    endpoint_type: str = typer.Option(
        "custom",
        "--type",
        "-t",
        help="Endpoint type (langchain, crewai, langgraph, openai, custom)",
    ),
    output: str = typer.Option(
        "recursant.yaml",
        "--output",
        "-o",
        help="Output file path",
    ),
) -> None:
    """Generate a skeleton recursant.yaml config file."""
    path = Path(output)
    if path.exists():
        overwrite = typer.confirm(f"{path} already exists. Overwrite?")
        if not overwrite:
            raise typer.Abort()

    content = SKELETON.format(endpoint_type=endpoint_type)
    path.write_text(content)
    console.print(f"Created [bold]{path}[/bold]")
