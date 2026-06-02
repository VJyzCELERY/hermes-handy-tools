"""Permission management commands."""

import click
from rich.console import Console

from ..api import OpenCodeAPI

console = Console()


@click.group()
def permission():
    """Manage OpenCode permissions."""
    pass


@permission.command("list")
@click.argument("session_id", required=False)
@click.option("--all", "show_all", is_flag=True, help="Show all pending permissions")
def list_permissions(session_id: str, show_all: bool):
    """List pending permission requests."""
    api = OpenCodeAPI()
    
    permissions = api.get_permissions()
    
    if session_id:
        permissions = [p for p in permissions if p.get("sessionID") == session_id]
    elif not show_all:
        console.print("Usage: opencode-python permission list <session_id> | --all")
        raise SystemExit(1)
    
    if not permissions:
        console.print("[yellow]no pending permissions[/yellow]")
        return
    
    for p in permissions:
        pid = p.get("id", "?")
        sid = p.get("sessionID", "?")
        perm = p.get("permission", "?")
        patterns = p.get("patterns", [])
        always = p.get("always", [])
        console.print(f"[green][{pid}[/green]] session={sid} permission={perm}")
        console.print(f"  request: {', '.join(patterns)}")
        if always:
            console.print(f"  already allowed: {', '.join(always)}")
        console.print()


@permission.command()
@click.argument("session_id")
@click.argument("reply", type=click.Choice(["once", "always", "reject"]))
def grant(session_id: str, reply: str):
    """Grant or reject a pending permission request."""
    api = OpenCodeAPI()
    
    permissions = api.get_permissions()
    session_perms = [p for p in permissions if p.get("sessionID") == session_id]
    
    if not session_perms:
        console.print(f"[red]no pending permissions for {session_id}[/red]")
        raise SystemExit(1)
    
    for p in session_perms:
        pid = p.get("id")
        if not pid:
            continue
        
        if api.reply_permission(pid, reply):
            console.print(f"[green]granted: {pid} ({reply})[/green]")
        else:
            console.print(f"[red]failed: {pid}[/red]")
