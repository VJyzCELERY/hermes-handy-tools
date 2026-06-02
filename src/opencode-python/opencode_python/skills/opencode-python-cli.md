# opencode-python-cli

---
name: opencode-python-cli
description: "Python CLI for OpenCode server management — CLI-first, API-based HITL, session tracking."
version: 0.1.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, hitl, session-tracking, python]
---

# OpenCode Python CLI

Python CLI for OpenCode server management. Replaces individual shell scripts with a unified CLI tool.

## Installation

```bash
cd /path/to/opencode-python-cli
pip install -e .
```

## Commands

### Server Management

```bash
opencode-python server status              # Check server status
opencode-python server serve               # Start server (localhost only)
opencode-python server stop                # Stop server (localhost only)
```

### Session Management

```bash
opencode-python session status <session_id>           # Check session status
opencode-python session status <session_id> --monitor # Monitor until blocked/idle
opencode-python session interrupt <session_id>        # Abort a running session
```

### Permission Management

```bash
opencode-python permission list <session_id>      # List pending for session
opencode-python permission list --all             # List all pending
opencode-python permission grant <session_id> once    # Allow once
opencode-python permission grant <session_id> always  # Allow always
opencode-python permission grant <session_id> reject  # Reject
```

### Question Management

```bash
opencode-python question get <session_id>              # List pending questions
opencode-python question reply <request_id> "Answer"   # Reply to questions
opencode-python question reject <request_id>           # Reject question
```

### Send Messages

```bash
opencode-python send "task"                              # New session
opencode-python send -s <session_id> "Continue"          # Continue session
opencode-python send -s <session_id> --steer "New dir"   # Interrupt + steer
opencode-python send --dir /path "task"                  # With working directory
opencode-python send -m opencode-go/mimo-v2.5 -v high "task"  # Model + variant
```

### Configuration

```bash
opencode-python config get                           # Show all config
opencode-python config get opencode_server_url       # Get specific value
opencode-python config set opencode_server_url http://localhost:4096
opencode-python config path                          # Show config file path
```

## Configuration

Config stored at `~/.config/opencode-python-cli/config.json`:

```json
{
  "opencode_server_url": "http://localhost:4096"
}
```

Environment variable `OPENCODE_SERVER_URL` takes precedence.
