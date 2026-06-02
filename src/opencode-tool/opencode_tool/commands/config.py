"""Configuration management commands."""

import click
from rich.console import Console

from ..config import load_config, set_config, get_config_value, CONFIG_FILE

console = Console()


@click.group()
def config():
    """Manage OpenCode Python CLI configuration."""
    pass


@config.command("get")
@click.argument("key", required=False)
def config_get(key: str):
    """Get configuration value(s)."""
    if key:
        value = get_config_value(key)
        if value is None:
            console.print(f"[red]key not found: {key}[/red]")
            raise SystemExit(1)
        console.print(f"{key} = {value}")
    else:
        config = load_config()
        for k, v in config.items():
            console.print(f"{k} = {v}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value."""
    set_config(key, value)
    console.print(f"[green]Set {key} = {value}[/green]")


@config.command("path")
def config_path():
    """Show configuration file path."""
    console.print(f"Config file: [cyan]{CONFIG_FILE}[/cyan]")
