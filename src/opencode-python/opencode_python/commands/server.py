"""Server management commands."""

import subprocess
import sys
import time
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.table import Table

from ..api import OpenCodeAPI
from ..config import get_server_url

console = Console()


@click.group()
def server():
    """Manage OpenCode server."""
    pass


@server.command()
@click.option("--port", default=4096, help="Port to listen on")
@click.option("--hostname", default="127.0.0.1", help="Hostname to listen on")
def serve(port: int, hostname: str):
    """Start OpenCode server (localhost only)."""
    url = get_server_url()
    
    # Check if URL is localhost
    if "localhost" not in url and "127.0.0.1" not in url:
        console.print("[red]Error: server serve only works with localhost URLs[/red]")
        sys.exit(1)
    
    # Check if already running
    api = OpenCodeAPI()
    if api.is_healthy():
        console.print("[yellow]Server already running[/yellow]")
        return
    
    # Find opencode binary
    opencode_paths = [
        Path.home() / ".linuxbrew" / "bin" / "opencode",
        Path("/usr/local/bin/opencode"),
        Path("/usr/bin/opencode"),
    ]
    
    opencode_bin = None
    for path in opencode_paths:
        if path.exists():
            opencode_bin = str(path)
            break
    
    if not opencode_bin:
        # Try which
        try:
            result = subprocess.run(["which", "opencode"], capture_output=True, text=True)
            if result.returncode == 0:
                opencode_bin = result.stdout.strip()
        except:
            pass
    
    if not opencode_bin:
        console.print("[red]Error: opencode binary not found[/red]")
        sys.exit(1)
    
    console.print(f"[green]Starting OpenCode server on {hostname}:{port}...[/green]")
    
    # Start server in background
    cmd = [opencode_bin, "serve", "--port", str(port), "--hostname", hostname]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    # Wait for startup
    console.print("Waiting for server to start...")
    for i in range(30):
        time.sleep(1)
        try:
            resp = requests.get(f"http://{hostname}:{port}/global/health", timeout=2)
            if resp.status_code == 200:
                console.print(f"[green]✓ Server started (PID {proc.pid})[/green]")
                return
        except:
            pass
    
    console.print("[red]Error: Server failed to start within 30 seconds[/red]")
    sys.exit(1)


@server.command()
def status():
    """Check server status."""
    api = OpenCodeAPI()
    url = get_server_url()
    
    console.print(f"Server URL: [cyan]{url}[/cyan]")
    
    if api.is_healthy():
        health = api.health()
        console.print(f"Status: [green]Running[/green]")
        console.print(f"Version: {health.get('version', 'unknown')}")
        
        # Show session count
        try:
            sessions = api.get_sessions()
            console.print(f"Sessions: {len(sessions)}")
        except:
            pass
    else:
        console.print("Status: [red]Not running[/red]")


@server.command()
def stop():
    """Stop OpenCode server (localhost only)."""
    url = get_server_url()
    
    # Check if URL is localhost
    if "localhost" not in url and "127.0.0.1" not in url:
        console.print("[red]Error: server stop only works with localhost URLs[/red]")
        sys.exit(1)
    
    # Find opencode process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "opencode web"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            console.print("[yellow]No OpenCode server found[/yellow]")
            return
        
        pids = result.stdout.strip().split("\n")
        for pid in pids:
            if pid:
                subprocess.run(["kill", pid], capture_output=True)
                console.print(f"[green]Stopped process {pid}[/green]")
        
        console.print("[green]✓ Server stopped[/green]")
        
    except Exception as e:
        console.print(f"[red]Error stopping server: {e}[/red]")
        sys.exit(1)
