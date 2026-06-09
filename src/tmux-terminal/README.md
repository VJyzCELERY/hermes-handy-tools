# tmux_terminal

A custom Hermes Agent tool that runs commands in ephemeral tmux sessions.

## Why

The built-in `terminal()` tool executes commands via subprocess. `tmux_terminal()` wraps each command in a tmux session, giving it a proper TTY environment — colors, interactive programs, and full terminal capabilities work naturally.

Key differences from `terminal()`:
- **Full TTY** — tmux provides a real terminal, so ncurses apps, colored output, and interactive CLIs work correctly
- **No pipe bottleneck** — `terminal()` pipes output through `subprocess.PIPE`, making OpenCode 10-30x slower. tmux_terminal uses a real PTY.
- **Hermes env inheritance** — automatically forwards all Hermes environment variables (session state, profile .env vars, `HERMES_*` prefixed vars, `PYTHONPATH`, etc.) into the tmux session
- **Orphan cleanup** — detects and kills stale `hermes-*` tmux sessions from interrupted Hermes/subagent processes
- **Session tracking** — logs every tool call with session ID, command, timestamp, and status for debugging
- **Ephemeral** — session created and destroyed per call, no state leaks
- **No polling** — background mode uses `notify_on_complete` so Hermes tells you when it's done

## Install

### Option 1: Manual copy

```bash
cp src/tmux-terminal/tmux_terminal.py ~/.hermes/hermes-agent/tools/
```

### Option 2: With the project's install script (if available)

```bash
cd hermes-handy-tools
uv run python -m install-tools
```

After copying, run `/reset` or restart Hermes. The tool appears as `tmux_terminal` under the `terminal` toolset.

### Verify installation

```bash
# Check syntax
python3 -m py_compile ~/.hermes/hermes-agent/tools/tmux_terminal.py

# Check registration (AST scan)
python3 -c "
import ast
from pathlib import Path
tool = Path('~/.hermes/hermes-agent/tools/tmux_terminal.py').expanduser()
tree = ast.parse(tool.read_text())
found = any(
    isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
    and isinstance(s.value.func, ast.Attribute)
    and s.value.func.attr == 'register'
    for s in tree.body
)
print(f'registry.register() at top level: {found}')
"
```

### Requirements

- `tmux` must be installed and on PATH
- Python 3.11+

## Usage

### Foreground (blocks until done)

```python
tmux_terminal(command="ls -la /tmp")
tmux_terminal(command="echo 'hello world'", workdir="/home/user")
tmux_terminal(command="long-running-script.sh", timeout=1200)
```

### Background (notify when done)

```python
tmux_terminal(command="make test", background=True, notify_on_complete=True)
# → returns session_id + pid
# → Hermes notifies when the process exits
```

### OpenCode (recommended over terminal())

```python
# ✅ Use tmux_terminal for OpenCode — real PTY, no pipe bottleneck
tmux_terminal(
    command='opencode run "run @.agents/commands/review-loop.md ..." --dir <worktree> --format json',
    timeout=600
)

# ❌ terminal() pipes output — makes OpenCode 10-30x slower
terminal(
    command='opencode run "..." --dir <worktree> --format json',
    background=True, notify_on_complete=True, timeout=600
)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | string | *required* | Shell command to execute |
| `timeout` | integer | 600 | Max seconds to wait (foreground) |
| `workdir` | string | cwd | Working directory |
| `background` | boolean | false | Run via Hermes process tracking |
| `notify_on_complete` | boolean | false | Notify on exit (background mode) |

## Environment Inheritance

`tmux_terminal` automatically forwards the Hermes environment into each tmux session. This includes:

- **All `HERMES_*` vars** — session state, tool config, gateway info
- **Profile-specific env vars** — anything loaded from a profile's `.env` file
- **Known extras** — `PYTHONPATH`, `OBSIDIAN_VAULT_PATH`, `AUXILIARY_VISION_PROVIDER`

This ensures commands inside tmux see the same environment as `terminal()` would, regardless of which Hermes profile is active.

**How it works:** The tool writes env vars to a temporary bash file, then sources it inside the tmux session via `source /path/to/hermes-env-xxxxx.sh`.

## Orphan Detection

Every time `tmux_terminal` is called, it scans for stale `hermes-*` tmux sessions and kills them. This handles:

- **Hermes interrupted** — WSL shutdown, crash, OOM kill leaves tmux sessions running
- **Subagent killed** — mid-command termination leaves orphaned sessions
- **Wrapper script died** — tmux session survived but the wrapper exited

**How it works:**
1. Lists all live `hermes-*` tmux sessions via `tmux list-sessions`
2. Cross-references with the tracking file (`~/.hermes/logs/tmux-terminal-sessions.tsv`)
3. Any session in tmux but NOT tracked as `running` is an orphan → killed
4. Orphaned temp output files (`/tmp/tmux-output-hermes-*`) are also cleaned up

## Session Tracking

Every tool call is logged to `~/.hermes/logs/tmux-terminal-sessions.tsv`:

```
session_id    command    start_time    status    workdir    pid
hermes-abc12345    echo hello    1780997862.4    completed    /path/to/workdir
```

**Session naming:** `hermes-{tool_call_id[:8]}` — derived from the Hermes tool call ID so each tmux session traces back to the exact tool call that created it. Falls back to `task_id` or random UUID if context is unavailable.

**Status values:** `running` → `completed` | `failed` | `timeout` | `orphaned`

**Audit log** at `~/.hermes/logs/tmux-terminal.log`:
```
[2026-06-09T09:37:42.400066+00:00] [hermes-112036e5] [start] cmd=echo hello workdir=/path
[2026-06-09T09:37:42.720833+00:00] [hermes-112036e5] [completed]
[2026-06-09T09:37:35.615700+00:00] [hermes-orphan-test] [orphan_kill] detected at cleanup
```

**Cleanup:** Completed/failed entries older than 1 hour are automatically pruned from the tracking file.

## How it works

1. Writes the command to a temp file (avoids all shell quoting issues)
2. Writes Hermes env vars to a sourceable bash file
3. Creates a tmux session with 200×50 terminal dimensions
4. Sources the env file inside the tmux session (inherits Hermes environment)
5. Sends the command via `tmux send-keys` — tmux's shell interprets it normally
6. Wraps the command with output capture (`> file 2>&1`) and a completion signal (`tmux wait-for -S`)
7. Blocks on `tmux wait-for` until the signal fires
8. Reads the output file, extracts exit code from `__HERMES_EXIT:N` marker
9. Kills the tmux session and cleans up temp files

Background mode delegates the wrapper script to Hermes' `process_registry.spawn_local()`, so when the script exits (command done), Hermes detects it and fires the notification.
