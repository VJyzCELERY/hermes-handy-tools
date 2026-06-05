---
name: opencode-tool-cmd
description: "Complete command reference with use cases, examples, and troubleshooting for opencode-tool."
version: 2.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, reference, detailed, hitl, profile]
    related_skills: [opencode-developer, opencode-tool-quick-ref]
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

# Create with specific name
eval $(opencode-tool profile set myproject)

# Connect to existing server (collaborate mode)
eval $(opencode-tool profile set --collaborate myuser)
eval $(opencode-tool profile set --collaborate myuser --url http://localhost:4905)

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

### profile init

Initialize default profile from config.

```bash
opencode-tool profile init
opencode-tool profile init --json
```

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
opencode-tool server serve --port 4905
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

**Monitor detects subagent HITL:** Checks ALL sessions for blocked state, catching HITL from spawned subagents.

### session interrupt

Abort a running session.

```bash
opencode-tool session interrupt <sid>
```

### session delete

Delete a session permanently. Use for truly unrecoverable sessions.

```bash
opencode-tool session delete <sid>
opencode-tool session delete <sid> --force    # skip confirmation
opencode-tool session delete <sid> --json
```

**Use cases:**
- Dirty sessions that won't clean up
- Stuck sessions that can't be interrupted
- Cleaning up orphaned sessions

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

# Check all sessions (catches subagent HITL)
opencode-tool hitl detect <sid> --all-sessions
```

**Detection layers (tried in order):**
1. REST API (fast)
2. Message scanning (moderate)
3. All-sessions scan (catches subagent HITL)
4. TUI control/next (with `--wait`)

**Output example:**
```
Session: ses_abc123
Profile: myproject
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
2. TUI execute-command (fallback)
3. Tmux keystrokes (last resort — sends keys to OpenCode TUI via tmux)

**Tmux fallback details:**
- Only triggers when layers 1 and 2 both fail
- Finds tmux session for current profile via `find_profile_tmux_session()`
- For questions: types answer + Enter via `tmux send-keys`
- For permissions: maps `once`→`y`, `always`→`a`, `reject`→`n`
- Best-effort — TUI must be in the right state to receive input

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

## Cleaner Commands

```bash
# Clean zombie servers once
opencode-tool cleaner run-once

# Start daemon
opencode-tool cleaner start
opencode-tool cleaner start --interval 300

# Stop daemon
opencode-tool cleaner stop

# Check status
opencode-tool cleaner status

# Show log
opencode-tool cleaner log
opencode-tool cleaner log --lines 50
```

**What it cleans:**
- Servers whose process is dead
- Servers with dead tmux sessions
- Stale servers (>10 minutes since last use)
- Stale registry entries (>24 hours)

**Does NOT clean profiles** — use `profile delete` or `profile terminate` for that.

---

## Skills Commands

```bash
opencode-tool skills list
opencode-tool skills get [name]
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
- `opencode_server_url` — Default server URL (default: http://localhost:4905)
- `monitor_retry_timeout` — Retry timeout (seconds, default: 60)
- `default_model` — Default model ID (default: mimo-v2.5)
- `default_variant` — Default variant (default: high)

---

## Common Use Cases

### Setup: First-time shell setup

```bash
# Create named profile for this project
eval $(opencode-tool profile set myproject)

# All subsequent commands use this profile
opencode-tool run "analyze this code"
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

### HITL: Catch subagent HITL

```bash
# Monitor detects subagent HITL automatically
opencode-tool session status <sid> --monitor

# Or manually check all sessions
opencode-tool hitl detect <sid> --all-sessions
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

### HITL: Prevention (add to every prompt)

```bash
# Add this suffix to prevent ask/question tool blocking
opencode-tool run --dir "$(pwd)" "your prompt here — If you have questions, answer them inline in your response. Do NOT use the ask or question tool."
```

### Cleanup: Delete dirty sessions

```bash
# Delete unrecoverable session
opencode-tool session delete <sid> --force

# Clean zombie servers
opencode-tool cleaner run-once

# Terminate specific profile
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

## Troubleshooting

### "Question not registered in API"

This happens when the `ask` tool is used. The question isn't in the REST API.

**Solution:** Add HITL prevention suffix to prompts, or use `hitl dismiss` to stop the agent.

### Session stuck in "busy" but no tools running

The session might be processing a long LLM call.

**Solution:** Wait, or check with `session status <sid>`. If stuck for >60s in retry, monitor will timeout.

### Subagent HITL not detected

The subagent's session is separate from the parent session.

**Solution:** Use `hitl detect <sid> --all-sessions` or `session status <sid> --monitor` (which checks all sessions automatically).

### Can't delete session

The session might be in a dirty state.

**Solution:** Use `session delete <sid> --force` to bypass confirmation. If that fails, the session may need manual cleanup via `opencode abort <sid>`.
