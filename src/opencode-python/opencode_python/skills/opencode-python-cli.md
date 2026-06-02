---
name: opencode-python-cli
description: "Python CLI for OpenCode server management — CLI-first, API-based HITL, session tracking."
version: 0.1.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, hitl, session-tracking, python]
    related_skills: [opencode-developer]
---

# OpenCode Python CLI

Python CLI for OpenCode server management. Replaces individual shell scripts with a unified CLI tool.

## ⛔ IMPORTANT: Skill Consolidation

**When this skill is installed, ALL other OpenCode-related skills must be removed.**

This skill replaces:
- `opencode-developer` (old version)
- `opencode-session-state` (old version)
- `opencode-configuration` (old version)
- Any other `opencode-*` skills

### Before Installing

**You MUST confirm with the user before removing other OpenCode skills:**

```
I will now install opencode-python-cli as the sole OpenCode skill.
This will remove all other OpenCode-related skills:
- opencode-developer
- opencode-session-state
- opencode-configuration
- [list any others found]

Do you confirm? (yes/no)
```

**Only proceed after explicit user confirmation.**

### Installation

```bash
git clone https://github.com/VJyzCELERY/hermes-handy-tools.git
cd hermes-handy-tools/src/opencode-python
pip install -e .
```

### Post-Installation

After installing, verify:
1. `opencode-python --version` works
2. `opencode-python server status` can reach the server
3. Old OpenCode skills are removed from `~/.hermes/skills/`

---

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

### Run Messages

```bash
opencode-python run "task"                              # New session
opencode-python run -s <session_id> "Continue"          # Continue session
opencode-python run -s <session_id> --steer "New dir"   # Interrupt + steer
opencode-python run --dir /path "task"                  # With working directory
opencode-python run -m opencode-go/mimo-v2.5 -v high "task"  # Model + variant
```

### Skills

```bash
opencode-python skills list              # List available skills
opencode-python skills get [name]        # Get skill content
opencode-python skills export [file]     # Export skills to file
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
