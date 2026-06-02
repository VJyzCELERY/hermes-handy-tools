"""OpenCode Python CLI - Main entry point."""

import click
from rich.console import Console

from . import __version__
from .commands import config, server, session, permission, question, run, skills
from .commands.model import model as model_cmd

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="opencode-tool")
def cli():
    """OpenCode Python CLI - Python CLI for OpenCode server management."""
    pass


# Add commands
cli.add_command(config)
cli.add_command(server)
cli.add_command(session)
cli.add_command(permission)
cli.add_command(question)
cli.add_command(run)
cli.add_command(skills)
cli.add_command(model_cmd)


if __name__ == "__main__":
    cli()
