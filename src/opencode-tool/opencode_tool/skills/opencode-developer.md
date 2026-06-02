---
name: opencode-developer
description: "Primary skill for all OpenCode interactions — CLI-first, API-based HITL, session tracking."
version: 5.2.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, development, coding-agent, cli, hitl, session-tracking]
    related_skills: [opencode-tool, opencode-tool-commands]
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
| `curl http://localhost:4096/session` | `opencode-tool session list` |
| `curl -X POST http://localhost:4096/session` | `opencode-tool run "task"` |
| `curl http://localhost:4096/permission` | `opencode-tool permission list --all` |
| `curl http://localhost:4096/question` | `opencode-tool question get <sid>` |
| Any `curl` to `localhost:4096` | Corresponding `opencode-tool` command |

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

When running tasks in a specific directory:

```bash
opencode-tool run --dir "$(pwd)" "task"
```

Without `--dir`, the session uses the server's working directory, which may be wrong.

---

## Related Skills

| Skill | Purpose |
|-------|---------|
| `opencode-tool` | Quick reference for all CLI commands |
| `opencode-tool-commands` | Detailed CLI documentation with use cases |

```
┌──────────────────────────────────────────────────┐
│  opencode web --port 4096 (server daemon)         │
│  • Persistent background process                  │
│  • Processes sessions autonomously                │
│  • REST API for all interactions                  │
└──────────────┬───────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────┐        ┌──────────┐
│ CLI     │        │ API      │
│ run +   │        │ HITL     │
│ monitor │        │ resolve  │
└────┬────┘        └────┬─────┘
     │                  │
     ▼                  ▼
opencode-tool    opencode-tool
  run/session       permission/question
```

**Server URL:** `http://localhost:4096` (env: `OPENCODE_SERVER_URL`)

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

### When Monitoring

1. **Use `opencode-tool session status --monitor`** — Runs until blocked or idle
2. **Only prints on status change** — Silent if status stays the same (busy → busy)
3. **Check for permissions** — `opencode-tool permission list <session_id>`
4. **Check for questions** — `opencode-tool question get <session_id>`
5. **Never poll manually** — Use the monitor flag or wait script
6. **Retry auto-timeout** — If status is retry for configurable timeout (default 60s), monitor terminates on next interval check

### When Blocked (HITL)

1. **Permission blocked** — `opencode-tool permission grant <session_id> once|always|reject`
2. **Question blocked** — `opencode-tool question reply <request_id> "Answer"`
3. **Never ignore HITL** — Always resolve before continuing

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

# Monitor until blocked/idle
opencode-tool session status <session_id> --monitor
```

### Step 4: Handle HITL (if blocked)

#### Permission Blocked

```bash
# List pending permissions
opencode-tool permission list <session_id>

# Grant permission
opencode-tool permission grant <session_id> once
opencode-tool permission grant <session_id> always
opencode-tool permission grant <session_id> reject
```

#### Question Blocked

```bash
# Get pending questions
opencode-tool question get <session_id>

# Reply to question
opencode-tool question reply <request_id> "Option A"

# Reject question
opencode-tool question reject <request_id>
```

### Step 5: Interrupt (if needed)

```bash
opencode-tool session interrupt <session_id>
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
│ │PERMISSION│ │  → opencode-tool permission grant
│ └─────────┘ │
│ ┌─────────┐ │
│ │QUESTION │ │  → opencode-tool question reply
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
| Permission blocked | Waiting for permission | `opencode-tool permission grant` |
| Question blocked | Waiting for answer | `opencode-tool question reply` |

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
opencode-tool session list --filter active
opencode-tool session list --filter blocked
opencode-tool session list --filter permission-block
opencode-tool session list --filter question-block
opencode-tool session list --filter idle
opencode-tool session search <query>
opencode-tool session get <session_id>
opencode-tool session get <session_id> --response        # Last assistant response
opencode-tool session get <session_id> --response --hide-tools  # Response text only
opencode-tool session messages <session_id>              # All messages
opencode-tool session messages <session_id> --last 5    # Last 5 messages
opencode-tool session messages <session_id> --role assistant  # Only assistant messages
opencode-tool session messages <session_id> --hide-tools     # No tool calls
opencode-tool session messages <session_id> --limit 10 --offset 20  # Pagination
opencode-tool session status <session_id>
opencode-tool session status <session_id> --monitor
opencode-tool session interrupt <session_id>

# Run
opencode-tool run "task"
opencode-tool run --dir /path "task"
opencode-tool run -m <provider>,<model> -v <variant> "task"
opencode-tool run -s <session_id> "continue"
opencode-tool run -s <session_id> -m <provider>,<model> "switch model and continue"
opencode-tool run -s <session_id> -v <variant> "switch variant and continue"
opencode-tool run -s <session_id> --steer "new direction"

# Permissions
opencode-tool permission list <session_id>
opencode-tool permission list --all
opencode-tool permission grant <session_id> once|always|reject

# Questions
opencode-tool question get <session_id>
opencode-tool question reply <request_id> "Answer"
opencode-tool question reject <request_id>

# Config
opencode-tool config get
opencode-tool config set <key> <value>
opencode-tool config path
```

---

## Common Mistakes to Avoid

1. **Using `opencode run`** — Always use `opencode-tool run`
2. **Using `curl`** — Always use `opencode-tool` commands
3. **Forgetting `--dir`** — Sessions may run in wrong directory
4. **Ignoring HITL** — Always resolve permissions/questions before continuing
5. **Polling manually** — Use `--monitor` flag instead
6. **Continuing stuck sessions** — Start fresh if session is stuck
7. **Wrong working directory** — Always verify with `pwd` and `git branch --show-current`

---

## Use Case Examples

### Running a New Session
```bash
opencode-tool run --dir "$(pwd)" "Implement the auth module"
```

### Continuing a Session
```bash
opencode-tool run -s ses_abc123 "Continue where you left off"
```

### Changing Model Mid-Session
```bash
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 "Switch to GPT 5.5"
```

### Changing Model Variant
```bash
opencode-tool run -s ses_abc123 -v high "Use high reasoning effort"
# Retains the current model, only changes variant
```

### Changing Both Model and Variant
```bash
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 -v high "Switch to GPT 5.5 with high reasoning"
```

### Steering to Different Model
```bash
# Interrupt and switch to different model
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 --steer "Focus on unit tests"

# Interrupt and switch to different model + variant
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 -v high --steer "Focus on unit tests"

# Interrupt and only change variant (retains model)
opencode-tool run -s ses_abc123 -v high --steer "Focus on unit tests"
```

**Model/Variant Behavior:**
- Only `-m` provided → keeps current variant, changes model
- Only `-v` provided → keeps current model, changes variant
- Both `-m` and `-v` provided → changes both

### Steering Conversation
```bash
opencode-tool run -s ses_abc123 --steer "Focus on unit tests instead"
```

### Queuing a Message (Non-Interrupt)
```bash
# Queue message for after current tool call completes (does NOT interrupt)
opencode-tool run -s ses_abc123 "After that, also add error handling"

# This is different from --steer which interrupts immediately
# Use queue when you want to add instructions without disrupting current work
```

### Monitoring a Session
```bash
opencode-tool session status ses_abc123 --monitor --interval 5
```

### Getting Last Response
```bash
# With tool calls
opencode-tool session get ses_abc123 --response

# Text only (no tool calls)
opencode-tool session get ses_abc123 --response --hide-tools
```

### Getting Messages with Filtering
```bash
# Last 5 assistant messages without tool calls
opencode-tool session messages ses_abc123 --last 5 --role assistant --hide-tools

# Paginate through all messages
opencode-tool session messages ses_abc123 --limit 10 --offset 20
```

### Replying to a Question
```bash
opencode-tool question get ses_abc123
opencode-tool question reply req_abc123 "Option A"
```

### Granting Permission
```bash
opencode-tool permission list ses_abc123
opencode-tool permission grant ses_abc123 once
```

### Interrupting a Session
```bash
opencode-tool session interrupt ses_abc123
```

---

## Related Skills

| Skill | Purpose |
|-------|---------|
| `opencode-tool` | Quick reference for all CLI commands |
| `opencode-tool-commands` | Detailed CLI documentation with use cases |
