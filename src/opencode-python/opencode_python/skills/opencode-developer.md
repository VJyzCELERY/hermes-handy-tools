---
name: opencode-developer
description: "Primary skill for all OpenCode interactions — CLI-first, API-based HITL, session tracking."
version: 3.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, development, coding-agent, cli, hitl, session-tracking]
    related_skills: [opencode-python-cli, opencode-session-state]
---

# OpenCode Developer Workflow — CLI-First, API-Based HITL

**OpenCode is the primary coding worker.** All interactions are CLI/API-based:

| Mode | When | Tools |
|------|------|-------|
| **CLI** | Sending tasks, monitoring, continuing sessions | `opencode-python send`, `opencode-python session` |
| **API** | HITL blockers — permissions, questions, status | `opencode-python permission`, `opencode-python question` |

---

## Architecture

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
│ send +  │        │ HITL     │
│ monitor │        │ resolve  │
└────┬────┘        └────┬─────┘
     │                  │
     ▼                  ▼
opencode-python    opencode-python
  send/session       permission/question
```

**Server URL:** `http://localhost:4096` (env: `OPENCODE_SERVER_URL`)

---

## Server Detection & Startup

**ALWAYS ensure the opencode server is running before any operation.**

```bash
opencode-python server status
# If not running:
opencode-python server serve
```

---

## CLI-First Workflow

### Step 1: Ensure server is running

```bash
opencode-python server status || opencode-python server serve
```

### Step 2: Send a task

```bash
opencode-python send "Implement the auth module"
opencode-python send -c "Fix the edge case"
opencode-python send -s ses_abc123 "Add more tests"
opencode-python send --dir /path/to/project "Do thing"
opencode-python send -m opencode-go/mimo-v2.5 -v high "task"
```

### Step 3: Monitor

```bash
opencode-python session status <session_id>
opencode-python session status <session_id> --monitor
```

### Step 4: Steer (interrupt + redirect)

```bash
opencode-python send -s <session_id> --steer "New direction"
```

### Step 5: Interrupt (if needed)

```bash
opencode-python session interrupt <session_id>
```

---

## HITL Resolution (API-Based)

**No TUI needed.** All resolution is via API.

### Permission Resolution

```bash
opencode-python permission list <session_id>
opencode-python permission grant <session_id> once|always|reject
```

### Question Resolution

```bash
opencode-python question get <session_id>
opencode-python question reply <request_id> "Option A" "Option B"
```

---

## Quick Reference

```bash
# Server
opencode-python server status
opencode-python server serve
opencode-python server stop

# Session
opencode-python session status <session_id>
opencode-python session status <session_id> --monitor
opencode-python session interrupt <session_id>

# Permissions
opencode-python permission list <session_id>
opencode-python permission list --all
opencode-python permission grant <session_id> once|always|reject

# Questions
opencode-python question get <session_id>
opencode-python question reply <request_id> "Answer"
opencode-python question reject <request_id>

# Send
opencode-python send "task"
opencode-python send -s <sid> --steer "new direction"

# Config
opencode-python config get
opencode-python config set opencode_server_url http://localhost:4096
```
