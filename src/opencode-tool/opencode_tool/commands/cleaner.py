"""Background cleaner for opencode-tool profiles.

Runs as a daemon, periodically cleaning orphaned profiles and zombie servers.

Usage:
    opencode-tool cleaner start       # start in background
    opencode-tool cleaner stop        # stop daemon
    opencode-tool cleaner status      # check if running
    opencode-tool cleaner run-once    # clean once and exit
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
from rich.console import Console

from ..registry import (
    OPENTOOL_DIR,
    load_registry,
    save_registry,
    is_pid_alive,
    cleanup_stale_entries,
    list_profiles,
    load_profile_env,
    get_servers_by_profile,
    delete_profile_dir,
    profile_exists,
)

# Stale threshold: 10 minutes without use
STALE_THRESHOLD_SECONDS = 600


def _is_tmux_session_alive(session_name: str) -> bool:
    """Check if a tmux session exists."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _kill_tmux_session(session_name: str):
    """Kill a tmux session."""
    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _parse_timestamp(ts_str: str) -> float:
    """Parse ISO timestamp to Unix time. Returns 0 on failure."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0


console = Console()

CLEANER_PID_FILE = OPENTOOL_DIR / "cleaner.pid"
CLEANER_LOG_FILE = OPENTOOL_DIR / "cleaner.log"
CLEANER_INTERVAL = 300  # 5 minutes default


def _log(message: str):
    """Write to cleaner log."""
    try:
        with open(CLEANER_LOG_FILE, "a") as f:
            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {message}\n")
    except:
        pass


def _clean_once() -> dict:
    """Run one cleanup cycle. Returns stats."""
    stats = {"servers_killed": 0, "profiles_deleted": 0, "registry_cleaned": 0}
    registry = load_registry()
    profiles = list_profiles()
    now = time.time()

    # Check servers in registry
    servers_to_remove = []
    for server in registry.get("servers", []):
        server_id = server.get("id")
        pid = server.get("pid")
        shell_pid = server.get("shell_pid")
        status = server.get("status")
        tmux_session = server.get("tmux_session")
        last_used_at = server.get("last_used_at", "")

        server_alive = pid and is_pid_alive(pid)
        shell_alive = shell_pid and is_pid_alive(shell_pid)

        # Check tmux session if applicable
        tmux_alive = False
        if tmux_session:
            tmux_alive = _is_tmux_session_alive(tmux_session)
        
        # Check staleness (last used > 10 minutes ago)
        last_used_ts = _parse_timestamp(last_used_at)
        stale = (now - last_used_ts) > STALE_THRESHOLD_SECONDS if last_used_ts > 0 else False

        is_orphan = False
        reason = None

        if status == "running" and not server_alive:
            is_orphan = True
            reason = "server dead"
        elif status == "running" and tmux_session and not tmux_alive:
            is_orphan = True
            reason = "tmux session dead"
        elif status == "running" and not tmux_session and not shell_alive:
            is_orphan = True
            reason = "shell dead (no tmux)"
        elif status == "running" and stale:
            is_orphan = True
            reason = f"stale ({int(now - last_used_ts)}s since last use)"

        if is_orphan:
            _log(f"Orphan server: {server_id} ({reason})")
            if server_alive:
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
            # Kill tmux session if it exists
            if tmux_session and tmux_alive:
                _kill_tmux_session(tmux_session)
                _log(f"Killed tmux session: {tmux_session}")
            servers_to_remove.append(server_id)
            stats["servers_killed"] += 1

    # Remove orphaned servers from registry
    if servers_to_remove:
        registry["servers"] = [
            s for s in registry.get("servers", [])
            if s.get("id") not in servers_to_remove
        ]
        save_registry(registry)
        stats["registry_cleaned"] = len(servers_to_remove)

    # Check profiles for orphans
    for profile_name in profiles:
        # Skip protected profiles
        env_data = load_profile_env(profile_name)
        if env_data.get("protected") or profile_name == "default":
            continue

        profile_servers = get_servers_by_profile(profile_name)
        has_running = any(s.get("status") == "running" for s in profile_servers)

        if not has_running:
            # Check if any server has a tmux session
            tmux_session = None
            for s in profile_servers:
                tmux_session = s.get("tmux_session")
                if tmux_session:
                    break
            
            if tmux_session:
                # Check if tmux session is alive
                tmux_alive = _is_tmux_session_alive(tmux_session)
                if not tmux_alive:
                    _log(f"Orphan profile: {profile_name} (no server, tmux dead)")
                    delete_profile_dir(profile_name)
                    stats["profiles_deleted"] += 1
            else:
                # Legacy: check shell PID
                shell_pid = None
                for s in profile_servers:
                    shell_pid = s.get("shell_pid")
                    if shell_pid:
                        break

                shell_alive = shell_pid and is_pid_alive(shell_pid)

                if not shell_alive:
                    _log(f"Orphan profile: {profile_name} (no server, shell dead)")
                    delete_profile_dir(profile_name)
                    stats["profiles_deleted"] += 1

    # Cleanup stale registry entries
    cleanup_stale_entries()

    return stats


def _is_running() -> bool:
    """Check if cleaner daemon is running."""
    if not CLEANER_PID_FILE.exists():
        return False
    try:
        pid = int(CLEANER_PID_FILE.read_text().strip())
        return is_pid_alive(pid)
    except:
        return False


def _get_pid() -> int:
    """Get cleaner daemon PID."""
    try:
        return int(CLEANER_PID_FILE.read_text().strip())
    except:
        return 0


def _daemon_loop(interval: int):
    """Main daemon loop."""
    _log("Cleaner daemon started")
    _log(f"Interval: {interval}s")

    # Write PID file
    CLEANER_PID_FILE.write_text(str(os.getpid()))

    # Setup signal handlers
    def handle_stop(signum, frame):
        _log("Cleaner daemon stopping")
        CLEANER_PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    while True:
        try:
            stats = _clean_once()
            if any(v > 0 for v in stats.values()):
                _log(f"Cleaned: {stats}")
        except Exception as e:
            _log(f"Error: {e}")

        time.sleep(interval)


@click.group()
def cleaner():
    """Background profile cleaner.

    Automatically cleans orphaned profiles and zombie servers.
    """
    pass


@cleaner.command("start")
@click.option("--interval", default=CLEANER_INTERVAL, help="Cleanup interval in seconds")
def start(interval: int):
    """Start cleaner daemon in background."""
    if _is_running():
        console.print("[yellow]Cleaner already running[/yellow]")
        console.print(f"  PID: {_get_pid()}")
        return

    # Fork to background
    pid = os.fork()
    if pid > 0:
        # Parent process
        console.print(f"[green]Cleaner started[/green]")
        console.print(f"  PID: {pid}")
        console.print(f"  Interval: {interval}s")
        console.print(f"  Log: {CLEANER_LOG_FILE}")
        return
    else:
        # Child process — become session leader
        os.setsid()
        _daemon_loop(interval)


@cleaner.command("stop")
def stop():
    """Stop cleaner daemon."""
    if not _is_running():
        console.print("[yellow]Cleaner not running[/yellow]")
        return

    pid = _get_pid()
    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Cleaner stopped (PID {pid})[/green]")
    except Exception as e:
        console.print(f"[red]Failed to stop: {e}[/red]")

    CLEANER_PID_FILE.unlink(missing_ok=True)


@cleaner.command("status")
def status():
    """Check cleaner status."""
    if _is_running():
        pid = _get_pid()
        console.print(f"[green]Cleaner running[/green]")
        console.print(f"  PID: {pid}")

        # Show last log lines
        if CLEANER_LOG_FILE.exists():
            console.print(f"\n  Recent log:")
            lines = CLEANER_LOG_FILE.read_text().strip().split("\n")
            for line in lines[-5:]:
                console.print(f"    {line}")
    else:
        console.print("[yellow]Cleaner not running[/yellow]")


@cleaner.command("run-once")
def run_once():
    """Run cleanup once and exit."""
    stats = _clean_once()
    if any(v > 0 for v in stats.values()):
        console.print(f"[green]Cleaned:[/green]")
        console.print(f"  Servers killed:    {stats['servers_killed']}")
        console.print(f"  Profiles deleted:  {stats['profiles_deleted']}")
        console.print(f"  Registry cleaned:  {stats['registry_cleaned']}")
    else:
        console.print("[green]Nothing to clean[/green]")


@cleaner.command("log")
@click.option("--lines", "-n", default=20, help="Number of lines to show")
def log(lines: int):
    """Show cleaner log."""
    if not CLEANER_LOG_FILE.exists():
        console.print("[yellow]No log file[/yellow]")
        return

    all_lines = CLEANER_LOG_FILE.read_text().strip().split("\n")
    for line in all_lines[-lines:]:
        console.print(line)
