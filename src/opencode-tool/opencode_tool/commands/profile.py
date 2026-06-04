"""Profile management commands for opencode-tool.

Profiles provide per-shell isolation with their own server instances.
Default behavior: auto-create isolated profile on any command.

Usage:
    opencode-tool profile set [name]       # set active profile (outputs export)
    opencode-tool profile create [name]    # create without env output
    opencode-tool profile list             # list all profiles
    opencode-tool profile delete <name>    # delete a profile
    opencode-tool profile current          # show active profile
    opencode-tool profile status [name]    # show profile details
"""

import json
import os
import signal
import subprocess
import sys
import time
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from ..registry import (
    create_profile_dir,
    delete_profile_dir,
    find_available_port,
    generate_profile_name,
    get_active_servers,
    get_profile_dir,
    get_running_servers,
    get_server_by_id,
    get_servers_by_profile,
    load_profile_env,
    load_registry,
    list_profiles,
    profile_exists,
    register_server,
    save_profile_env,
    find_profile_by_url,
    url_is_available,
    save_registry,
)

console = Console()

# Default server URL
DEFAULT_URL = "http://localhost:4096"


def _get_active_profile() -> Optional[str]:
    """Get current active profile from env var."""
    return os.environ.get("OPENCODE_TOOL_PROFILE")


def _build_export_env(
    profile_name: str,
    url: str,
    mode: str = "isolated",
    server_id: Optional[str] = None,
) -> str:
    """Build shell export commands for profile activation."""
    lines = [
        f'export OPENCODE_SERVER_URL="{url}"',
        f'export OPENCODE_SERVER_MODE="{mode}"',
        f'export OPENCODE_TOOL_PROFILE="{profile_name}"',
    ]
    if server_id:
        lines.append(f'export OPENCODE_SERVER_ID="{server_id}"')
    return "\n".join(lines)


def _start_server_background(port: int, directory: Optional[str] = None) -> Optional[int]:
    """Start opencode serve in background. Returns PID or None on failure."""
    import shutil

    # Find opencode binary
    opencode_bin = shutil.which("opencode")
    if not opencode_bin:
        # Try common paths
        from pathlib import Path
        candidates = [
            Path.home() / ".linuxbrew" / "bin" / "opencode",
            Path("/usr/local/bin/opencode"),
            Path("/usr/bin/opencode"),
        ]
        for p in candidates:
            if p.exists():
                opencode_bin = str(p)
                break

    if not opencode_bin:
        return None

    cmd = [
        opencode_bin, "serve",
        "--port", str(port),
        "--hostname", "127.0.0.1",
    ]

    # Use cwd instead of --directory (opencode serve has no --directory flag)
    start_cwd = directory if directory else None

    # Start in background
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=start_cwd,
    )

    return proc.pid


def _wait_for_health(url: str, timeout: int = 10) -> bool:
    """Wait for server to become healthy."""
    import requests

    for _ in range(timeout * 2):  # Check every 0.5s
        try:
            resp = requests.get(f"{url}/global/health", timeout=1)
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(0.5)
    return False


def _create_and_start_profile(
    name: str,
    port: Optional[int] = None,
    directory: Optional[str] = None,
    mode: str = "isolated",
    url: Optional[str] = None,
) -> Optional[dict]:
    """Create profile, find port, start server. Returns profile info.

    Returns None if URL is already owned by another profile (caller should reuse).
    """
    # Find available port
    if port is None:
        port = find_available_port()

    # Build URL
    if url is None:
        url = f"http://localhost:{port}"

    # Check URL uniqueness — 1 URL = 1 profile
    existing_profile = find_profile_by_url(url)
    if existing_profile and existing_profile != name:
        return None  # URL taken by another profile

    # Create profile directory
    create_profile_dir(name)

    # Start server (isolated mode only)
    server_id = None
    pid = None
    if mode == "isolated":
        pid = _start_server_background(port, directory)
        if pid:
            # Wait for server to be ready
            if _wait_for_health(url):
                server_id = register_server(
                    url=url,
                    port=port,
                    pid=pid,
                    profile_name=name,
                    mode=mode,
                    directory=directory,
                )
            else:
                # Server failed to start
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
                console.print(f"[red]Server failed to start on port {port}[/red]")
                raise SystemExit(1)
    else:
        # Collaborate mode — just register the connection
        server_id = register_server(
            url=url,
            port=port,
            pid=0,  # Not our process
            profile_name=name,
            mode=mode,
            directory=directory,
        )

    # Save profile env
    env_data = {
        "name": name,
        "url": url,
        "port": port,
        "mode": mode,
        "server_id": server_id,
        "directory": directory or os.getcwd(),
    }
    save_profile_env(name, env_data)

    return env_data


@click.group()
def profile():
    """Manage opencode-tool profiles.

    A profile = a named configuration + its own server instance.
    Default behavior: auto-create isolated profile on any command.
    """
    pass


@profile.command("set")
@click.argument("name", required=False)
@click.option("--port", type=int, help="Port for the server")
@click.option("--dir", "directory", help="Working directory")
@click.option(
    "--collaborate",
    "collaborate_name",
    help="Connect to existing server (collaborate mode)",
)
@click.option("--url", help="Server URL (for collaborate mode)")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_set(
    name: Optional[str],
    port: Optional[int],
    directory: Optional[str],
    collaborate_name: Optional[str],
    url: Optional[str],
    json_out: bool,
):
    """Set active profile for this shell session.

    Outputs shell export commands for eval:
        eval $(opencode-tool profile set)
        eval $(opencode-tool profile set myproject)
        eval $(opencode-tool profile set --collaborate myuser)
    """
    # Generate name if not provided
    if not name:
        name = generate_profile_name()

    # Determine mode
    if collaborate_name:
        mode = "collaborate"
        if not url:
            url = DEFAULT_URL
        # Use collaborate_name as the profile name if none given
        if not name or name == collaborate_name:
            name = collaborate_name
    else:
        mode = "isolated"

    # Check if profile already exists — reuse it
    if profile_exists(name):
        env_data = load_profile_env(name)
        if env_data:
            # If existing profile has a running server, reuse it
            existing_url = env_data.get("url")
            if existing_url and url_is_available(existing_url, exclude_profile=name):
                export_cmd = _build_export_env(
                    profile_name=name,
                    url=existing_url,
                    mode=env_data.get("mode", mode),
                    server_id=env_data.get("server_id"),
                )
                if json_out:
                    print(json.dumps(env_data, indent=2))
                else:
                    click.echo(f"Profile: {name} (existing)", err=True)
                    click.echo(f"Mode:    {env_data.get('mode', mode)}", err=True)
                    click.echo(f"URL:     {existing_url}", err=True)
                    click.echo("", err=True)
                    print(export_cmd)
                return
            # URL conflict or no server — recreate
            url = existing_url or url
            mode = env_data.get("mode", mode)

    # Create or reuse profile
    env_data = _create_and_start_profile(
        name=name,
        port=port,
        directory=directory,
        mode=mode,
        url=url,
    )

    if env_data is None:
        # URL taken by another profile — find that profile
        existing = find_profile_by_url(url)
        console.print(f"[yellow]URL {url} already used by profile: {existing}[/yellow]")
        console.print(f"  Use: eval $(opencode-tool profile set {existing})")
        raise SystemExit(1)

    # Output export commands
    export_cmd = _build_export_env(
        profile_name=name,
        url=env_data["url"],
        mode=env_data["mode"],
        server_id=env_data.get("server_id"),
    )

    if json_out:
        print(json.dumps(env_data, indent=2))
    else:
        # Print info to stderr, exports to stdout
        click.echo(f"Profile: {name}", err=True)
        click.echo(f"Mode:    {mode}", err=True)
        click.echo(f"URL:     {env_data['url']}", err=True)
        if env_data.get("server_id"):
            click.echo(f"Server:  {env_data['server_id']}", err=True)
        click.echo("", err=True)
        # Exports go to stdout for eval
        print(export_cmd)

    # Persist active profile to file
    from ..auto_init import set_active_profile
    set_active_profile(name)


@profile.command("create")
@click.argument("name", required=False)
@click.option("--port", type=int, help="Port for the server")
@click.option("--dir", "directory", help="Working directory")
@click.option(
    "--collaborate",
    "collaborate_name",
    help="Connect to existing server (collaborate mode)",
)
@click.option("--url", help="Server URL (for collaborate mode)")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_create(
    name: Optional[str],
    port: Optional[int],
    directory: Optional[str],
    collaborate_name: Optional[str],
    url: Optional[str],
    json_out: bool,
):
    """Create a profile without setting shell environment.

    Same as 'profile set' but does not output export commands.
    Useful for scripting or pre-creating profiles.
    """
    if not name:
        name = generate_profile_name()

    if collaborate_name:
        mode = "collaborate"
        if not url:
            url = DEFAULT_URL
        if not name or name == collaborate_name:
            name = collaborate_name
    else:
        mode = "isolated"

    env_data = _create_and_start_profile(
        name=name,
        port=port,
        directory=directory,
        mode=mode,
        url=url,
    )

    if env_data is None:
        existing = find_profile_by_url(url or f"http://localhost:{port}")
        console.print(f"[yellow]URL {url} already used by profile: {existing}[/yellow]")
        console.print(f"  Use: opencode-tool profile set {existing}")
        raise SystemExit(1)

    if json_out:
        print(json.dumps(env_data, indent=2))
    else:
        console.print(f"[green]Profile created: {name}[/green]")
        console.print(f"  Mode: {mode}")
        console.print(f"  URL:  {env_data['url']}")
        if env_data.get("server_id"):
            console.print(f"  Server: {env_data['server_id']}")


@profile.command("list")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_list(json_out: bool):
    """List all profiles."""
    profiles = list_profiles()

    if json_out:
        print(json.dumps({"profiles": profiles}, indent=2))
        return

    if not profiles:
        console.print("[yellow]No profiles found[/yellow]")
        return

    active = _get_active_profile()

    table = Table(title="Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Active", style="green")
    table.add_column("Protected", style="magenta")
    table.add_column("Mode", style="yellow")
    table.add_column("URL")

    for name in profiles:
        env_data = load_profile_env(name)
        is_active = name == active
        is_protected = env_data.get("protected") or name == "default"
        mode = env_data.get("mode", "?")
        url = env_data.get("url", "?")

        table.add_row(
            name,
            "✓" if is_active else "",
            "🔒" if is_protected else "",
            mode,
            url,
        )

    console.print(table)


@profile.command("current")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_current(json_out: bool):
    """Show the currently active profile."""
    active = _get_active_profile()

    if json_out:
        data = {"profile": active, "active": active is not None}
        if active:
            env_data = load_profile_env(active)
            data.update(env_data)
        print(json.dumps(data, indent=2))
        return

    if not active:
        console.print("[yellow]No active profile[/yellow]")
        console.print("  Run: eval $(opencode-tool profile set)")
        return

    env_data = load_profile_env(active)
    console.print(f"Profile: [cyan]{active}[/cyan]")
    console.print(f"Mode:    {env_data.get('mode', '?')}")
    console.print(f"URL:     {env_data.get('url', '?')}")


@profile.command("status")
@click.argument("name", required=False)
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_status(name: Optional[str], json_out: bool):
    """Show profile status and server info."""
    if not name:
        name = _get_active_profile()
    if not name:
        console.print("[yellow]No profile specified or active[/yellow]")
        return

    if not profile_exists(name):
        console.print(f"[red]Profile not found: {name}[/red]")
        raise SystemExit(1)

    env_data = load_profile_env(name)
    servers = get_servers_by_profile(name)

    if json_out:
        print(json.dumps({
            "profile": name,
            "env": env_data,
            "servers": servers,
        }, indent=2))
        return

    console.print(f"Profile: [cyan]{name}[/cyan]")
    console.print(f"Mode:    {env_data.get('mode', '?')}")
    console.print(f"URL:     {env_data.get('url', '?')}")
    console.print(f"Port:    {env_data.get('port', '?')}")
    console.print(f"Dir:     {env_data.get('directory', '?')}")

    if servers:
        console.print("\nServers:")
        for s in servers:
            status_color = "green" if s.get("status") == "running" else "red"
            console.print(
                f"  [{status_color}]{s['id']}[/{status_color}] "
                f"port={s.get('port')} pid={s.get('pid')} status={s.get('status')}"
            )


@profile.command("delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def profile_delete(name: str, force: bool):
    """Delete a profile and stop its servers."""
    if name == "default":
        console.print("[red]Cannot delete default profile[/red]")
        console.print("  Default profile can only be changed via config")
        raise SystemExit(1)

    if not profile_exists(name):
        console.print(f"[red]Profile not found: {name}[/red]")
        raise SystemExit(1)

    # Check if active
    active = _get_active_profile()
    if active == name:
        console.print("[red]Cannot delete active profile[/red]")
        console.print("  Run: eval $(opencode-tool env clear)")
        raise SystemExit(1)

    if not force:
        if not click.confirm(f"Delete profile '{name}'?"):
            return

    # Stop servers
    servers = get_servers_by_profile(name)
    for s in servers:
        if s.get("status") == "running" and s.get("pid"):
            try:
                os.kill(s["pid"], signal.SIGTERM)
            except:
                pass

    # Delete profile directory
    delete_profile_dir(name)

    console.print(f"[green]Deleted profile: {name}[/green]")


@profile.command("terminate")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def profile_terminate(name: str, force: bool):
    """Terminate a profile: kill server + delete profile + clean registry."""
    if name == "default":
        console.print("[red]Cannot terminate default profile[/red]")
        console.print("  Default profile can only be changed via config")
        raise SystemExit(1)

    if not profile_exists(name):
        console.print(f"[red]Profile not found: {name}[/red]")
        raise SystemExit(1)

    # Check if active
    active = _get_active_profile()
    if active == name:
        console.print("[red]Cannot terminate active profile[/red]")
        console.print("  Run: eval $(opencode-tool env clear)")
        raise SystemExit(1)

    if not force:
        if not click.confirm(f"Terminate profile '{name}' (kill server + delete)?"):
            return

    # Kill servers (only if localhost)
    servers = get_servers_by_profile(name)
    killed = 0
    for s in servers:
        pid = s.get("pid")
        url = s.get("url", "")
        is_localhost = "localhost" in url or "127.0.0.1" in url
        if pid and s.get("status") == "running" and is_localhost:
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except (OSError, ProcessLookupError):
                pass

    # Delete profile directory
    delete_profile_dir(name)

    console.print(f"[green]Terminated: {name}[/green]")
    if killed:
        console.print(f"  Killed {killed} server(s)")
    else:
        console.print(f"  Profile deleted (server not killed — remote URL)")


@profile.command("cleanup")
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_cleanup(dry_run: bool, json_out: bool):
    """Clean up orphaned profiles and zombie servers.
    
    Detects:
      - Servers whose owning shell is dead (zombie servers)
      - Profiles with no running server and dead shell
      - Stale registry entries
    """
    from ..registry import cleanup_stale_entries, is_pid_alive

    registry = load_registry()
    profiles = list_profiles()
    cleaned = {"servers_killed": 0, "profiles_deleted": 0, "registry_cleaned": 0}
    orphans = []

    # Check each server in registry
    servers_to_remove = []
    for server in registry.get("servers", []):
        server_id = server.get("id")
        pid = server.get("pid")
        shell_pid = server.get("shell_pid")
        profile = server.get("profile")
        status = server.get("status")

        # Check if server process is alive
        server_alive = pid and is_pid_alive(pid)
        # Check if owning shell is alive
        shell_alive = shell_pid and is_pid_alive(shell_pid)

        is_orphan = False
        reason = None

        if status == "running" and not server_alive:
            is_orphan = True
            reason = "server process dead"
        elif status == "running" and not shell_alive:
            is_orphan = True
            reason = "owning shell dead"

        if is_orphan:
            orphans.append({
                "server_id": server_id,
                "profile": profile,
                "port": server.get("port"),
                "reason": reason,
            })
            if not dry_run:
                # Kill if still somehow alive
                if server_alive:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except:
                        pass
                servers_to_remove.append(server_id)
                cleaned["servers_killed"] += 1

    # Remove orphaned servers from registry
    if not dry_run and servers_to_remove:
        registry["servers"] = [
            s for s in registry.get("servers", [])
            if s.get("id") not in servers_to_remove
        ]
        save_registry(registry)
        cleaned["registry_cleaned"] = len(servers_to_remove)

    # Check profiles for orphans (profile exists but no running server, shell dead)
    for profile_name in profiles:
        # Skip default profile — never clean it
        if profile_name == "default":
            continue

        env_data = load_profile_env(profile_name)
        profile_servers = get_servers_by_profile(profile_name)
        has_running = any(s.get("status") == "running" for s in profile_servers)

        if not has_running:
            # Profile has no running server — check if shell is dead
            shell_pid = None
            for s in profile_servers:
                shell_pid = s.get("shell_pid")
                if shell_pid:
                    break

            shell_alive = shell_pid and is_pid_alive(shell_pid)

            if not shell_alive:
                orphans.append({
                    "profile": profile_name,
                    "reason": "no running server, shell dead",
                })
                if not dry_run:
                    delete_profile_dir(profile_name)
                    cleaned["profiles_deleted"] += 1

    # Cleanup stale registry entries
    if not dry_run:
        cleanup_stale_entries()

    if json_out:
        print(json.dumps({
            "dry_run": dry_run,
            "orphans": orphans,
            "cleaned": cleaned,
        }, indent=2))
        return

    if not orphans:
        console.print("[green]No orphans found — everything clean[/green]")
        return

    action = "Would clean" if dry_run else "Cleaned"
    console.print(f"[yellow]{len(orphans)} orphan(s) found:[/yellow]")
    for o in orphans:
        name = o.get("profile", "?")
        reason = o.get("reason", "?")
        console.print(f"  {name}: {reason}")

    if dry_run:
        console.print(f"\n[dim]Run without --dry-run to clean[/dim]")
    else:
        console.print(f"\n[green]{action}:[/green]")
        console.print(f"  Servers killed:    {cleaned['servers_killed']}")
        console.print(f"  Profiles deleted:  {cleaned['profiles_deleted']}")
        console.print(f"  Registry cleaned:  {cleaned['registry_cleaned']}")
        console.print(f"  Registry cleaned:  {cleaned['registry_cleaned']}")


@profile.command("init")
@click.option("--json", "json_out", is_flag=True, help="Output JSON")
def profile_init(json_out: bool):
    """Initialize default profile with a running server.
    
    Uses URL from config. Does NOT start a server — connects to existing.
    """
    from ..auto_init import create_default_profile
    from ..config import get_server_url
    from ..api import OpenCodeAPI

    if profile_exists("default"):
        env_data = load_profile_env("default")
        if json_out:
            print(json.dumps(env_data, indent=2))
        else:
            console.print("[yellow]Default profile already exists[/yellow]")
            console.print(f"  URL: {env_data.get('url', '?')}")
        return

    # Check if server at config URL is running
    config_url = get_server_url()
    api = OpenCodeAPI(config_url)
    if not api.is_healthy():
        if not json_out:
            console.print(f"[yellow]Warning: Server at {config_url} not running[/yellow]")
            console.print("  Start it with: opencode-tool server serve")

    if not json_out:
        console.print("Creating default profile...")

    create_default_profile()

    if profile_exists("default"):
        env_data = load_profile_env("default")
        if json_out:
            print(json.dumps(env_data, indent=2))
        else:
            console.print("[green]Default profile created[/green]")
            console.print(f"  URL: {env_data.get('url', '?')}")
    else:
        console.print("[red]Failed to create default profile[/red]")
        raise SystemExit(1)


@profile.command("protect")
@click.argument("name")
def profile_protect(name: str):
    """Protect a profile from cleanup.

    Protected profiles are not removed by cleaner or cleanup.
    """
    if not profile_exists(name):
        console.print(f"[red]Profile not found: {name}[/red]")
        raise SystemExit(1)

    env_data = load_profile_env(name)
    env_data["protected"] = True
    save_profile_env(name, env_data)

    console.print(f"[green]Protected: {name}[/green]")


@profile.command("unprotect")
@click.argument("name")
def profile_unprotect(name: str):
    """Remove protection from a profile."""
    if not profile_exists(name):
        console.print(f"[red]Profile not found: {name}[/red]")
        raise SystemExit(1)

    env_data = load_profile_env(name)
    env_data.pop("protected", None)
    save_profile_env(name, env_data)

    console.print(f"[green]Unprotected: {name}[/green]")
