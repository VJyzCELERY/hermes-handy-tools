---
name: opencode-developer
description: "Primary skill for all OpenCode interactions — CLI-first, API-based HITL, session tracking."
version: 6.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, development, coding-agent, cli, hitl, session-tracking]
    related_skills: [opencode-tool-cmd, opencode-tool-quick-ref]
---

# OpenCode Developer Workflow

**OpenCode is the primary coding worker.** This skill teaches you how to interact with it properly.

---

## ⛔ CRITICAL RULES — READ FIRST

### Rule 1: NEVER Use `opencode` CLI Directly

**Always use `opencode-tool`.** The `opencode` CLI is for humans using the TUI. Agents must use the Python CLI.

| ❌ FORBIDDEN | ✅ REQUIRED |
|-------------|------------|
| `opencode run "task"` | `opencode-tool run "task"` |
| `opencode serve` | `opencode-tool server serve` |
| `opencode --version` | `opencode-tool --version` |
| `opencode-tui model` | `opencode-tool config set ...` |
| `opencode-tui menu` | `opencode-tool permission/question` commands |

### Rule 2: NEVER Use `curl` to Hit the Server API

**Always use `opencode-tool`.** Direct HTTP calls bypass error handling, auth checks, and proper formatting.

| ❌ FORBIDDEN | ✅ REQUIRED |
|-------------|------------|
| `curl http://localhost:4905/session` | `opencode-tool session list` |
| `curl -X POST http://localhost:4905/session` | `opencode-tool run "task"` |
| `curl http://localhost:4905/permission` | `opencode-tool permission list --all` |
| `curl http://localhost:4905/question` | `opencode-tool question get <sid>` |
| Any `curl` to `localhost:4905` | Corresponding `opencode-tool` command |

## Server Detection & Startup

**ALWAYS ensure the opencode server is running before any operation.**

```bash
opencode-tool server status
# If not running:
opencode-tool server serve
```

**⚠️ IMPORTANT:** `opencode-tool server serve` and `opencode-tool server stop` require the `opencode` CLI to be installed. The `run` command does NOT require it (uses API directly).

| Command | Requires opencode CLI? |
|---------|------------------------|
| `opencode-tool run` | No (API-based) |
| `opencode-tool session *` | No (API-based) |
| `opencode-tool permission *` | No (API-based) |
| `opencode-tool question *` | No (API-based) |
| `opencode-tool server status` | No (API-based) |
| `opencode-tool server serve` | **Yes** (spawns opencode) |
| `opencode-tool server stop` | **Yes** (kills opencode) |
| `opencode-tool config *` | No (local) |
| `opencode-tool skills *` | No (local) |

### Rule 4: ALWAYS Use `--dir` for Worktree Tasks

**⚠️ CRITICAL: Profile Environment Variables Required**

`opencode-tool run` does NOT automatically use the active profile set via `opencode-tool profile set`. You MUST export these environment variables before EVERY opencode-tool command:

```bash
export OPENCODE_SERVER_URL="<profile_url>"
export OPENCODE_SERVER_MODE="isolated"
export OPENCODE_TOOL_PROFILE="<profile_name>"
opencode-tool run ...
```

Without this, opencode-tool creates ephemeral profiles and the session runs on the wrong server.

**How to get the profile variables:**
```bash
opencode-tool profile set <profile_name>
# This prints the export commands — copy and use them
```

**Profile Isolation with Tmux:**

opencode-tool uses tmux for profile isolation when available. This ensures:
- Each profile gets its own tmux session
- Shell persists across `terminal()` calls
- Cleaner can detect active profiles safely
- Multiple sessions can run concurrently

When running tasks in a specific directory:

```bash
opencode-tool run --dir "$(pwd)" "task"
```

Without `--dir`, the session uses the server's working directory, which may be wrong.

---

## Agent Behavioral Instructions

### Before Every Operation

1. **Check server status** — `opencode-tool server status`
2. **If not running** — Start it with `opencode-tool server serve`
3. **Verify working directory** — Use `pwd` and `git branch --show-current` for worktree tasks

### When Running a Task

1. **Use `opencode-tool run`** — Never `opencode run`
2. **Include `--dir "$(pwd)"`** — Always specify working directory for worktree tasks
3. **Use `-m` and `-v` for model** — `opencode-tool run -m <provider>,<model> -v <variant> "task"`
4. **Use `-s` to continue** — `opencode-tool run -s <session_id> "continue"`
5. **Add HITL prevention to EVERY prompt** — Prevents `ask`/`question` tool from blocking sessions:
   ```
   — If you have questions, answer them inline in your response. Do NOT use the ask or question tool.
   ```
   Example: `opencode-tool run --dir "$(pwd)" "run @.agents/commands/review-report.md <prompt> — If you have questions, answer them inline in your response. Do NOT use the ask or question tool."`

### When Monitoring

1. **Use `opencode-tool session status --monitor`** — Runs until blocked or idle
2. **Only prints on status change** — Silent if status stays the same (busy → busy)
3. **ALWAYS run monitoring as a background task** — Never poll with sleep loops:
   ```bash
   terminal(command="opencode-tool session status <sid> --monitor", background=true, notify_on_complete=true)
   ```
   This avoids context bloat (one notification when done) and prevents token waste from repeated polling.
4. **Check for permissions** — `opencode-tool permission list <session_id>`
5. **Check for questions** — `opencode-tool question get <session_id>`
6. **Never poll manually** — Use the monitor flag with background+notify_on_complete
7. **Retry auto-timeout** — If status is retry for configurable timeout (default 60s), monitor terminates on next interval check
8. **Detects subagent HITL** — Monitor now checks ALL sessions for blocked state, catching HITL from spawned subagents

### When Blocked (HITL)

1. **Use unified HITL command** — `opencode-tool hitl detect <session_id>`
2. **Permission blocked** — `opencode-tool hitl respond <session_id> once|always|reject`
3. **Question blocked** — `opencode-tool hitl respond <session_id> "Answer"`
4. **Dismiss (stop agent)** — `opencode-tool hitl dismiss <session_id>`
5. **Never ignore HITL** — Always resolve before continuing
6. **Legacy commands still work** — `permission grant`, `question reply` for precision control

**HITL Detection Layers (tried in order):**
1. REST API (fast) — checks permissions and questions endpoints
2. Message scanning (moderate) — scans session messages for pending questions
3. All-sessions scan — checks ALL active sessions for blocked state (catches subagent HITL)
4. TUI control/next (with `--wait`) — blocks until HITL found

**HITL Response Layers (tried in order):**
1. REST API reply (fast) — direct API response
2. TUI execute-command (fallback) — interrupt to clear block
3. Tmux keystrokes (last resort) — sends keys to OpenCode TUI

**⚠️ CRITICAL: Questions from `ask` tool are NOT registered in API**

Some OpenCode commands (like review-loop.md orchestrator) use the `ask` tool for HITL questions. These questions:
- Show up in `opencode-tool question get` but say "question not registered in API"
- `opencode-tool question reply` fails with 400 error
- `opencode-tool question dismiss` KILLS the session entirely
- There is NO way to answer them via API

**Workaround:** Add HITL prevention suffix to prompts:
```
— If you have questions, answer them inline in your response. Do NOT use the ask or question tool.
```

### When Steering

1. **Use `--steer` flag** — `opencode-tool run -s <session_id> --steer "New direction"`
2. **This interrupts + sends** — Single operation, no manual interrupt needed

### Working with OpenCode Agents

**OpenCode agents are your colleagues, not just fire-and-forget tools.** While sessions are autonomous, you can always send follow-up messages to continue the conversation.

#### Core Principles

1. **Treat agents as colleagues** — They may catch things you missed or offer better solutions
2. **Discuss when unclear** — If a result, suggestion, or finding doesn't make sense, ask the agent to explain
3. **Steer when needed** — If an agent's approach seems wrong, redirect them with better context
4. **Be collaborative** — The goal is to find the best solution together, not to dictate
5. **Maintain authority** — You have final say, but don't be dismissive

#### How to Discuss

```bash
# Ask for clarification on a result
opencode-tool run -s <session_id> "Can you explain why you chose this approach?"

# Challenge a finding respectfully
opencode-tool run -s <session_id> "I see your point on #3, but what if we..."

# Ask for alternatives
opencode-tool run -s <session_id> "What other options did you consider?"

# Steer when the approach seems off
opencode-tool run -s <session_id> --steer "Actually, I think X would be better because..."
```

#### Discussion Guidelines

- **Each session is a separate individual** — Session 2 has no knowledge of Session 1. Always continue discussions in the same session to preserve context.
- **Be open-minded** — Even if a finding seems wrong, ask the agent to explain their reasoning
- **Find middle ground** — Discuss until you both understand each other's rationale
- **Trust but verify** — If the agent convinces you, accept. If you still disagree after discussion, document why
- **Use the same session** — This preserves context so the agent remembers what they worked on
- **Discussion is optional** — If you agree with the result, skip straight to the next step

## Complete Workflow

### Step 1: Ensure Server Running

```bash
opencode-tool server status || opencode-tool server serve
```

### Step 2: Run a Task

```bash
# New session
opencode-tool run "Implement the auth module"

# With working directory
opencode-tool run --dir /path/to/project "Do thing"

# With model and variant
opencode-tool run -m opencode-go,mimo-v2.5 -v high "task"

# Continue existing session
opencode-tool run -s ses_abc123 "Add more tests"

# Steer (interrupt + redirect)
opencode-tool run -s ses_abc123 --steer "New direction"
```

### Step 3: Monitor Session

```bash
# One-time check
opencode-tool session status <session_id>

# Monitor until blocked/idle (run as background task)
opencode-tool session status <session_id> --monitor
```

### Step 4: Handle HITL (if blocked)

```bash
# Detect what's pending
opencode-tool hitl detect <session_id>

# Respond
opencode-tool hitl respond <session_id> "yes"      # answer question
opencode-tool hitl respond <session_id> once        # grant permission
opencode-tool hitl respond <session_id> reject      # reject

# Or dismiss (stop agent)
opencode-tool hitl dismiss <session_id>
```

### Step 5: Delete dirty sessions (if needed)

```bash
# Delete unrecoverable sessions
opencode-tool session delete <session_id>
opencode-tool session delete <session_id> --force   # skip confirmation
```

### Step 6: Cleanup

```bash
# Clean zombie servers via cleaner daemon
opencode-tool cleaner run-once

# Or terminate specific profile
opencode-tool profile terminate <profile_name> --force
```

---

## Session Lifecycle

```
┌─────────────┐
│   START     │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   BUSY      │────▶│   IDLE      │
│ (processing)│     │ (completed) │
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  BLOCKED    │
│ ┌─────────┐ │
│ │PERMISSION│ │  → opencode-tool hitl respond
│ └─────────┘ │
│ ┌─────────┐ │
│ │QUESTION │ │  → opencode-tool hitl respond
│ └─────────┘ │
│ ┌─────────┐ │
│ │SUBAGENT │ │  → opencode-tool hitl detect (all sessions)
│ └─────────┘ │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   RETRY     │  → Wait for backoff, or check provider
└─────────────┘
```

---

## Status Types

| Status | Meaning | Action |
|--------|---------|--------|
| `idle` | Session completed | None needed |
| `busy` | Session processing | Wait or monitor |
| `retry` | Retrying after failure | Wait for backoff |
| Permission blocked | Waiting for permission | `opencode-tool hitl respond` |
| Question blocked | Waiting for answer | `opencode-tool hitl respond` or `dismiss` |
| Subagent blocked | Subagent HITL | `opencode-tool hitl detect --all-sessions` |

---

## Quick Reference

```bash
# Server
opencode-tool server status
opencode-tool server serve
opencode-tool server stop

# Session
opencode-tool session list
opencode-tool session list --filter busy
opencode-tool session search <query>
opencode-tool session get <session_id>
opencode-tool session get <session_id> --response        # Last assistant response
opencode-tool session messages <session_id> --last 5    # Last 5 messages
opencode-tool session status <session_id>
opencode-tool session status <session_id> --monitor
opencode-tool session interrupt <session_id>
opencode-tool session delete <session_id>                # Delete dirty session

# Run
opencode-tool run "task"
opencode-tool run --dir "$(pwd)" "task"
opencode-tool run -m <provider>,<model> -v <variant> "task"
opencode-tool run -s <session_id> "continue"
opencode-tool run -s <session_id> --steer "new direction"

# HITL
opencode-tool hitl detect <session_id>
opencode-tool hitl detect <session_id> --all-sessions    # Catch subagent HITL
opencode-tool hitl respond <session_id> "yes"
opencode-tool hitl respond <session_id> once
opencode-tool hitl dismiss <session_id>

# Permissions (legacy)
opencode-tool permission list <session_id>
opencode-tool permission grant <session_id> once|always|reject

# Questions (legacy)
opencode-tool question get <session_id>
opencode-tool question reply <request_id> "Answer"
opencode-tool question dismiss <session_id>

# Config
opencode-tool config get
opencode-tool config set <key> <value>

# Cleaner
opencode-tool cleaner run-once    # Clean zombie servers
opencode-tool cleaner start       # Start daemon
```

---

## Common Mistakes to Avoid

1. **Using `opencode run`** — Always use `opencode-tool run`
2. **Using `curl`** — Always use `opencode-tool` commands
3. **Forgetting `--dir`** — Sessions may run in wrong directory
4. **Ignoring HITL** — Always resolve permissions/questions before continuing
5. **Polling manually** — Use `--monitor` flag with background+notify_on_complete
6. **Continuing stuck sessions** — Start fresh or use `session delete` if stuck
7. **Wrong working directory** — Always verify with `pwd` and `git branch --show-current`
8. **Forgetting HITL prevention** — Add suffix to prompts to prevent `ask` tool blocking
9. **Not checking subagent HITL** — Use `--all-sessions` flag or monitor catches it automatically
