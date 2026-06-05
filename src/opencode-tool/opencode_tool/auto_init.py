"""Auto-initialization for opencode-tool profiles.

Simplified: always uses the default profile.
No ephemeral profile creation — profiles are managed explicitly via `profile set`.

Profile resolution:
1. OPENCODE_TOOL_PROFILE env var (if set)
2. Default profile (always)
"""

import os
import sys
from typing import Optional

from .registry import (
    create_profile_dir,
    load_profile_env,
    profile_exists,
    register_server,
    save_profile_env,
    OPENTOOL_DIR,
)


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
    """Set active profile in file-based persistence."""
    OPENTOOL_DIR.mkdir(parents=True, exist_ok=True)
    profile_file = _get_active_profile_file(pid)
    profile_file.write_text(profile_name)


def ensure_profile() -> Optional[str]:
    """Ensure a profile exists for this session.

    Always returns "default" — no ephemeral profile creation.
    Creates default profile if it doesn't exist.
    """
    # Ensure default profile exists
    if not profile_exists("default"):
        create_default_profile()

    # Already have active profile via env var — use it
    profile = get_active_profile()
    if profile:
        return profile

    # Check if we should auto-init (skip for non-server commands)
    if not _should_auto_init():
        return None

    # Always use default profile
    return "default"


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
        from urllib.parse import urlparse
        parsed = urlparse(url)
        port = parsed.port or 4905

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


def _get_active_profile_file(pid: Optional[int] = None):
    """Get active profile file for given PID (or current shell PID)."""
    if pid is None:
        pid = os.getppid()  # Parent PID (the shell)
    return OPENTOOL_DIR / f"active-profile-{pid}"


ACTIVE_PROFILE_FILE = None  # Computed per-call
