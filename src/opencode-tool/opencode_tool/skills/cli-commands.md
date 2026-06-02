---
name: opencode-tool-commands
description: "Detailed CLI command documentation with use cases, examples, and troubleshooting."
version: 1.0.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, commands, reference, documentation]
    related_skills: [opencode-developer, opencode-tool]
---

# OpenCode Python CLI — Detailed Command Reference

Complete documentation for every `opencode-tool` command with use cases, examples, and troubleshooting.

**Entrypoint:** `opencode-developer` — Load this skill first for behavioral rules and workflow.

**⚠️ Server Commands:** `opencode-tool server serve` and `opencode-tool server stop` require the `opencode` CLI to be installed. The `run` command does NOT require it (uses API directly).

---

## Server Commands

### `opencode-tool server status`

Check if the OpenCode server is running and accessible.

**Syntax:**
```bash
opencode-tool server status
```

**Output:**
```
Server URL: http://localhost:4096
Status: Running
Version: 1.15.7
Sessions: 44
```

**Use Cases:**
- Pre-flight check before any operation
- Verifying server health after startup
- Debugging connection issues

**Example:**
```bash
# Always check before running tasks
opencode-tool server status || opencode-tool server serve
```

---

### `opencode-tool server serve`

Start the OpenCode web server in the background.

**Syntax:**
```bash
opencode-tool server serve
```

**Output:**
```
Server started on http://localhost:4096
PID: 12345
```

**Use Cases:**
- Starting server after system reboot
- Restarting server after crash
- Starting server for the first time

**Example:**
```bash
# Start server if not running
if ! opencode-tool server status >/dev/null 2>&1; then
    opencode-tool server serve
fi
```

**Notes:**
- Server runs in background
- Uses port 4096 by default
- PID stored for later stop

---

### `opencode-tool server stop`

Stop the running OpenCode server.

**Syntax:**
```bash
opencode-tool server stop
```

**Output:**
```
Server stopped
```

**Use Cases:**
- Graceful shutdown
- Restarting server
- Freeing port 4096

**Example:**
```bash
# Restart server
opencode-tool server stop
sleep 2
opencode-tool server serve
```

---

## Session Commands

### `opencode-tool session list`

List all sessions with pagination and optional status filter.

**Syntax:**
```bash
opencode-tool session list [--limit N] [--offset N] [--json] [--filter FILTER]
```

**Options:**
- `--limit N` — Number of sessions to show (default: 20)
- `--offset N` — Offset for pagination (default: 0)
- `--json` — Output JSON
- `--filter FILTER` — Filter by status:
  - `all` (default) — All sessions
  - `busy` — Only busy sessions (processing, no blocks)
  - `active` — Busy + blocked (permission, question, retry)
  - `blocked` — Not idle but not busy (permission, question, retry)
  - `idle` — Completed sessions
  - `permission-block` — Blocked on permission request
  - `question-block` — Blocked on question
  - `retry` — Retrying after failure instead of table

**Output:**
```
Sessions (showing 1-20 of 45)

ID                    Title                          Agent    Model              Updated
ses_abc123            Implement auth module           build    mimo-v2.5          2026-06-02 15:30
ses_def456            Fix edge case in login          build    deepseek-v4-flash  2026-06-02 14:20
...
```

**Use Cases:**
- Finding a specific session to continue
- Reviewing recent activity
- Checking session history
- Finding blocked sessions that need attention

**Examples:**
```bash
# List all sessions
opencode-tool session list

# List only busy sessions
opencode-tool session list --filter busy

# List all active sessions (busy + blocked)
opencode-tool session list --filter active

# List blocked sessions (permission, question, retry)
opencode-tool session list --filter blocked

# List sessions blocked on permission
opencode-tool session list --filter permission-block

# List sessions blocked on question
opencode-tool session list --filter question-block

# List idle (completed) sessions
opencode-tool session list --filter idle

# Paginate through filtered results
opencode-tool session list --filter busy --limit 10 --offset 20
```

---

### `opencode-tool session search <query>`

Search sessions by title, agent, or model.

**Syntax:**
```bash
opencode-tool session search <query> [--limit N] [--json]
```

**Options:**
- `--limit N` — Max results (default: 10)
- `--json` — Output JSON

**Output:**
```
Found 3 session(s) matching 'auth':

ses_abc123
  Title: Implement auth module
  Agent: build | Model: mimo-v2.5
  Updated: 2026-06-02 15:30

ses_def456
  Title: Fix auth token refresh
  Agent: build | Model: deepseek-v4-flash
  Updated: 2026-06-02 14:20
```

**Use Cases:**
- Finding sessions by topic
- Locating specific work
- Reviewing related sessions

**Example:**
```bash
# Find all sessions about "test"
opencode-tool session search test

# Find sessions using GPT 5.5
opencode-tool session search gpt-5.5
```

---

### `opencode-tool session get <session_id>`

Get detailed information about a specific session.

**Syntax:**
```bash
opencode-tool session get <session_id> [--json] [--messages] [--response] [--hide-tools]
```

**Options:**
- `--json` — Output JSON
- `--messages` — Include message history
- `--response` — Show only the last assistant response
- `--hide-tools` — Hide tool calls in response (with `--response`)

**Output:**
```
Session: ses_abc123
Title:   Implement auth module
Agent:   build
Model:   mimo-v2.5 (opencode-go)
Variant: high
Created: 2026-06-02 15:30:00
Updated: 2026-06-02 15:45:00
Cost:    $0.0023
Tokens:  15000 in / 3000 out
```

**Use Cases:**
- Checking session details
- Reviewing cost and tokens
- Getting session metadata
- Getting the last response from a session

**Examples:**
```bash
# Get session details
opencode-tool session get ses_abc123

# Get last assistant response (with tool calls)
opencode-tool session get ses_abc123 --response

# Get last assistant response (text only, no tool calls)
opencode-tool session get ses_abc123 --response --hide-tools

# Get session with messages
opencode-tool session get ses_abc123 --messages --json
```

---

### `opencode-tool session messages <session_id>`

Get messages from a session with filtering and pagination.

**Syntax:**
```bash
opencode-tool session messages <session_id> [--limit N] [--offset N] [--last N] [--role ROLE] [--hide-tools] [--json]
```

**Options:**
- `--limit N` — Number of messages to show (default: 20)
- `--offset N` — Offset for pagination (default: 0)
- `--last N` — Get last N messages
- `--role ROLE` — Filter by role (`user` or `assistant`)
- `--hide-tools` — Hide tool call results
- `--json` — Output JSON

**Output:**
```
Messages for ses_abc123 (showing 1-5 of 18):

USER
  "Search the internet about opencode and hermes"

ASSISTANT
  tool: webfetch (completed)

ASSISTANT
  Based on my research, here's what I found...
```

**Use Cases:**
- Reviewing conversation history
- Checking what the agent did
- Debugging session behavior
- Getting specific messages (last N, by role)

**Examples:**
```bash
# Get all messages
opencode-tool session messages ses_abc123

# Get last 5 messages
opencode-tool session messages ses_abc123 --last 5

# Get only assistant messages (no tool calls)
opencode-tool session messages ses_abc123 --role assistant --hide-tools

# Paginate through messages
opencode-tool session messages ses_abc123 --limit 10 --offset 20

# Get messages as JSON
opencode-tool session messages ses_abc123 --json
```

---

### `opencode-tool session status <session_id>`

Check the current status of a session.

**Syntax:**
```bash
opencode-tool session status <session_id> [--monitor] [--interval N]
```

**Options:**
- `--monitor` — Monitor until blocked/idle (only prints on status change)
- `--interval N` — Monitor interval in seconds (default: 10)

**Output (one-time):**
```
Session: ses_abc123
Status:  busy
Permissions: none
Questions: none
```

**Output (monitor mode — only prints on status change):**
```
Monitoring ses_abc123 (Ctrl+C to stop)...

Session: ses_abc123
Status:  busy
Permissions: none
Questions: none

✓ Session completed (idle)
```

**Use Cases:**
- Checking if session is still running
- Monitoring long-running tasks
- Detecting HITL blockers

**Examples:**
```bash
# One-time check
opencode-tool session status ses_abc123

# Monitor until done (silent until status changes)
opencode-tool session status ses_abc123 --monitor

# Monitor with custom interval
opencode-tool session status ses_abc123 --monitor --interval 5
```

**Status Types:**
| Status | Meaning |
|--------|---------|
| `idle` | Session completed |
| `busy` | Session processing |
| `retry` | Retrying after failure (auto-timeout after 60s) |

**Monitor Behavior:**
- Only prints when status changes (busy → idle, busy → permission blocked, etc.)
- Does NOT print if status stays the same (busy → busy)
- For retry status, waits for configurable timeout (default 60s) before allowing termination
- Retry timeout is configurable via `opencode-tool config set monitor_retry_timeout <seconds>`

---

### `opencode-tool session interrupt <session_id>`

Abort a running session.

**Syntax:**
```bash
opencode-tool session interrupt <session_id>
```

**Output:**
```
aborted: ses_abc123
```

**Use Cases:**
- Stopping a stuck session
- Cancelling a long-running task
- Freeing resources

**Example:**
```bash
# Interrupt a session
opencode-tool session interrupt ses_abc123

# Verify it's stopped
opencode-tool session status ses_abc123
```

**Notes:**
- Session state is preserved
- Can be continued later with `-s`
- Use sparingly — prefer steering

---

## Run Commands

### `opencode-tool run "task"`

Send a task to OpenCode and create a new session.

**Syntax:**
```bash
opencode-tool run [options] "task"
```

**Options:**
- `--dir PATH` — Working directory
- `-m, --model MODEL` — Model to use
- `-v, --variant VARIANT` — Model variant (low/medium/high)
- `-c, --continue` — Continue last session
- `-s, --session SESSION_ID` — Continue specific session
- `--steer "direction"` — Interrupt and redirect (requires `-s`)

**Output:**
```
ses_abc123
```

**Examples:**

```bash
# Simple task
opencode-tool run "Implement the auth module"

# With working directory
opencode-tool run --dir /path/to/project "Fix the bug"

# With model and variant
opencode-tool run -m opencode-go,mimo-v2.5 -v high "Complex task"

# Continue last session
opencode-tool run -c "Add more tests"

# Continue specific session
opencode-tool run -s ses_abc123 "Continue where you left off"

# Queue message (does NOT interrupt, waits for current tool call to finish)
opencode-tool run -s ses_abc123 "After that, also add error handling"

# Steer (interrupt + redirect)
opencode-tool run -s ses_abc123 --steer "Focus on unit tests instead"

# Change model mid-session
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 "Switch to GPT 5.5"

# Change variant mid-session (retains current model)
opencode-tool run -s ses_abc123 -v high "Use high reasoning effort"

# Change both model and variant
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 -v high "Switch to GPT 5.5 with high reasoning"

# Steer + switch model
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 --steer "Focus on unit tests"

# Steer + switch both model and variant
opencode-tool run -s ses_abc123 -m openai,gpt-5.5 -v high --steer "Focus on unit tests"
```

**Use Cases:**
- Starting new development tasks
- Continuing existing work
- Redirecting agent focus

**Notes:**
- Always use `--dir "$(pwd)"` for worktree tasks
- Returns session ID for monitoring
- Use `-s` with `--steer` to redirect

---

## Permission Commands

### `opencode-tool permission list <session_id>`

List pending permissions for a specific session.

**Syntax:**
```bash
opencode-tool permission list <session_id>
```

**Output:**
```
Permissions: 2 pending
  [per_abc123] bash: git push
  [per_def456] bash: npm install
```

**Use Cases:**
- Checking what permissions are needed
- Reviewing before granting
- Debugging permission blocks

**Example:**
```bash
# List permissions for a session
opencode-tool permission list ses_abc123

# List all pending permissions across all sessions
opencode-tool permission list --all
```

---

### `opencode-tool permission list --all`

List all pending permissions across all sessions.

**Syntax:**
```bash
opencode-tool permission list --all
```

**Output:**
```
All Pending Permissions:

Session: ses_abc123
  [per_abc123] bash: git push

Session: ses_def456
  [per_def456] bash: npm install
```

**Use Cases:**
- Overview of all blocked sessions
- Finding which sessions need attention
- Batch permission management

---

### `opencode-tool permission grant <session_id> <action>`

Grant or reject a permission request.

**Syntax:**
```bash
opencode-tool permission grant <session_id> once|always|reject
```

**Actions:**
- `once` — Allow this specific command
- `always` — Allow this command pattern for the session
- `reject` — Deny the command

**Output:**
```
granted: per_abc123
```

**Examples:**
```bash
# Allow once
opencode-tool permission grant ses_abc123 once

# Allow always for this session
opencode-tool permission grant ses_abc123 always

# Reject
opencode-tool permission grant ses_abc123 reject
```

**Use Cases:**
- Resolving permission blocks
- Allowing safe operations
- Denying risky operations

**Notes:**
- `once` is safest — allows one execution
- `always` is convenient but less secure
- Use `reject` for untrusted commands

---

## Question Commands

### `opencode-tool question get <session_id>`

Get pending questions for a session.

Scans the last assistant message for the latest question tool call (ignoring stale questions from `GET /question` API), then cross-references with the REST API to get the proper `que_` request_id for reply.

**Syntax:**
```bash
opencode-tool question get <session_id>
```

**Output (question registered in API):**
```
[que_abc123]
  Q1: Superpower
      If you could have any superpower, which one would you choose?
        1. X-ray vision: See through walls and across distances
        2. Time freeze: Freeze time and do whatever you want
        3. Teleportation: Teleport anywhere in the world
        4. Mind reading: Read people's thoughts
```

**Output (question not yet registered):**
```
[call_abc123]
  (question not registered in API — may need TUI to reply)
  Q1: Superpower
      ...
```

**Use Cases:**
- Checking what questions are pending
- Reviewing before answering
- Debugging question blocks

**Example:**
```bash
# Get questions for a session
opencode-tool question get ses_abc123
```

---

### `opencode-tool question reply <request_id> <answers...>`

Reply to a pending question.

**Syntax:**
```bash
opencode-tool question reply <request_id> "Answer"
opencode-tool question reply <request_id> "Option A" "Option B"
```

**Output:**
```
replied: que_abc123
  Q1: Option A
  Q2: Option B
```

**Examples:**
```bash
# Single answer
opencode-tool question reply que_abc123 "Option A"

# Multiple answers (one per sub-question, quoted separately)
opencode-tool question reply que_abc123 "Option A" "Option B"

# Numeric choice
opencode-tool question reply que_abc123 "1"
```

**How it finds the question:**
1. `GET /question` by id (fast path)
2. `GET /question` by `tool.callID` mapping
3. Scans active sessions' messages
4. If not found, sends raw answers as-is

**Use Cases:**
- Answering agent questions
- Providing input to workflows
- Resolving question blocks

**Notes:**
- Answers must match option labels or numbers
- Multiple answers for multi-select questions
- Use `get` first to see available options and the request_id
- Pass answers as separate quoted strings, NOT as a JSON array

---

### `opencode-tool question reject <request_id>`

Reject a pending question.

**Syntax:**
```bash
opencode-tool question reject <request_id>
```

**Output:**
```
rejected: req_abc123
```

**Use Cases:**
- Declining to answer
- Skipping optional questions
- Rejecting unwanted prompts

---

### `opencode-tool question dismiss <session_id>`

Dismiss a pending question by aborting the session. Clears stuck question blocks when the question isn't registered in the API.

**Syntax:**
```bash
opencode-tool question dismiss <session_id>
```

**Output:**
```
dismissed: ses_abc123
Session interrupted — agent stopped, question cleared
```

**Use Cases:**
- Question not registered in API (shows "may need TUI to reply" in `get` output)
- Stuck on a question with no way to answer via CLI
- Need to quickly unblock a session

**Notes:**
- This aborts the session — the agent stops processing
- You can send a new message after dismiss to continue the session
- Prefer `question reply` or `question reject` when the question is registered

---

## Skills Commands

### `opencode-tool skills list`

List all available bundled skills.

**Syntax:**
```bash
opencode-tool skills list
```

**Output:**
```
Available Skills:
  - opencode-developer: Primary skill for all OpenCode interactions
  - cli-commands: Detailed CLI command documentation
  - opencode-tool-cli: CLI command reference
```

**Use Cases:**
- Discovering available skills
- Checking installed skills
- Finding skill names

---

### `opencode-tool skills get [name]`

Get skill content by name.

**Syntax:**
```bash
opencode-tool skills get [name]
```

**Output (with name):**
```markdown
---
name: opencode-developer
description: "Primary skill for all OpenCode interactions..."
---
# OpenCode Developer Workflow
...
```

**Output (without name):**
Returns all skills concatenated.

**Use Cases:**
- Reading skill content
- Installing skills manually
- Reviewing skill instructions

**Example:**
```bash
# Get specific skill
opencode-tool skills get opencode-developer

# Get all skills
opencode-tool skills get
```

---

### `opencode-tool skills export [file]`

Export skills to a file.

**Syntax:**
```bash
opencode-tool skills export [file] [--name SKILL_NAME]
```

**Options:**
- `--name SKILL_NAME` — Export specific skill only

**Output:**
```markdown
---
name: opencode-developer
description: "Primary skill for all OpenCode interactions..."
---
# OpenCode Developer Workflow
...
```

**Use Cases:**
- Installing skills to Hermes
- Backing up skills
- Sharing skills

**Example:**
```bash
# Export to file
opencode-tool skills export /path/to/output.md

# Export specific skill
opencode-tool skills export --name opencode-developer /path/to/output.md

# Export to stdout (for piping)
opencode-tool skills export
```

---

## Config Commands

### `opencode-tool config get [key]`

Show configuration values.

**Syntax:**
```bash
opencode-tool config get [key]
```

**Output (without key):**
```
Configuration:
  opencode_server_url = http://localhost:4096
```

**Output (with key):**
```
opencode_server_url = http://localhost:4096
```

**Use Cases:**
- Checking current configuration
- Verifying server URL
- Debugging config issues

**Example:**
```bash
# Show all config
opencode-tool config get

# Show specific value
opencode-tool config get opencode_server_url
```

---

### `opencode-tool config set <key> <value>`

Set a configuration value.

**Syntax:**
```bash
opencode-tool config set <key> <value>
```

**Output:**
```
Set opencode_server_url = http://localhost:4097
```

**Use Cases:**
- Changing server URL
- Updating configuration
- Customizing behavior

**Example:**
```bash
# Set server URL
opencode-tool config set opencode_server_url http://localhost:4097

# Set custom port
opencode-tool config set opencode_server_url http://192.168.1.100:4096
```

---

### `opencode-tool config path`

Show the configuration file path.

**Syntax:**
```bash
opencode-tool config path
```

**Output:**
```
~/.config/opencode-tool-cli/config.json
```

**Use Cases:**
- Finding config file location
- Manual config editing
- Debugging config issues

---

## Global Options

### `--version`

Show version information.

```bash
opencode-tool --version
# opencode-tool, version 0.1.0
```

### `--help`

Show help for any command.

```bash
opencode-tool --help
opencode-tool run --help
opencode-tool session --help
```

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENCODE_SERVER_URL` | Server URL | `http://localhost:4096` |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (server not found, permission denied, etc.) |
| `2` | Usage error (bad arguments) |

---

## Troubleshooting

### "Server not reachable"

```bash
# Check if server is running
opencode-tool server status

# Start server
opencode-tool server serve

# Check server health
curl -s http://localhost:4096/global/health
```

### "Session not found"

```bash
# List all sessions
opencode-tool session list

# Search for session
opencode-tool session search <query>
```

### "Permission denied"

```bash
# List pending permissions
opencode-tool permission list <session_id>

# Grant permission
opencode-tool permission grant <session_id> once
```

### "Question blocked"

```bash
# Get pending questions
opencode-tool question get <session_id>

# Reply to question
opencode-tool question reply <request_id> "Answer"

# Dismiss stuck question (aborts session)
opencode-tool question dismiss <session_id>
```

### "Session stuck"

```bash
# Check session status
opencode-tool session status <session_id>

# Monitor for blocking reasons
opencode-tool session status <session_id> --monitor

# Interrupt if needed
opencode-tool session interrupt <session_id>

# Start fresh session
opencode-tool run "New task"
```
