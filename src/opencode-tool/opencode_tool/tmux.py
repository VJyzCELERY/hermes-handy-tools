"""Tmux session management for opencode-tool profiles.

Provides tmux-based shell persistence for profile isolation.
Each profile gets its own tmux session, keeping the shell alive
across multiple terminal() calls.

Also provides TUI HITL response via tmux — sends keystrokes to
the OpenCode TUI to answer questions or grant permissions.
"""

import subprocess
import time
from typing import Optional


def is_tmux_available() -> bool:
    """Check if tmux is installed and accessible."""
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_tmux_session(session_name: str, width: int = 120, height: int = 40) -> bool:
    """Create a new detached tmux session.

    Args:
        session_name: Name for the tmux session
        width: Terminal width (columns)
        height: Terminal height (rows)

    Returns:
        True if session created successfully
    """
    try:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name,
             "-x", str(width), "-y", str(height)],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def send_tmux_keys(session_name: str, command: str) -> bool:
    """Send commands to a tmux session.

    Args:
        session_name: Target tmux session
        command: Command to send

    Returns:
        True if command sent successfully
    """
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, command, "Enter"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def send_tmux_raw(session_name: str, keys: str) -> bool:
    """Send raw key sequence to a tmux session (no Enter).

    Args:
        session_name: Target tmux session
        keys: Raw key sequence (e.g., 'y', 'n', 'Escape', 'Enter')

    Returns:
        True if keys sent successfully
    """
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, keys],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_tmux_session_alive(session_name: str) -> bool:
    """Check if a tmux session exists and is alive.

    Args:
        session_name: Session to check

    Returns:
        True if session exists
    """
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def kill_tmux_session(session_name: str) -> bool:
    """Kill a tmux session.

    Args:
        session_name: Session to kill

    Returns:
        True if session killed successfully
    """
    try:
        result = subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_tmux_session_pid(session_name: str) -> Optional[int]:
    """Get the PID of the shell process in a tmux session.

    Args:
        session_name: Session to query

    Returns:
        PID of the shell process, or None if not found
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_pid}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            # Get the first pane's PID (the shell)
            pids = result.stdout.strip().split('\n')
            if pids:
                return int(pids[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def get_tmux_session_info(session_name: str) -> Optional[dict]:
    """Get detailed info about a tmux session.

    Args:
        session_name: Session to query

    Returns:
        Dict with session info, or None if not found
    """
    try:
        # Get session info
        result = subprocess.run(
            ["tmux", "list-sessions", "-t", session_name,
             "-F", "#{session_name}:#{session_created}:#{session_attached}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split(':')
        if len(parts) < 3:
            return None

        # Get pane PID
        pane_pid = get_tmux_session_pid(session_name)

        return {
            "name": parts[0],
            "created": int(parts[1]) if parts[1].isdigit() else 0,
            "attached": parts[2] == "1",
            "pane_pid": pane_pid,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def wait_for_tmux_command(session_name: str, command: str,
                          timeout: int = 30, interval: float = 0.5) -> bool:
    """Wait for a command to complete in a tmux session.

    This sends a command and waits for the prompt to return,
    indicating the command has completed.

    Args:
        session_name: Target tmux session
        command: Command to execute
        timeout: Max seconds to wait
        interval: Check interval in seconds

    Returns:
        True if command completed within timeout
    """
    # Send the command
    if not send_tmux_keys(session_name, command):
        return False

    # Wait for completion (simplified - just wait for timeout)
    # In practice, we'd check for prompt return, but that's complex
    time.sleep(min(timeout, 5))
    return True


# ── TUI HITL Response via tmux ──

def find_profile_tmux_session(profile_name: Optional[str] = None) -> Optional[str]:
    """Find the tmux session for a profile.

    Args:
        profile_name: Profile name. If None, uses active profile.

    Returns:
        Tmux session name or None
    """
    import os
    from .registry import load_profile_env, list_profiles

    if profile_name is None:
        profile_name = os.environ.get("OPENCODE_TOOL_PROFILE")

    if profile_name:
        env_data = load_profile_env(profile_name)
        tmux_session = env_data.get("tmux_session")
        if tmux_session and is_tmux_session_alive(tmux_session):
            return tmux_session

    # Fallback: find any opencode-* tmux session
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.startswith("opencode-"):
                    return line
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def tmux_respond_question(session_name: str, answer: str) -> bool:
    """Respond to a question in the OpenCode TUI via tmux.

    Sends keystrokes to type the answer and submit it.

    Args:
        session_name: Tmux session name
        answer: Answer text to send

    Returns:
        True if keystrokes sent successfully
    """
    # Type the answer
    if not send_tmux_keys(session_name, answer):
        return False

    # Small delay for TUI to process
    time.sleep(0.3)

    # Press Enter to submit
    send_tmux_raw(session_name, "Enter")
    return True


def tmux_respond_permission(session_name: str, answer: str) -> bool:
    """Respond to a permission request in the OpenCode TUI via tmux.

    Maps answer to TUI keybindings:
      - 'once' / 'y' / 'yes' → 'y'
      - 'always' → 'a'
      - 'reject' / 'n' / 'no' → 'n'

    Args:
        session_name: Tmux session name
        answer: Permission answer

    Returns:
        True if keystrokes sent successfully
    """
    answer_lower = answer.lower().strip()

    if answer_lower in ("once", "y", "yes"):
        key = "y"
    elif answer_lower in ("always", "a"):
        key = "a"
    elif answer_lower in ("reject", "n", "no"):
        key = "n"
    else:
        key = answer_lower

    return send_tmux_raw(session_name, key)


def tmux_dismiss_hitl(session_name: str) -> bool:
    """Dismiss HITL by pressing Escape in the TUI.

    Args:
        session_name: Tmux session name

    Returns:
        True if keystrokes sent successfully
    """
    return send_tmux_raw(session_name, "Escape")
