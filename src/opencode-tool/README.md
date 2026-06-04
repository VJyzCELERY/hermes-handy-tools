# opencode-tool

Python CLI for OpenCode server management. Replaces individual shell scripts with a unified CLI tool.

## For Agents: Pre-Installation Checks

**Before installing opencode-tool, agents MUST perform these checks:**

### Step 1: Check if opencode CLI is installed

```bash
which opencode || echo "NOT INSTALLED"
```

- **If NOT installed:** Ask the user: "opencode CLI is not installed. Would you like me to install it?"
- **If user says yes:** Install opencode following official instructions
- **If user says no:** Stop installation — opencode-tool requires opencode for server management

### Step 2: Check if opencode can serve

```bash
opencode --version
opencode serve --help
```

- Verify opencode can start a server (has `serve` or `web` subcommand)
- If opencode is installed but cannot serve, warn the user

### Step 3: Check if server is already running

```bash
curl -s http://localhost:4096/global/health 2>/dev/null || echo "NOT RUNNING"
```

- **If running:** Server is ready, proceed with installation
- **If NOT running:** Ask the user: "OpenCode server is not running on localhost:4096. Would you like me to start it?"
  - If user says yes: `opencode web` or `opencode-tool server serve`
  - If user says no: Installation can proceed, but commands requiring server will fail

### Step 4: Proceed with installation

After all checks pass, proceed with installation:

```bash
git clone https://github.com/VJyzCELERY/hermes-handy-tools.git
cd hermes-handy-tools/src/opencode-tool
pip install -e .
```

## Installation

### Prerequisites

- Python 3.11+
- tmux (for profile isolation)
- OpenCode CLI installed (for server management)
- OpenCode server running on `localhost:4096` (or set `OPENCODE_SERVER_URL`)

### Install tmux

**Ubuntu/Debian:**
```bash
sudo apt-get install tmux
```

**macOS:**
```bash
brew install tmux
```

**Arch Linux:**
```bash
sudo pacman -S tmux
```

**Verify tmux is installed:**
```bash
tmux -V
```

### Install

```bash
git clone https://github.com/VJyzCELERY/hermes-handy-tools.git
cd hermes-handy-tools/src/opencode-tool
pip install -e .
```

### Verify

```bash
opencode-tool --version
opencode-tool server status
```

## Skills Installation

When you install `opencode-tool`, you have bundled skills that teach agents how to use the tool properly. You MUST choose an installation mode.

### ⚠️ IMPORTANT: Choose Your Installation Mode

**The installer will ask you which mode to use.** Choose one:

| Mode | What Happens | When to Use |
|------|--------------|-------------|
| **Strict** (default) | Removes ALL existing opencode-related skills. Installs bundled skills fresh. | First install, or when existing skills are outdated/conflicting. |
| **Consolidation** | Merges bundled skills into your existing skills. Keeps what you have, adds what's missing. | You have customizations you want to keep. |
| **Tool only** | Installs only the CLI tool. No skills are installed or modified. | You already have your own agent instructions. |
| **Abort** | Cancels installation. Nothing changes. | You changed your mind. |

### Default Behavior

**Strict mode is the default.** If you don't specify a mode, the installer will:
1. Warn you that existing opencode skills will be removed
2. Ask for confirmation before proceeding
3. Only proceed after explicit "yes"

### Installation Modes Explained

#### Strict Mode (Default)

```bash
opencode-tool install --mode strict
```

This mode:
1. Scans `~/.hermes/skills/` for any opencode-related skills
2. Lists all skills that will be removed
3. Asks for confirmation
4. Removes old skills
5. Installs bundled skills from the package

**Use this when:**
- First time installing opencode-tool
- Existing skills are outdated or conflicting
- You want a clean slate

#### Consolidation Mode

```bash
opencode-tool install --mode consolidation
```

This mode:
1. Scans existing opencode skills
2. Compares with bundled skills
3. Shows diff of what will be added/changed
4. Asks for confirmation
5. Merges bundled content into existing skills (additive only)

**Use this when:**
- You have custom rules in existing skills
- You want to keep your modifications
- You want to add missing content from bundled skills

#### Tool Only Mode

```bash
opencode-tool install --mode tool-only
```

This mode:
1. Installs only the CLI tool
2. Does NOT touch any skills
3. No confirmation needed

**Use this when:**
- You already have your own agent instructions
- You don't want skill files managed by the installer
- You prefer manual skill management

#### Abort

```bash
opencode-tool install --mode abort
# or just press Ctrl+C when prompted
```

Cancels installation. Nothing changes.

## What the Bundled Skills Teach

The bundled skills (`opencode-developer.md`, `opencode-tool.md`, and `opencode-tool-commands.md`) instruct agents to:

### Critical Rules

1. **DO NOT use `opencode` CLI directly** — Always use `opencode-tool`
2. **DO NOT use `curl` to hit the server API** — Always use `opencode-tool`
3. **ALWAYS check server status before any operation**
4. **ALWAYS use `--dir "$(pwd)"` when running tasks in a worktree**

### Forbidden vs Required

| ❌ Forbidden | ✅ Required |
|-------------|------------|
| `opencode run ...` | `opencode-tool run ...` |
| `opencode serve` | `opencode-tool server serve` |
| `curl http://localhost:4096/...` | `opencode-tool <command> ...` |
| Manual TUI interaction | `opencode-tool permission/question` commands |
| `opencode-tui model` | `opencode-tool config set ...` |

### Agent Workflow

1. **Server check first** — Always verify server is running
2. **Run task** — Use `opencode-tool run`
3. **Monitor** — Use `opencode-tool session status --monitor`
4. **Handle HITL** — Use `opencode-tool permission/question` commands
5. **Never skip steps** — Follow the complete workflow

## Quick Start

```bash
# Check server
opencode-tool server status

# Start server if needed
opencode-tool server serve

# Run a task
opencode-tool run "Implement the auth module"

# Monitor until done
opencode-tool session status <session_id> --monitor

# Handle permissions if blocked
opencode-tool permission list <session_id>
opencode-tool permission grant <session_id> once

# Handle questions if blocked
opencode-tool question get <session_id>
opencode-tool question reply <request_id> "Answer"
```

## Commands Overview

| Category | Commands |
|----------|----------|
| **Server** | `status`, `serve`, `stop` |
| **Session** | `list`, `search`, `get`, `messages`, `status`, `interrupt` |
| **Run** | `run` (new, continue, steer, queue, model switch, variant switch) |
| **Permissions** | `list`, `grant` |
| **Questions** | `get`, `reply`, `reject` |
| **Skills** | `list`, `get`, `export` |
| **Config** | `get`, `set`, `path` |

For detailed command documentation with use cases, see `opencode-tool-commands` in the bundled skills.

## Configuration

Config stored at `~/.config/opencode-tool-cli/config.json`:

```json
{
  "opencode_server_url": "http://localhost:4096",
  "monitor_retry_timeout": 60,
  "default_model": "mimo-v2.5",
  "default_variant": "high"
}
```

Environment variable `OPENCODE_SERVER_URL` takes precedence.

## Troubleshooting

### Server not reachable

```bash
# Check if server is running
opencode-tool server status

# Start server (requires opencode CLI)
opencode-tool server serve

# Check server health
curl -s http://localhost:4096/global/health
```

### Session stuck

```bash
# Check session status
opencode-tool session status <session_id>

# Monitor for blocking reasons
opencode-tool session status <session_id> --monitor

# Interrupt if needed
opencode-tool session interrupt <session_id>
```

### Permission blocked

```bash
# List pending permissions
opencode-tool permission list <session_id>

# Grant permission
opencode-tool permission grant <session_id> once
```

### Question blocked

```bash
# Get pending questions
opencode-tool question get <session_id>

# Reply to question
opencode-tool question reply <request_id> "Your answer"
```
