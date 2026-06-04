"""OpenCode Python CLI - Main entry point."""

import click
from rich.console import Console

from . import __version__
from .commands import config, server, session, permission, question, run, skills
from .commands.model import model as model_cmd
from .commands.profile import profile as profile_cmd
from .commands.hitl import hitl as hitl_cmd
from .commands.cleaner import cleaner as cleaner_cmd
from .auto_init import ensure_profile

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="opencode-tool")
def cli():
    """OpenCode Python CLI - Python CLI for OpenCode server management."""
    from .auto_init import ensure_profile
    ensure_profile()


# Add commands
cli.add_command(config)
cli.add_command(server)
cli.add_command(session)
cli.add_command(permission)
cli.add_command(question)
cli.add_command(run)
cli.add_command(skills)
cli.add_command(model_cmd)
cli.add_command(profile_cmd)
cli.add_command(hitl_cmd)
cli.add_command(cleaner_cmd)


if __name__ == "__main__":
    cli()
