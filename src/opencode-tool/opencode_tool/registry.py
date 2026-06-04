"""Server registry and port detection for opencode-tool.

Manages persistent tracking of server instances across profiles.
Handles port conflict detection and server lifecycle.
"""

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

# Paths
OPENTOOL_DIR = Path.home() / ".opencode-tool"
REGISTRY_FILE = OPENTOOL_DIR / "registry.json"
PROFILES_DIR = OPENTOOL_DIR / "profiles"

# Port range for auto-start
DEFAULT_PORT_START = 16384
MAX_PORT_ATTEMPTS = 100

# Cleanup threshold (hours)
CLEANUP_HOURS = 24


def ensure_dirs():
    """Create opencode-tool directories if they don't exist."""
    OPENTOOL_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def load_registry() -> dict:
    """Load server registry from disk."""
    ensure_dirs()
    if not REGISTRY_FILE.exists():
        return {"servers": [], "version": 1}
    try:
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"servers": [], "version": 1}


def save_registry(registry: dict):
    """Save server registry to disk."""
    ensure_dirs()
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def _generate_server_id() -> str:
    """Generate a unique server ID using UUID."""
    return f"server_{uuid.uuid4().hex[:12]}"


def _generate_profile_name() -> str:
    """Generate a random profile name using UUID."""
    return uuid.uuid4().hex[:12]


def is_port_free_in_os(port: int) -> bool:
    """Check if port is available at OS level."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def is_port_available(port: int, registry: Optional[dict] = None) -> bool:
    """Check if port is free (OS + registry)."""
    if not is_port_free_in_os(port):
        return False

    if registry:
        for server in registry.get("servers", []):
            if server.get("port") == port and server.get("status") == "running":
                return False

    return True


def find_available_port(
    start: int = DEFAULT_PORT_START,
    max_attempts: int = MAX_PORT_ATTEMPTS,
    registry: Optional[dict] = None,
) -> int:
    """Find an available port, checking for conflicts."""
    if registry is None:
        registry = load_registry()

    for port in range(start, start + max_attempts):
        if is_port_available(port, registry):
            return port

    raise RuntimeError(f"No available port in range {start}-{start + max_attempts}")


def register_server(
    url: str,
    port: int,
    pid: int,
    profile_name: str,
    mode: str = "isolated",
    directory: Optional[str] = None,
    shell_pid: Optional[int] = None,
    tmux_session: Optional[str] = None,
) -> str:
    """Register a new server in the registry. Returns server ID."""
    registry = load_registry()
    server_id = _generate_server_id()

    now = datetime.now(timezone.utc).isoformat()
    server_entry = {
        "id": server_id,
        "url": url,
        "port": port,
        "pid": pid,
        "profile": profile_name,
        "mode": mode,
        "started_at": now,
        "created_at": now,
        "last_used_at": now,
        "status": "running",
        "directory": directory or os.getcwd(),
        "shell_pid": shell_pid or os.getppid(),
        "tmux_session": tmux_session,
    }

    registry["servers"].append(server_entry)
    save_registry(registry)

    return server_id


def update_server_status(server_id: str, status: str):
    """Update server status in registry."""
    registry = load_registry()
    for server in registry.get("servers", []):
        if server.get("id") == server_id:
            server["status"] = status
            if status == "stopped":
                server["stopped_at"] = datetime.now(timezone.utc).isoformat()
            break
    save_registry(registry)


def update_server_last_used(server_id: str):
    """Update last_used_at timestamp for a server."""
    registry = load_registry()
    for server in registry.get("servers", []):
        if server.get("id") == server_id:
            server["last_used_at"] = datetime.now(timezone.utc).isoformat()
            break
    save_registry(registry)


def remove_server(server_id: str):
    """Remove a server from registry."""
    registry = load_registry()
    registry["servers"] = [
        s for s in registry.get("servers", []) if s.get("id") != server_id
    ]
    save_registry(registry)


def get_server_by_id(server_id: str) -> Optional[dict]:
    """Get server entry by ID."""
    registry = load_registry()
    for server in registry.get("servers", []):
        if server.get("id") == server_id:
            return server
    return None


def get_servers_by_profile(profile_name: str) -> List[dict]:
    """Get all servers for a profile."""
    registry = load_registry()
    return [
        s for s in registry.get("servers", []) if s.get("profile") == profile_name
    ]


def get_running_servers() -> List[dict]:
    """Get all running servers."""
    registry = load_registry()
    return [
        s for s in registry.get("servers", []) if s.get("status") == "running"
    ]


def find_server_by_url(url: str) -> Optional[dict]:
    """Find a running server by URL. Returns first match or None."""
    registry = load_registry()
    for server in registry.get("servers", []):
        if server.get("url") == url and server.get("status") == "running":
            return server
    return None


def find_profile_by_url(url: str) -> Optional[str]:
    """Find profile name that owns a running server with this URL."""
    server = find_server_by_url(url)
    if server:
        return server.get("profile")
    return None


def url_is_available(url: str, exclude_profile: Optional[str] = None) -> bool:
    """Check if URL is available (not used by another running profile)."""
    registry = load_registry()
    for server in registry.get("servers", []):
        if server.get("url") == url and server.get("status") == "running":
            if exclude_profile and server.get("profile") == exclude_profile:
                continue  # Same profile, OK
            return False
    return True


def get_active_servers() -> List[dict]:
    """Get servers that appear to be alive (PID check)."""
    running = get_running_servers()
    alive = []
    for server in running:
        pid = server.get("pid")
        if pid and _is_pid_alive(pid):
            alive.append(server)
        else:
            update_server_status(server["id"], "stopped")
    return alive


def is_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# Keep private alias for internal use
_is_pid_alive = is_pid_alive


def cleanup_stale_entries():
    """Remove stopped servers older than CLEANUP_HOURS."""
    registry = load_registry()
    now = time.time()
    cutoff = now - (CLEANUP_HOURS * 3600)

    alive_servers = []
    for server in registry.get("servers", []):
        if server.get("status") == "stopped":
            stopped_at = server.get("stopped_at")
            if stopped_at:
                try:
                    stopped_time = datetime.fromisoformat(stopped_at).timestamp()
                    if stopped_time < cutoff:
                        continue  # Skip — too old
                except (ValueError, TypeError):
                    pass
        alive_servers.append(server)

    registry["servers"] = alive_servers
    save_registry(registry)


# Profile operations

def get_profile_dir(profile_name: str) -> Path:
    """Get profile directory path."""
    return PROFILES_DIR / profile_name


def profile_exists(profile_name: str) -> bool:
    """Check if a profile exists."""
    return get_profile_dir(profile_name).is_dir()


def create_profile_dir(profile_name: str) -> Path:
    """Create profile directory. Returns path."""
    profile_dir = get_profile_dir(profile_name)
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def delete_profile_dir(profile_name: str):
    """Delete profile directory and contents."""
    import shutil
    profile_dir = get_profile_dir(profile_name)
    if profile_dir.exists():
        shutil.rmtree(profile_dir)


def load_profile_env(profile_name: str) -> dict:
    """Load profile env.json."""
    profile_dir = get_profile_dir(profile_name)
    env_file = profile_dir / "env.json"
    if not env_file.exists():
        return {}
    try:
        with open(env_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_profile_env(profile_name: str, env_data: dict):
    """Save profile env.json."""
    profile_dir = create_profile_dir(profile_name)
    env_file = profile_dir / "env.json"
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=2)


def list_profiles() -> List[str]:
    """List all profile names."""
    ensure_dirs()
    return [
        d.name for d in PROFILES_DIR.iterdir()
        if d.is_dir() and (d / "env.json").exists()
    ]


def generate_profile_name() -> str:
    """Generate a random profile name."""
    return _generate_profile_name()
