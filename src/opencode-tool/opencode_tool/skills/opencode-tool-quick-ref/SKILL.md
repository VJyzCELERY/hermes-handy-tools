---
name: opencode-tool-quick-ref
description: "Quick CLI command reference for opencode-tool — profile system, HITL, session management."
version: 2.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, reference, quick]
    related_skills: [opencode-developer, opencode-tool-cmd]
---

# OpenCode Python CLI — Quick Reference

**⚠️ Testing:** Use `uv run --project . -m opencode_tool.main` from project dir.

---

## ⛔ Critical Rules

1. **ALWAYS use `opencode-tool`** — NEVER `opencode` CLI or `curl`
2. **Profile-first** — Every command runs in a profile
3. **Default profile** — Uses port 4905 (not 4096), connects to existing server
4. **HITL prevention** — Add suffix to prompts to prevent `ask` tool blocking

---

## Profile System

**One profile = one opencode server connection.**

```bash
# Create profile (auto-persists to file)
opencode-tool profile set myproject
opencode-tool profile set              # random UUID name

# List profiles
opencode-tool profile list

# Check current
opencode-tool profile current

# Switch to different profile
opencode-tool profile set other-project

# Delete profile
opencode-tool profile delete myproject

# Terminate (kill server + delete)
opencode-tool profile terminate myproject

# Initialize default profile (from config)
opencode-tool profile init
```

**How profiles work:**
- Default profile uses port 4905 (avoids conflict with opencode's own 4096)
- Profile loaded from `OPENCODE_TOOL_PROFILE` env var
- Config loaded from `.env` file
- New profiles fork settings from default

---

## Session

```bash
opencode-tool session list
opencode-tool session list --filter busy|active|blocked|idle
opencode-tool session search <query>
opencode-tool session get <sid>
opencode-tool session get <sid> --response
opencode-tool session messages <sid> --last 5
opencode-tool session status <sid> --monitor
opencode-tool session interrupt <sid>
opencode-tool session delete <sid>              # Delete dirty session
opencode-tool session delete <sid> --force      # Skip confirmation
```

## Run

```bash
opencode-tool run "task"
opencode-tool run --dir /path "task"
opencode-tool run -m <provider>,<model> -v <variant> "task"
opencode-tool run -s <sid> "continue"
opencode-tool run -s <sid> --steer "new direction"
```

## HITL (Human-In-The-Loop)

```bash
# Detection (layers: REST API → message scan → all-sessions → TUI)
opencode-tool hitl detect <sid>
opencode-tool hitl detect <sid> --wait
opencode-tool hitl detect <sid> --all-sessions    # Catch subagent HITL

# Response (layers: REST API → TUI interrupt → tmux keystrokes)
opencode-tool hitl respond <sid> "yes"       # answer question
opencode-tool hitl respond <sid> once         # grant permission
opencode-tool hitl respond <sid> reject       # reject
opencode-tool hitl dismiss <sid>              # stop agent
```

**HITL Prevention (add to every prompt):**
```
— If you have questions, answer them inline in your response. Do NOT use the ask or question tool.
```

## Permissions (legacy)

```bash
opencode-tool permission list <sid>
opencode-tool permission grant <sid> once|always|reject
```

## Questions (legacy)

```bash
opencode-tool question get <sid>
opencode-tool question reply <qid> "Answer"
opencode-tool question dismiss <sid>
```

## Server

```bash
opencode-tool server status
opencode-tool server serve
opencode-tool server stop
```

## Cleaner

```bash
opencode-tool cleaner run-once    # Clean zombie servers
opencode-tool cleaner start       # Start daemon
opencode-tool cleaner stop        # Stop daemon
opencode-tool cleaner status      # Check status
```

## Config

```bash
opencode-tool config get
opencode-tool config set <key> <value>
```

**Config keys:**
- `opencode_server_url` — Default server URL (default: http://localhost:4905)
- `monitor_retry_timeout` — Retry timeout in seconds (default: 60)
- `default_model` — Default model ID (default: mimo-v2.5)
- `default_variant` — Default variant (default: high)

## Skills

```bash
opencode-tool skills list
opencode-tool skills get [name]
```

---

## Common Patterns

```bash
# Connect to existing server
opencode-tool profile init

# Start new isolated server
opencode-tool profile set myproject

# Run and handle HITL
sid=$(opencode-tool run "task")
opencode-tool hitl detect $sid
opencode-tool hitl respond $sid "yes"

# Clean up dirty session
opencode-tool session delete $sid --force

# Clean zombie servers
opencode-tool cleaner run-once
```
