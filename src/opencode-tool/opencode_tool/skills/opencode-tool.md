---
name: opencode-tool
description: "Quick CLI command reference for opencode-tool — profile system, HITL, session management."
version: 1.2.0
author: hermes
platforms: [linux, macos, wsl]
metadata:
  hermes:
    tags: [opencode, cli, reference, quick]
    related_skills: [opencode-developer, opencode-tool-commands]
---

# OpenCode Python CLI — Quick Reference

**⚠️ Testing:** Use `uv run --project . -m opencode_tool.main` from project dir.

---

## ⛔ Critical Rules

1. **ALWAYS use `opencode-tool`** — NEVER `opencode` CLI or `curl`
2. **Profile-first** — Every command runs in a profile
3. **Default profile** — Auto-created from config, connects to existing server

---

## Profile System

**One profile = one opencode server connection (with tmux isolation).**

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

# Clean orphaned profiles
opencode-tool profile cleanup
opencode-tool profile cleanup --dry-run

# Initialize default profile (from config)
opencode-tool profile init
```

**How profiles work:**
- First command auto-creates profile if none active
- **With tmux (recommended):** Each profile gets its own tmux session
  - Tmux session keeps shell alive across `terminal()` calls
  - PID-based `active-profile` file works correctly
  - Cleaner detects tmux session liveness for safe cleanup
- **Without tmux (legacy):** Each shell gets its own profile (PID-based)
  - Profile persists to `~/.opencode-tool/active-profile-<pid>`
  - ⚠️ Fails for Hermes: each `terminal()` call creates new PID
- Default profile connects to config URL (http://localhost:4096)
- New profiles fork settings from default

### Tmux Isolation (Recommended)

```bash
# tmux must be installed for automatic isolation
tmux -V  # Check if tmux is installed

# Install tmux (if not installed)
sudo apt-get install tmux  # Ubuntu/Debian
brew install tmux          # macOS
sudo pacman -S tmux        # Arch Linux
```

**How it works:**

1. `opencode-tool run "task"` → creates tmux session `opencode-{name}`
2. Starts opencode server inside tmux: `opencode serve --port {port}`
3. Sets env vars: `OPENCODE_SERVER_URL`, `OPENCODE_TOOL_PROFILE`
4. Subsequent calls reuse the same profile via env vars
5. Tmux session stays alive until:
   - Profile is terminated: `opencode-tool profile terminate <name>`
   - Cleaner detects staleness: `last_used_at` > 10 minutes
   - Tmux session is killed externally

**Benefits for Hermes:**

- Shell PID persists across `terminal()` calls (it's the tmux shell)
- Cleaner won't kill active servers mid-generation
- Multiple Hermes sessions can run concurrently

### Legacy PID-Based Isolation (Without tmux)

⚠️ **Not recommended for Hermes** — each `terminal()` call creates a new shell with a new PID, causing the cleaner to mark active profiles as orphaned.

**Workaround if tmux is not available:**

```python
# Must chain commands to preserve env vars
terminal(command='eval "$(opencode-tool run \'task1\' 2>&1 >/dev/null)" && opencode-tool run \'task2\'')
```

---

## Two Ways to Get a Server

**Option 1: Connect to existing server**
```bash
opencode-tool profile init              # creates default profile
# or
opencode-tool profile set --collaborate myuser --url http://localhost:4096
```

**Option 2: Start new server**
```bash
opencode-tool profile set myproject     # auto-starts on random port
```

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
opencode-tool hitl detect <sid>
opencode-tool hitl detect <sid> --wait
opencode-tool hitl respond <sid> "yes"       # answer question
opencode-tool hitl respond <sid> once         # grant permission
opencode-tool hitl respond <sid> reject       # reject
opencode-tool hitl dismiss <sid>              # stop agent
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

## Config

```bash
opencode-tool config get
opencode-tool config set <key> <value>
```

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

# Clean up
opencode-tool profile cleanup
```
