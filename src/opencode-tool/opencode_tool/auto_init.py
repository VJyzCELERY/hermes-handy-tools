"""Auto-initialization for opencode-tool profiles.

Lazy auto-init: only creates a profile when a command actually needs it.
Commands that need a server: run, hitl, session, permission, question.
Commands that don't: config, skills, profile list/current/status.

Tmux-based isolation:
- Each profile gets its own tmux session
- Shell persists across terminal() calls
- Cleaner can detect tmux session liveness
- Fallback to PID-based if tmux not available
"""

import os
import signal
import socket
import sys
import time
from typing import Optional
from urllib.parse import urlparse

from .registry import (
    create_profile_dir,
    find_available_port,
    generate_profile_name,
    load_profile_env,
    profile_exists,
    register_server,
    save_profile_env,
    OPENTOOL_DIR,
)
from .commands.profile import _start_server_background, _wait_for_health, _build_export_env


def _get_active_profile_file(pid: Optional[int] = None):
    """Get active profile file for given PID (or current shell PID).
    
    Args:
        pid: PID to use. If None, uses current shell's parent PID.
    """
    if pid is None:
        pid = os.getppid()  # Parent PID (the shell)
    return OPENTOOL_DIR / f"active-profile-{pid}"


ACTIVE_PROFILE_FILE = None  # Computed per-call


def get_active_profile() -> Optional[str]:
    """Check if shell has active profile.
    
    Checks in order:
      1. Environment variable (set by eval)
      2. Active profile file (persistent across runs)
    """
    # Check env var first
    profile = os.environ.get("OPENCODE_TOOL_PROFILE")
    if profile:
        return profile

    # Check file-based persistence
    profile_file = _get_active_profile_file()
    if profile_file.exists():
        try:
            profile = profile_file.read_text().strip()
            if profile and profile_exists(profile):
                # Set env vars for this process
                env_data = load_profile_env(profile)
                if env_data:
                    os.environ["OPENCODE_SERVER_URL"] = env_data.get("url", "")
                    os.environ["OPENCODE_SERVER_MODE"] = env_data.get("mode", "isolated")
                    os.environ["OPENCODE_TOOL_PROFILE"] = profile
                    if env_data.get("server_id"):
                        os.environ["OPENCODE_SERVER_ID"] = env_data["server_id"]
                return profile
        except Exception:
            pass

    return None


def set_active_profile(profile_name: str, pid: Optional[int] = None):
    """Set active profile in file-based persistence.
    
    Args:
        profile_name: Profile to set as active
        pid: PID to use for file name. If None, uses current shell PID.
             For tmux-based profiles, use the tmux shell PID.
    """
    OPENTOOL_DIR.mkdir(parents=True, exist_ok=True)
    profile_file = _get_active_profile_file(pid)
    profile_file.write_text(profile_name)


def ensure_profile() -> Optional[str]:
    """Ensure a profile exists for this session.
    
    Returns profile name if:
      - Profile already active via env var, OR
      - New profile created
    
    Creates new profile on EVERY call unless env var is set.
    Outputs export commands to stderr so user can eval them.
    """
    # Ensure default profile exists
    if not profile_exists("default"):
        create_default_profile()

    # Already have active profile — use it
    profile = get_active_profile()
    if profile:
        return profile

    # Check if we should auto-init
    if not _should_auto_init():
        return None

    # Try tmux-based profile first, fallback to legacy
    return _auto_init_profile()


def _auto_init_profile() -> Optional[str]:
    """Create ephemeral profile with tmux-based isolation.
    
    Tries tmux first, falls back to legacy PID-based if tmux unavailable.
    """
    try:
        from .tmux import is_tmux_available
        if is_tmux_available():
            return _auto_init_profile_tmux()
        else:
            return _auto_init_profile_legacy()
    except ImportError:
        return _auto_init_profile_legacy()


def _auto_init_profile_tmux() -> Optional[str]:
    """Create ephemeral profile using tmux for shell persistence."""
    from .tmux import (
        create_tmux_session, send_tmux_keys, kill_tmux_session,
        get_tmux_session_pid, is_tmux_session_alive
    )
    
    try:
        name = generate_profile_name()
        port = find_available_port()
        url = f"http://localhost:{port}"
        tmux_session = f"opencode-{name}"
        
        # Create tmux session
        if not create_tmux_session(tmux_session):
            return None
        
        # Start opencode server inside tmux
        server_cmd = f"opencode serve --port {port} --hostname 127.0.0.1"
        if not send_tmux_keys(tmux_session, server_cmd):
            kill_tmux_session(tmux_session)
            return None
        
        # Wait for health
        if not _wait_for_health(url):
            kill_tmux_session(tmux_session)
            return None
        
        # Get tmux shell PID for active-profile file
        tmux_pid = get_tmux_session_pid(tmux_session)
        if not tmux_pid:
            kill_tmux_session(tmux_session)
            return None
        
        # Register in registry with tmux info
        server_id = register_server(
            url=url,
            port=port,
            pid=tmux_pid,
            profile_name=name,
            mode="isolated",
            tmux_session=tmux_session,
        )
        
        # Save profile env
        env_data = _fork_default_profile(name, url, port, server_id)
        env_data["tmux_session"] = tmux_session
        save_profile_env(name, env_data)
        
        # Set env vars for this process
        os.environ["OPENCODE_SERVER_URL"] = url
        os.environ["OPENCODE_SERVER_MODE"] = "isolated"
        os.environ["OPENCODE_TOOL_PROFILE"] = name
        os.environ["OPENCODE_SERVER_ID"] = server_id
        
        # Output export commands to stderr for user to eval
        export_cmd = _build_export_env(name, url, "isolated", server_id)
        print(export_cmd, file=sys.stderr)
        
        # Persist active profile to file (using tmux PID)
        set_active_profile(name, tmux_pid)
        
        return name
        
    except Exception:
        return None


def _auto_init_profile_legacy() -> Optional[str]:
    """Create ephemeral profile using legacy PID-based isolation.
    
    Fallback when tmux is not available.
    """
    try:
        name = generate_profile_name()
        port = find_available_port()
        url = f"http://localhost:{port}"

        # Create profile directory
        create_profile_dir(name)

        # Start server
        pid = _start_server_background(port)
        if not pid:
            return None

        # Wait for health
        if not _wait_for_health(url):
            try:
                os.kill(pid, signal.SIGTERM)
            except:
                pass
            return None

        # Register in registry
        server_id = register_server(
            url=url,
            port=port,
            pid=pid,
            profile_name=name,
            mode="isolated",
        )

        # Save profile env
        env_data = _fork_default_profile(name, url, port, server_id)
        save_profile_env(name, env_data)

        # Set env vars for this process
        os.environ["OPENCODE_SERVER_URL"] = url
        os.environ["OPENCODE_SERVER_MODE"] = "isolated"
        os.environ["OPENCODE_TOOL_PROFILE"] = name
        os.environ["OPENCODE_SERVER_ID"] = server_id

        # Output export commands to stderr for user to eval
        export_cmd = _build_export_env(name, url, "isolated", server_id)
        print(export_cmd, file=sys.stderr)

        # Persist active profile to file
        set_active_profile(name)

        return name

    except Exception:
        return None


def create_default_profile():
    """Create the default profile if it doesn't exist.
    
    Uses opencode_server_url from config directly.
    Connects to existing server — does NOT start a new one.
    """
    if profile_exists("default"):
        return

    try:
        name = "default"
        # Get URL from config
        from .config import get_server_url
        url = get_server_url()

        # Parse port from URL
        parsed = urlparse(url)
        port = parsed.port or 4096

        create_profile_dir(name)

        # Register as our server (don't start — connect to existing)
        server_id = register_server(
            url=url,
            port=port,
            pid=0,  # Not our process — connecting to existing
            profile_name=name,
            mode="collaborate",
        )

        env_data = {
            "name": name,
            "url": url,
            "port": port,
            "mode": "collaborate",
            "server_id": server_id,
        }

        # Save model/variant from config
        from .config import get_config_value
        env_data["default_model"] = get_config_value("default_model")
        env_data["default_variant"] = get_config_value("default_variant")

        save_profile_env(name, env_data)

    except Exception:
        pass


def _port_is_available(port: int) -> bool:
    """Check if port is free at OS level."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def _should_auto_init() -> bool:
    """Check if current command needs auto-init.
    
    Returns True for commands that need a server connection.
    """
    # Get the command being executed
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    # Skip auto-init for commands that don't need a server
    skip_commands = {
        "config", "skills", "profile",
        "--help", "-h", "--version", "-v",
    }

    # If first arg is in skip list, don't auto-init
    if args and args[0] in skip_commands:
        return False

    # If no args, don't auto-init
    if not args:
        return False

    # For profile subcommands, only auto-init for set/create
    if args[0] == "profile" and len(args) > 1:
        profile_cmds = {"set", "create", "delete", "terminate"}
        if args[1] not in profile_cmds:
            return False

    return True


def _fork_default_profile(name: str, url: str, port: int, server_id: str) -> dict:
    """Create profile env by forking default profile settings."""
    # Start with defaults
    env_data = {
        "name": name,
        "url": url,
        "port": port,
        "mode": "isolated",
        "server_id": server_id,
    }

    # Fork from default profile if it exists
    if profile_exists("default"):
        default_env = load_profile_env("default")
        if default_env:
            # Inherit model/variant settings from default
            env_data["default_model"] = default_env.get("default_model")
            env_data["default_variant"] = default_env.get("default_variant")

    # Also check config for model/variant
    from .config import get_config_value
    if not env_data.get("default_model"):
        env_data["default_model"] = get_config_value("default_model")
    if not env_data.get("default_variant"):
        env_data["default_variant"] = get_config_value("default_variant")

    return env_data
