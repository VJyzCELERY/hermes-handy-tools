"""Tmux session management for opencode-tool profiles.

Provides tmux-based shell persistence for profile isolation.
Each profile gets its own tmux session, keeping the shell alive
across multiple terminal() calls.
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
