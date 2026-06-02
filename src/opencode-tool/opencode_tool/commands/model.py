"""Model command for OpenCode - list available models."""

import click
from rich.console import Console
from rich.table import Table

from ..api import OpenCodeAPI

console = Console()


@click.group()
def model():
    """Model management commands."""
    pass


@model.command("list")
@click.option("--provider", "-p", help="Filter by provider name")
@click.option("--search", "-s", help="Search model names")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def list_models(provider, search, json_out):
    """List all available models from providers.
    
    Examples:
        opencode-tool model list
        opencode-tool model list --provider opencode-go
        opencode-tool model list --search mimo
    """
    api = OpenCodeAPI()
    
    if not api.is_healthy():
        console.print("[red]error: server not running[/red]")
        raise SystemExit(1)
    
    models = api.list_models()
    
    # Apply filters
    if provider:
        models = [m for m in models if provider.lower() in m["provider"].lower()]
    if search:
        models = [m for m in models if search.lower() in m["model_id"].lower() or search.lower() in m["name"].lower()]
    
    if json_out:
        import json
        print(json.dumps(models, indent=2))
        return
    
    if not models:
        console.print("[yellow]No models found[/yellow]")
        return
    
    # Sort by provider then model_id
    models.sort(key=lambda m: (m["provider"], m["model_id"]))
    
    table = Table(title=f"Available Models ({len(models)} total)")
    table.add_column("Provider", style="cyan")
    table.add_column("Model ID", style="green")
    table.add_column("Name", style="white")
    
    for m in models:
        table.add_row(m["provider"], m["model_id"], m["name"])
    
    console.print(table)
