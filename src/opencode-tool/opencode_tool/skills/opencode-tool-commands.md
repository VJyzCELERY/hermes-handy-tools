---
name: opencode-tool-commands
description: "Complete command reference with use cases, examples, and troubleshooting for opencode-tool."
version: 1.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, reference, detailed, hitl, profile]
    related_skills: [opencode-developer, opencode-tool]
---

# OpenCode Tool — Complete Command Reference

Every command, every flag, every use case.

**⚠️ Testing:** Always use `uv run --project . -m opencode_tool.main` from the project directory.

---

## Profile Commands

### profile set

Set the active profile for the current shell session. Outputs shell export commands for `eval`.

```bash
# Auto-generate random UUID name
eval $(opencode-tool profile set)
# Output:
# Profile: a1b2c3d4e5f6
# Mode:    isolated
# URL:     http://localhost:16384
# export OPENCODE_SERVER_URL="http://localhost:16384"
# export OPENCODE_SERVER_MODE="isolated"
# export OPENCODE_TOOL_PROFILE="a1b2c3d4e5f6"

# Create with specific name
eval $(opencode-tool profile set myproject)

# Connect to existing server (collaborate mode)
eval $(opencode-tool profile set --collaborate myuser)
eval $(opencode-tool profile set --collaborate myuser --url http://localhost:4096)

# JSON output
eval $(opencode-tool profile set myproject --json)
```

**Flags:**
- `--port PORT` — Specific port (default: auto-detect)
- `--dir PATH` — Working directory
- `--collaborate NAME` — Connect to existing server
- `--url URL` — Server URL (for collaborate mode)
- `--json` — Output JSON instead of export commands

**Rules:**
- 1 URL = 1 profile (no duplicate URLs)
- If profile name exists, reuses it
- Server auto-started on available port

### profile create

Create a profile without setting shell environment. Same as `set` but no export output.

```bash
opencode-tool profile create myproject
opencode-tool profile create myproject --port 12345
opencode-tool profile create myproject --from .env
```

### profile list

List all profiles.

```bash
opencode-tool profile list
opencode-tool profile list --json
```

### profile current

Show the currently active profile.

```bash
opencode-tool profile current
opencode-tool profile current --json
```

### profile status

Show profile details and server info.

```bash
opencode-tool profile status myproject
opencode-tool profile status  # uses active profile
opencode-tool profile status --json
```

### profile delete

Delete a profile directory. Stops servers first.

```bash
opencode-tool profile delete myproject
opencode-tool profile delete myproject --force  # skip confirmation
```

### profile terminate

Kill server process + delete profile + clean registry. More thorough than delete.

```bash
opencode-tool profile terminate myproject
opencode-tool profile terminate myproject --force
```

**Use case:** When you want to fully clean up a profile including its server process.

### profile cleanup

Scan and clean orphaned profiles and zombie servers.

```bash
# Preview what would be cleaned
opencode-tool profile cleanup --dry-run

# Actually clean
opencode-tool profile cleanup

# JSON output
opencode-tool profile cleanup --json
```

**Detects:**
- Servers whose owning shell is dead
- Profiles with no running server and dead shell
- Stale registry entries

**Use case:** Run periodically or when you notice zombie opencode processes.

---

## Server Commands

### server status

Check if the server is running.

```bash
opencode-tool server status
```

### server serve

Start the opencode server.

```bash
opencode-tool server serve
opencode-tool server serve --port 4096
opencode-tool server serve --password mypass
```

### server stop

Stop the opencode server.

```bash
opencode-tool server stop
```

---

## Session Commands

### session list

List all sessions with optional filters.

```bash
opencode-tool session list
opencode-tool session list --filter busy
opencode-tool session list --filter active      # busy + blocked
opencode-tool session list --filter blocked
opencode-tool session list --filter permission-block
opencode-tool session list --filter question-block
opencode-tool session list --filter idle
opencode-tool session list --filter retry
opencode-tool session list --json
```

### session search

Search sessions by title, agent, or model.

```bash
opencode-tool session search "bug fix"
opencode-tool session search mimo --json
```

### session get

Get session details.

```bash
opencode-tool session get <sid>
opencode-tool session get <sid> --json
opencode-tool session get <sid> --messages
opencode-tool session get <sid> --response        # last assistant response
opencode-tool session get <sid> --response --hide-tools  # text only
```

### session messages

Get messages from a session.

```bash
opencode-tool session messages <sid>
opencode-tool session messages <sid> --last 5
opencode-tool session messages <sid> --role assistant
opencode-tool session messages <sid> --hide-tools
opencode-tool session messages <sid> --limit 10 --offset 20
opencode-tool session messages <sid> --json
```

### session status

Check session status.

```bash
opencode-tool session status <sid>
opencode-tool session status <sid> --monitor       # watch until blocked/idle
opencode-tool session status <sid> --monitor --interval 5
```

### session interrupt

Abort a running session.

```bash
opencode-tool session interrupt <sid>
```

---

## Run Command

### run

Send a prompt to OpenCode.

```bash
# New session
opencode-tool run "fix the bug"

# With working directory
opencode-tool run --dir /path/to/project "fix the bug"

# With model and variant
opencode-tool run -m opencode-go,mimo-v2.5 -v high "fix the bug"

# Continue existing session
opencode-tool run -s <sid> "now add tests"

# Switch model on continue
opencode-tool run -s <sid> -m opencode-go,mimo-v2.5 "continue"

# Switch variant only
opencode-tool run -s <sid> -v high "continue"

# Steer (interrupt + send)
opencode-tool run -s <sid> --steer "actually, try a different approach"

# Steer + switch model
opencode-tool run -s <sid> -m opencode-go,mimo-v2.5 --steer "new direction"

# Queue message (no interrupt)
opencode-tool run -s <sid> "also fix the tests"
```

**Flags:**
- `-s, --session SID` — Continue specific session
- `-c, --continue` — Continue last session
- `-m, --model MODEL` — Model (format: provider,model)
- `-v, --variant VARIANT` — Reasoning effort variant
- `-d, --dir DIR` — Working directory
- `-w, --wait` — Wait for completion
- `--steer` — Interrupt first, then send
- `--json` — Output JSON

---

## HITL Commands

### hitl detect

Detect pending HITL requests (permissions or questions).

```bash
# Basic detection
opencode-tool hitl detect <sid>

# JSON output
opencode-tool hitl detect <sid> --json

# Block until found (isolated mode only)
opencode-tool hitl detect <sid> --wait

# With timeout
opencode-tool hitl detect <sid> --wait --timeout 10
```

**Detection layers (tried in order):**
1. REST API (fast)
2. Message scanning (moderate)
3. TUI control/next (with `--wait`)

**Output example:**
```
Session: ses_abc123
Profile: myproject (isolated)
Source:  message-scan
Type:    question

  Q1: Confirm Action
      The agent wants to run: rm -rf /tmp/old
      Options:
        1. yes: Allow this action
        2. no:  Reject this action
```

### hitl respond

Respond to a pending HITL request. Auto-detects type.

```bash
# Answer a question
opencode-tool hitl respond <sid> "yes"
opencode-tool hitl respond <sid> "Option A"

# Grant permission
opencode-tool hitl respond <sid> once       # allow this time
opencode-tool hitl respond <sid> always     # allow forever

# Reject
opencode-tool hitl respond <sid> reject

# JSON output
opencode-tool hitl respond <sid> "yes" --json
```

**Response layers:**
1. REST API reply (fast)
2. TUI execute-command (isolated only, fallback)

### hitl dismiss

Dismiss all HITL requests (stops agent).

```bash
opencode-tool hitl dismiss <sid>
opencode-tool hitl dismiss <sid> --json
```

**Use case:** Agent is stuck on a question you can't answer, or you want to stop it.

---

## Permission Commands (Legacy — prefer hitl)

```bash
opencode-tool permission list <sid>
opencode-tool permission list --all
opencode-tool permission grant <sid> once
opencode-tool permission grant <sid> always
opencode-tool permission grant <sid> reject
```

---

## Question Commands (Legacy — prefer hitl)

```bash
opencode-tool question get <sid>
opencode-tool question reply <qid> "Answer"
opencode-tool question reject <qid>
opencode-tool question dismiss <sid>
```

---

## Skills Commands

```bash
opencode-tool skills list
opencode-tool skills get [name]
opencode-tool skills export [file]
```

---

## Config Commands

```bash
opencode-tool config get
opencode-tool config get <key>
opencode-tool config set <key> <value>
opencode-tool config path
```

**Config keys:**
- `opencode_server_url` — Default server URL
- `monitor_retry_timeout` — Retry timeout (seconds)
- `default_model` — Default model ID
- `default_variant` — Default variant

---

## Common Use Cases

### Setup: First-time shell setup

```bash
# Create named profile for this project
eval $(opencode-tool profile set myproject)

# All subsequent commands use this profile
opencode-tool run "analyze this code"
```

### Auto: One-shot command (no profile setup)

```bash
# Auto-creates ephemeral profile
opencode-tool run "quick question about main.py"
```

### HITL: Handle stuck agent

```bash
# Check what's pending
opencode-tool hitl detect <sid>

# Respond
opencode-tool hitl respond <sid> "yes"

# Or dismiss if can't answer
opencode-tool hitl dismiss <sid>
```

### HITL: Automated HITL response

```bash
#!/bin/bash
sid=$1
result=$(opencode-tool hitl detect $sid --json)
type=$(echo $result | python3 -c "import sys,json; print(json.load(sys.stdin)['type'])")

if [ "$type" == "permission" ]; then
    opencode-tool hitl respond $sid once
elif [ "$type" == "question" ]; then
    opencode-tool hitl respond $sid "auto-approved"
fi
```

### Collaboration: Help user's session

```bash
# Connect to user's server
eval $(opencode-tool profile set --collaborate myuser --url http://localhost:4096)

# Detect HITL on user's session
opencode-tool hitl detect <user_session_id>

# Respond (REST API only — safe)
opencode-tool hitl respond <user_session_id> once
```

### Cleanup: Kill zombie servers

```bash
# Preview what's orphaned
opencode-tool profile cleanup --dry-run

# Clean all zombies
opencode-tool profile cleanup

# Kill specific profile
opencode-tool profile terminate old-project --force
```

### Monitor: Watch session until done

```bash
# Monitor with auto-exit on completion
opencode-tool session status <sid> --monitor

# Monitor with custom interval
opencode-tool session status <sid> --monitor --interval 5
```

---

## Environment Variables

| Variable | Description | Set by |
|----------|-------------|--------|
| `OPENCODE_SERVER_URL` | Server URL | `profile set` |
| `OPENCODE_SERVER_MODE` | `isolated` or `collaborate` | `profile set` |
| `OPENCODE_TOOL_PROFILE` | Active profile name | `profile set` |
| `OPENCODE_SERVER_ID` | Server registry ID | `profile set` |
| `OPENCODE_SERVER_PASSWORD` | Auth password | manual |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (see stderr) |

---

## Troubleshooting

**"No active profile"**
```bash
eval $(opencode-tool profile set)
```

**"Port already in use"**
```bash
opencode-tool profile cleanup  # kill zombies first
```

**"Server not running"**
```bash
opencode-tool server status
opencode-tool server serve  # start it
```

**"HITL not responding"**
```bash
# Check mode
echo $OPENCODE_SERVER_MODE

# If collaborate, REST API only — no TUI fallback
# Switch to isolated for full capabilities
eval $(opencode-tool profile set myproject)
```

**Zombie processes accumulating**
```bash
opencode-tool profile cleanup --dry-run  # preview
opencode-tool profile cleanup             # clean
```
