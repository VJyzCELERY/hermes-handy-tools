#!/usr/bin/env python3
"""
Tmux Terminal — run commands in ephemeral tmux sessions.

Mimics the built-in terminal() tool but executes inside a proper tmux
environment. Commands get full TTY support (colors, interactive programs,
terminal capabilities) and stdout is captured via file redirect rather
than tmux capture-pane.

Ephemeral: each call creates a tmux session, runs the command, captures
output, and destroys the session.

Foreground mode: blocks until the command finishes, returns output.
Background mode: delegates to Hermes process_registry — when the command
finishes, the process exits and Hermes notifies via notify_on_complete.
No polling required.
"""

import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool call ID resolution
# ---------------------------------------------------------------------------

def _resolve_session_id(kw: dict) -> str:
    """Resolve a tmux session ID from the tool call context.

    Priority:
    1. tool_call_id from Hermes ContextVar (unique per tool call)
    2. task_id from kw (session-level identifier)
    3. Random UUID fallback (for tests / outside Hermes)

    Format: hermes-{id[:8]}  (tmux session names must be short)
    """
    # Try ContextVar first (set by Hermes during tool dispatch)
    try:
        from tools.approval import _approval_tool_call_id
        tc_id = _approval_tool_call_id.get()
        if tc_id:
            return f"hermes-{tc_id[:8]}"
    except (ImportError, LookupError):
        pass

    # Fall back to task_id from kwargs
    task_id = kw.get("task_id") or ""
    if task_id:
        return f"hermes-{task_id[:8]}"

    # Last resort: random UUID
    return f"hermes-{uuid.uuid4().hex[:8]}"

# ---------------------------------------------------------------------------
# Session tracking & orphan detection
# ---------------------------------------------------------------------------

# Tracking file: records every tmux session this tool creates.
# Format per line: session_id\tcommand\tstart_time\tstatus\tworkdir\tpid
# Status: running | completed | failed | orphaned | timeout
_TRACKING_DIR = Path.home() / ".hermes" / "logs"
_TRACKING_FILE = _TRACKING_DIR / "tmux-terminal-sessions.tsv"
_LOG_FILE = _TRACKING_DIR / "tmux-terminal.log"


def _ensure_tracking_dir() -> None:
    """Create the tracking directory if it doesn't exist."""
    _TRACKING_DIR.mkdir(parents=True, exist_ok=True)


def _log_event(session_id: str, action: str, details: str = "") -> None:
    """Append a timestamped log entry to the log file."""
    _ensure_tracking_dir()
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{session_id}] [{action}] {details}\n"
    try:
        with open(_LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass  # best-effort logging


def _track_start(session_id: str, command: str, workdir: str) -> None:
    """Record a tmux session as running in the tracking file."""
    _ensure_tracking_dir()
    _log_event(session_id, "start", f"cmd={command[:200]} workdir={workdir}")
    try:
        with open(_TRACKING_FILE, "a") as f:
            f.write(f"{session_id}\t{command[:500]}\t{time.time()}\trunning\t{workdir}\t\n")
    except Exception:
        pass


def _track_update(session_id: str, status: str, pid: str = "") -> None:
    """Update the status of a tracked session."""
    _log_event(session_id, status)
    if not _TRACKING_FILE.exists():
        return
    try:
        lines = _TRACKING_FILE.read_text().splitlines()
        updated = []
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 6 and parts[0] == session_id:
                parts[3] = status
                if pid:
                    parts[5] = pid
                updated.append("\t".join(parts))
            else:
                updated.append(line)
        _TRACKING_FILE.write_text("\n".join(updated) + "\n")
    except Exception:
        pass


def _cleanup_orphans() -> list[str]:
    """Find and kill orphaned hermes-* tmux sessions.

    An orphan is a tmux session matching 'hermes-*' that is NOT in the
    tracking file as 'running'. This happens when:
    - Hermes was interrupted (WSL shutdown, crash, OOM kill)
    - A subagent was killed mid-command
    - The wrapper script died but the tmux session survived

    Returns list of killed session IDs.
    """
    _ensure_tracking_dir()

    # Get all live hermes-* tmux sessions
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5,
        )
        live_sessions = set()
        for line in result.stdout.splitlines():
            name = line.strip()
            if name.startswith("hermes-"):
                live_sessions.add(name)
    except Exception:
        return []

    if not live_sessions:
        return []

    # Read tracking file to find which sessions are "running"
    running_sessions = set()
    if _TRACKING_FILE.exists():
        try:
            for line in _TRACKING_FILE.read_text().splitlines():
                parts = line.split("\t")
                if len(parts) >= 4 and parts[3] == "running":
                    running_sessions.add(parts[0])
        except Exception:
            pass

    # Orphans = live sessions that are NOT tracked as running
    orphans = live_sessions - running_sessions

    killed = []
    for orphan in orphans:
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", orphan],
                capture_output=True, timeout=5,
            )
            _log_event(orphan, "orphan_kill", f"detected at cleanup, not in tracking file")
            killed.append(orphan)
        except Exception:
            pass

    # Also clean up orphaned temp output files
    try:
        import glob
        for f in glob.glob("/tmp/tmux-output-hermes-*"):
            # Check if the session part is an orphan
            session_name = f.replace("/tmp/tmux-output-", "")
            if session_name in orphans:
                try:
                    os.unlink(f)
                except Exception:
                    pass
    except Exception:
        pass

    # Also clean up orphaned tracking entries for sessions that no longer exist
    if _TRACKING_FILE.exists():
        try:
            lines = _TRACKING_FILE.read_text().splitlines()
            cleaned = []
            for line in lines:
                parts = line.split("\t")
                if len(parts) >= 4:
                    sid = parts[0]
                    status = parts[3]
                    # Remove completed/failed entries older than 1 hour
                    if status in ("completed", "failed", "orphaned", "timeout"):
                        try:
                            start_time = float(parts[2])
                            if time.time() - start_time > 3600:
                                continue  # skip old entries
                        except (ValueError, IndexError):
                            pass
                cleaned.append(line)
            _TRACKING_FILE.write_text("\n".join(cleaned) + "\n")
        except Exception:
            pass

    return killed

# ---------------------------------------------------------------------------
# Hermes environment inheritance
# ---------------------------------------------------------------------------

# Env vars that Hermes injects into the terminal() tool's environment.
# tmux_terminal must forward these so commands inside tmux see the same
# environment as terminal() would.
_HERMES_ENV_PREFIX = "HERMES_"
_HERMES_EXTRA_VARS = (
    "PYTHONPATH",
    "OBSIDIAN_VAULT_PATH",
    "AUXILIARY_VISION_PROVIDER",
    "TERMINAL_CWD",
)

# Basic system vars that tmux/shell set themselves — do NOT forward these
# because they'd conflict with the tmux session's own values.
_SYSTEM_VARS_TO_SKIP = frozenset({
    "HOME", "USER", "SHELL", "LOGNAME", "LANG", "LC_ALL", "TERM",
    "PWD", "OLDPWD", "SHLVL", "_", "HOSTNAME", "HOSTTYPE", "MACHTYPE",
    "OSTYPE", "PPID", "BASHOPTS", "BASH_VERSION", "EUID", "GROUPS",
    "HOME", "HOSTNAME", "IFS", "LINENO", "MAILCHECK", "PIPESTATUS",
    "PPID", "RANDOM", "SECONDS", "SHELLOPTS", "BASH_VERSINFO",
    "BASH", "BASH_SOURCE", "BASH_LINENO", "FUNCNAME", "DIRSTACK",
    "PIPESTATUS", "MODULEPATH", "MODULESHOME", "LMOD_CMD",
})


def _collect_hermes_env() -> dict[str, str]:
    """Collect Hermes-injected env vars from the current process.

    Returns a dict of env vars that should be exported inside the tmux
    session so commands see the same environment as terminal() provides.

    Collects:
    - All HERMES_* prefixed vars (session state, tool config, etc.)
    - Profile-specific env vars (from .env files loaded by the profile)
    - Extra known vars (PYTHONPATH, OBSIDIAN_VAULT_PATH, etc.)

    Profile env vars are forwarded by collecting everything that's NOT
    a basic system/shell var. This ensures any .env a profile loads
    gets passed through to the tmux session.
    """
    collected = {}
    for key, val in os.environ.items():
        # Always forward HERMES_* vars
        if key.startswith(_HERMES_ENV_PREFIX):
            collected[key] = val
        # Forward known extra vars
        elif key in _HERMES_EXTRA_VARS:
            collected[key] = val
        # Forward anything that's not a basic system var
        # This captures profile-specific .env vars (API keys, custom config, etc.)
        elif key not in _SYSTEM_VARS_TO_SKIP and not key.startswith("_"):
            # Skip internal bash vars (FUNCNAME, BASH_*, etc.)
            if not key.startswith("BASH_") and key not in (
                "FUNCNAME", "LINENO", "BASH_LINENO", "BASH_SOURCE",
                "BASH_REMATCH", "FUNCNEST", "PIPESTATUS", "RANDOM",
                "SECONDS", "LINENO", "BASHOPTS", "SHELLOPTS",
            ):
                collected[key] = val
    return collected


def _build_env_exports(env: dict[str, str]) -> str:
    """Write Hermes env vars to a sourceable bash file.

    Returns the path to the file. The file contains export statements
    that can be sourced inside a tmux session to inherit the environment.
    """
    if not env:
        # Write a no-op file so the path is always valid
        fd, path = tempfile.mkstemp(prefix="hermes-env-", suffix=".sh")
        os.write(fd, b"# (no hermes env vars to export)\n")
        os.close(fd)
        return path

    lines = ["#!/bin/bash", "# Auto-generated Hermes env exports"]
    for key in sorted(env):
        val = env[key]
        if "'" in val:
            escaped = val.replace("'", "\\'")
            lines.append(f"export {key}=$'{escaped}'")
        else:
            lines.append(f"export {key}='{val}'")

    fd, path = tempfile.mkstemp(prefix="hermes-env-", suffix=".sh")
    os.write(fd, "\n".join(lines).encode())
    os.write(fd, b"\n")
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Requirements check
# ---------------------------------------------------------------------------

def check_requirements() -> bool:
    """Return True if tmux is available on PATH."""
    try:
        return subprocess.run(
            ["which", "tmux"], capture_output=True, timeout=5
        ).returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

# The wrapper script template. Runs inside bash — creates a tmux session,
# sends the user command with output capture + completion signal, waits,
# outputs the result to stdout (so the caller captures it), and cleans up.
#
# Key design: the user command is read from a temp file (no quoting issues)
# and sent to tmux via send-keys. The tmux shell interprets it normally.
# $? is escaped as \$? so the wrapper's bash doesn't expand it — tmux's
# shell does when the command finishes.

WRAPPER_SCRIPT = r"""#!/bin/bash
set -euo pipefail

SESSION="{session}"
OUTFILE="{outfile}"
CWD="{cwd}"
COMMAND=$(cat {cmd_file})
ENVFILE="{env_file}"

# Create tmux session with large terminal dimensions
tmux new-session -d -s "$SESSION" -x 200 -y 50 -c "$CWD"

# Inherit Hermes environment inside the tmux session.
# Source the env file (avoids send-keys buffer limits for many vars).
tmux send-keys -t "$SESSION" "source $ENVFILE" Enter

# Small delay to let env settle, then send the actual command
sleep 0.2

# Send command: capture stdout+stderr to file, record exit code, signal done.
# \\$? is literal — expanded by tmux's shell, not the wrapper's.
tmux send-keys -t "$SESSION" \
    "($COMMAND) > $OUTFILE 2>&1; echo __HERMES_EXIT:\\$? >> $OUTFILE; tmux wait-for -S $SESSION" \
    Enter

# Block until the tmux session signals completion
tmux wait-for "$SESSION"

# Output the captured result (caller reads this from stdout)
cat "$OUTFILE"

# Cleanup
tmux kill-session -t "$SESSION" 2>/dev/null || true
rm -f "$OUTFILE" "{cmd_file}" "$ENVFILE"
"""


def _write_file(content: str, prefix: str, suffix: str) -> str:
    """Write content to a temp file, return the path."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.write(fd, content.encode())
    os.close(fd)
    return path


def _run_tmux_command(
    command: str,
    timeout: int = 600,
    workdir: str | None = None,
    kw: dict | None = None,
) -> str:
    """
    Run a command in an ephemeral tmux session (foreground).

    Returns JSON with output, exit_code, and optional error.
    """
    session = _resolve_session_id(kw or {})
    outfile = f"/tmp/tmux-output-{session}"
    cwd = workdir or os.getcwd()

    # Track this session
    _track_start(session, command, cwd)

    # Write command to a temp file (avoids all quoting issues)
    cmd_file = _write_file(command, prefix="hermes-tmux-cmd-", suffix=".sh")

    # Write Hermes env vars to a sourceable file
    hermes_env = _collect_hermes_env()
    env_file = _build_env_exports(hermes_env)

    # Write the wrapper script
    script = WRAPPER_SCRIPT.format(
        session=session,
        outfile=outfile,
        cwd=cwd,
        cmd_file=cmd_file,
        env_file=env_file,
    )
    script_file = _write_file(script, prefix="hermes-tmux-wrap-", suffix=".sh")
    os.chmod(script_file, 0o755)

    try:
        result = subprocess.run(
            ["bash", script_file],
            capture_output=True,
            text=True,
            timeout=timeout + 10,  # extra headroom for tmux startup
        )

        stdout = result.stdout
        exit_code = -1
        error = None

        if "__HERMES_EXIT:" in stdout:
            parts = stdout.rsplit("__HERMES_EXIT:", 1)
            output = parts[0].rstrip("\n")
            try:
                exit_code = int(parts[1].strip())
            except ValueError:
                pass
            _track_update(session, "completed")
        else:
            output = stdout.rstrip("\n")
            if result.returncode != 0 and not output:
                error = result.stderr.rstrip("\n") if result.stderr else "Command failed"
            _track_update(session, "failed" if result.returncode != 0 else "completed")

        return json.dumps({
            "output": output,
            "exit_code": exit_code,
            "error": error,
        }, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        # Kill any lingering tmux session
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True, timeout=5,
        )
        _track_update(session, "timeout")
        return json.dumps({
            "output": "",
            "exit_code": -1,
            "error": f"Timed out after {timeout}s",
        })
    except Exception as e:
        _track_update(session, "failed")
        return json.dumps({
            "output": "",
            "exit_code": -1,
            "error": str(e),
        })
    finally:
        # Cleanup temp files (wrapper may have already cleaned cmd_file)
        for f in [script_file, cmd_file, env_file]:
            try:
                Path(f).unlink(missing_ok=True)
            except Exception:
                pass


def _build_bg_command(
    command: str,
    workdir: str | None = None,
    kw: dict | None = None,
) -> str:
    """
    Build a self-contained bash command string for background execution.

    The command creates a tmux session, runs the user command, captures
    output, and exits. When this shell process exits, Hermes detects it
    and fires notify_on_complete.
    """
    session = _resolve_session_id(kw or {})
    outfile = f"/tmp/tmux-output-{session}"
    cwd = workdir or os.getcwd()

    # Write command to a temp file
    cmd_file = _write_file(command, prefix="hermes-tmux-cmd-", suffix=".sh")

    # Write Hermes env vars to a sourceable file
    hermes_env = _collect_hermes_env()
    env_file = _build_env_exports(hermes_env)

    script = WRAPPER_SCRIPT.format(
        session=session,
        outfile=outfile,
        cwd=cwd,
        cmd_file=cmd_file,
        env_file=env_file,
    )
    script_file = _write_file(script, prefix="hermes-tmux-wrap-", suffix=".sh")
    os.chmod(script_file, 0o755)

    return f"bash {shlex.quote(script_file)}"


# ---------------------------------------------------------------------------
# Hermes tool registration
# ---------------------------------------------------------------------------

TMUX_TERMINAL_DESCRIPTION = (
    "Execute a command in an ephemeral tmux session. Commands run in a full "
    "terminal environment with proper TTY support (colors, interactive programs, "
    "terminal capabilities). Returns stdout from the command. The tmux session is "
    "created and destroyed per call. Use background=true + notify_on_complete=true "
    "for long-running commands to avoid polling."
)

TMUX_TERMINAL_SCHEMA = {
    "name": "tmux_terminal",
    "description": TMUX_TERMINAL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute in the tmux session",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Max seconds to wait (default: 600). Returns INSTANTLY when "
                    "command finishes — set high for long tasks."
                ),
                "minimum": 1,
            },
            "workdir": {
                "type": "string",
                "description": (
                    "Working directory for this command (absolute path). "
                    "Defaults to the session working directory."
                ),
            },
            "background": {
                "type": "boolean",
                "description": (
                    "Run in background with Hermes process tracking. When the tmux "
                    "command finishes, the process exits and Hermes detects it. "
                    "Almost always pair with notify_on_complete=true."
                ),
                "default": False,
            },
            "notify_on_complete": {
                "type": "boolean",
                "description": (
                    "When true and background=true, you'll be notified exactly once "
                    "when the process finishes."
                ),
                "default": False,
            },
        },
        "required": ["command"],
    },
}


def _handle_tmux_terminal(args, **kw):
    """Dispatch handler for the tmux_terminal tool."""
    # Run orphan cleanup on every call (cheap — just checks tmux list)
    orphans_killed = _cleanup_orphans()
    if orphans_killed:
        logger.info(f"Cleaned up {len(orphans_killed)} orphaned tmux sessions: {orphans_killed}")

    command = args.get("command")
    if not command:
        return json.dumps({"error": "No command provided", "output": "", "exit_code": -1})

    background = args.get("background", False)

    if background:
        # Background mode: build a command string and delegate to
        # process_registry. The wrapper script IS the process — when the
        # tmux command finishes, the script exits, and Hermes notifies.
        bg_cmd = _build_bg_command(
            command=command,
            workdir=args.get("workdir"),
            kw=kw,
        )
        # Track the background session (using a generated ID since the actual
        # tmux session ID is created inside the wrapper script)
        bg_session_id = f"hermes-bg-{uuid.uuid4().hex[:8]}"
        _track_start(bg_session_id, command, args.get("workdir") or os.getcwd())
        try:
            from tools.process_registry import process_registry
            session = process_registry.spawn_local(
                command=bg_cmd,
                cwd=args.get("workdir") or os.getcwd(),
                task_id=kw.get("task_id") or "",
            )
            result = {
                "output": "Background tmux session started",
                "session_id": session.id,
                "pid": session.pid,
                "exit_code": 0,
                "error": None,
            }
            _track_update(bg_session_id, "running", pid=str(session.pid))
            if not args.get("notify_on_complete", False):
                result["hint"] = (
                    "background=true without notify_on_complete=true means "
                    "this process runs SILENTLY — you will not be told when "
                    "it exits. Re-launch with notify_on_complete=true, or "
                    "call process(action='poll')/process(action='wait') to "
                    "check on it."
                )
            return json.dumps(result, ensure_ascii=False)
        except ImportError:
            # process_registry not available — fall back to foreground
            logger.warning("process_registry not available, falling back to foreground")
            _track_update(bg_session_id, "failed")
            return _run_tmux_command(
                command=command,
                timeout=args.get("timeout", 600),
                workdir=args.get("workdir"),
                kw=kw,
            )
    else:
        return _run_tmux_command(
            command=command,
            timeout=args.get("timeout", 600),
            workdir=args.get("workdir"),
            kw=kw,
        )


# ---------------------------------------------------------------------------
# Registration (must be at module top level for AST discovery)
# ---------------------------------------------------------------------------

from tools.registry import registry  # noqa: E402

registry.register(
    name="tmux_terminal",
    toolset="terminal",
    schema=TMUX_TERMINAL_SCHEMA,
    handler=_handle_tmux_terminal,
    check_fn=check_requirements,
    emoji="🖥️",
    max_result_size_chars=100_000,
)
