---
name: opencode-tool
description: "Quick CLI command reference. For detailed documentation with use cases, see opencode-tool-commands."
version: 1.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, reference, quick]
    related_skills: [opencode-developer, opencode-tool-commands]
---

# OpenCode Python CLI — Quick Reference

Fast reference for all `opencode-tool` commands. For detailed documentation with use cases, examples, and troubleshooting, see `opencode-tool-commands`.

**Entrypoint:** `opencode-developer` — Load this skill first for behavioral rules and workflow.

**⚠️ Server Commands:** `opencode-tool server serve` and `opencode-tool server stop` require the `opencode` CLI to be installed.

---

## ⛔ Critical Rules

1. **ALWAYS use `opencode-tool`** — NEVER `opencode` CLI or `curl`
2. **ALWAYS check server first** — `opencode-tool server status`
3. **ALWAYS use `--dir`** — For worktree tasks: `opencode-tool run --dir "$(pwd)" "task"`

---

## Server

```bash
opencode-tool server status              # Check server
opencode-tool server serve               # Start server
opencode-tool server stop                # Stop server
```

## Session

```bash
opencode-tool session list               # List all sessions
opencode-tool session list --filter busy # List busy sessions
opencode-tool session list --filter active  # List active (busy+blocked)
opencode-tool session list --filter blocked  # List blocked sessions
opencode-tool session list --filter permission-block  # Permission blocked
opencode-tool session list --filter question-block  # Question blocked
opencode-tool session list --filter idle    # List completed sessions
opencode-tool session search <query>     # Search sessions
opencode-tool session get <sid>          # Get session details
opencode-tool session get <sid> --response  # Get last response
opencode-tool session get <sid> --response --hide-tools  # Response text only
opencode-tool session messages <sid>     # Get all messages
opencode-tool session messages <sid> --last 5  # Last 5 messages
opencode-tool session messages <sid> --role assistant  # Only assistant
opencode-tool session messages <sid> --hide-tools  # No tool calls
opencode-tool session messages <sid> --limit 10 --offset 20  # Pagination
opencode-tool session status <sid>       # Check status
opencode-tool session status <sid> --monitor  # Monitor until blocked/idle
opencode-tool session interrupt <sid>    # Abort session
```

## Run

```bash
opencode-tool run "task"                 # New session
opencode-tool run --dir /path "task"     # With working directory
opencode-tool run -m <provider>,<model> -v <variant> "task"  # Model + variant
opencode-tool run -s <sid> "continue"    # Continue session
opencode-tool run -s <sid> -m <provider>,<model> "continue"  # Switch model
opencode-tool run -s <sid> -v <variant> "continue"  # Switch variant only
opencode-tool run -s <sid> -m <provider>,<model> -v <variant> "continue"  # Switch both
opencode-tool run -s <sid> --steer "dir" # Interrupt + steer
opencode-tool run -s <sid> -m <provider>,<model> --steer "dir"  # Steer + switch model
opencode-tool run -s <sid> -m <provider>,<model> -v <variant> --steer "dir"  # Steer + switch both
opencode-tool run -s <sid> "queue msg"   # Queue (no interrupt)
```

## Permissions

```bash
opencode-tool permission list <sid>      # List pending for session
opencode-tool permission list --all      # List all pending
opencode-tool permission grant <sid> once|always|reject  # Grant
```

## Questions

```bash
opencode-tool question get <sid>         # Get pending questions
opencode-tool question reply <qid> "Answer"  # Reply
opencode-tool question reject <qid>      # Reject
opencode-tool question dismiss <sid>     # Dismiss (aborts session)
```

## Skills

```bash
opencode-tool skills list                # List available skills
opencode-tool skills get [name]          # Get skill content
opencode-tool skills export [file]       # Export skills
```

## Config

```bash
opencode-tool config get                 # Show all config
opencode-tool config get <key>           # Get specific value
opencode-tool config set <key> <value>   # Set value
opencode-tool config path                # Show config file path
```

---

## Common Patterns

```bash
# Pre-flight check
opencode-tool server status || opencode-tool server serve

# Run and monitor
sid=$(opencode-tool run --dir "$(pwd)" "task")
opencode-tool session status $sid --monitor

# Handle permission block
opencode-tool permission list $sid
opencode-tool permission grant $sid once

# Handle question block
opencode-tool question get $sid
opencode-tool question reply <qid> "Answer"
# Or dismiss stuck question:
opencode-tool question dismiss $sid

# Steer a session
opencode-tool run -s $sid --steer "New direction"
```

---

## For Detailed Documentation

See `cli-commands.md` for:
- Complete command syntax
- All options and flags
- Use cases and examples
- Troubleshooting guide
- Exit codes
- Environment variables
