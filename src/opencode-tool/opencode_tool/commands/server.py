"""Server management commands."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List

import click
import requests
from rich.console import Console

from ..api import OpenCodeAPI
from ..config import get_server_url, get_config_value

console = Console()


@click.group()
def server():
    """Manage OpenCode server."""
    pass


@server.command()
@click.option("--port", default=0, type=int, help="Port to listen on (default: 0 = random)")
@click.option("--hostname", default="127.0.0.1", help="Hostname to listen on")
@click.option("--password", default=None, help="Server password (or use OPENCODE_SERVER_PASSWORD env)")
@click.option("--print-logs", is_flag=True, help="Print logs to stderr")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"]), default=None, help="Log level")
@click.option("--pure", is_flag=True, help="Run without external plugins")
@click.option("--mdns", is_flag=True, help="Enable mDNS service discovery")
@click.option("--mdns-domain", default="opencode.local", help="Custom domain name for mDNS service")
@click.option("--cors", multiple=True, help="Additional domains to allow for CORS")
def serve(
    port: int,
    hostname: str,
    password: Optional[str],
    print_logs: bool,
    log_level: Optional[str],
    pure: bool,
    mdns: bool,
    mdns_domain: str,
    cors: tuple,
):
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
    
    # Get password from config if not provided
    if not password:
        password = get_config_value("opencode_server_password")
    
    console.print(f"[green]Starting OpenCode server on {hostname}:{port}...[/green]")
    
    # Build command - match opencode serve parameters
    cmd = [opencode_bin, "serve"]
    
    if port:
        cmd.extend(["--port", str(port)])
    
    cmd.extend(["--hostname", hostname])
    
    if print_logs:
        cmd.append("--print-logs")
    
    if log_level:
        cmd.extend(["--log-level", log_level])
    
    if pure:
        cmd.append("--pure")
    
    if mdns:
        cmd.append("--mdns")
        if mdns_domain != "opencode.local":
            cmd.extend(["--mdns-domain", mdns_domain])
    
    for domain in cors:
        cmd.extend(["--cors", domain])
    
    # Setup environment with password if provided
    import os
    env = os.environ.copy()
    if password:
        env["OPENCODE_SERVER_PASSWORD"] = password
        console.print(f"[yellow]Password authentication enabled[/yellow]")
    
    # Start server in background
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env
    )
    
    # Wait for startup
    console.print("Waiting for server to start...")
    for i in range(30):
        time.sleep(1)
        try:
            # Try without auth first
            resp = requests.get(f"http://{hostname}:{port}/global/health" if port else f"http://{hostname}/global/health", timeout=2)
            if resp.status_code == 200:
                console.print(f"[green]✓ Server started (PID {proc.pid})[/green]")
                return
            # Try with auth if configured
            if password:
                resp = requests.get(
                    f"http://{hostname}:{port}/global/health" if port else f"http://{hostname}/global/health",
                    auth=("opencode", password),
                    timeout=2
                )
                if resp.status_code == 200:
                    console.print(f"[green]✓ Server started with auth (PID {proc.pid})[/green]")
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
    
    # Check if auth is configured
    password = get_config_value("opencode_server_password")
    if password:
        console.print(f"Auth: [green]configured[/green]")
    
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
