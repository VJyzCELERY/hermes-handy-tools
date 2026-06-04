# Tmux-Based Profile Isolation Design

## Problem

The current PID-based profile isolation fails for Hermes because:
1. Each `terminal()` call spawns a new shell with a different PID
2. The shell dies immediately after the command completes
3. The cleaner sees `shell_pid` as dead → kills active servers
4. Long-running generations get interrupted mid-work

## Solution

Use tmux sessions to maintain shell persistence across `terminal()` calls:
- Each profile gets its own tmux session
- The tmux session keeps the shell alive
- The PID-based `active-profile` file works because the tmux shell persists
- The cleaner can detect tmux session liveness correctly

## Architecture

```
opencode-tool run "hello"
  → no active profile
  → tmux new-session -d -s opencode-{name}
  → tmux send-keys "opencode serve --port {port}" Enter
  → wait for health check
  → set env vars (OPENCODE_TOOL_PROFILE, OPENCODE_SERVER_URL)
  → save active-profile-{tmux_pid} file
  → return session ID

opencode-tool run "world" (same Hermes session)
  → env var set → find existing profile
  → reuse server via API

Cleaner
  → check: is tmux session alive?
    yes → check last_used_at → if stale → kill tmux + delete profile
    no  → orphan → delete profile
```

## Implementation Plan

### Phase 1: Core Tmux Integration

#### 1.1 Add tmux utility functions (`opencode_tool/tmux.py`)

```python
"""Tmux session management for opencode-tool profiles."""

import subprocess
import time
from typing import Optional

def is_tmux_available() -> bool:
    """Check if tmux is installed."""
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def create_tmux_session(session_name: str) -> bool:
    """Create a new tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def send_tmux_keys(session_name: str, command: str) -> bool:
    """Send commands to a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session_name, command, "Enter"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def is_tmux_session_alive(session_name: str) -> bool:
    """Check if a tmux session is alive."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def kill_tmux_session(session_name: str) -> bool:
    """Kill a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def get_tmux_session_pid(session_name: str) -> Optional[int]:
    """Get the PID of the shell process in a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "list-phones", "-t", session_name, "-F", "#{pane_pid}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split('\n')[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None
```

#### 1.2 Update `auto_init.py` to use tmux

Changes:
- Add `tmux_session` field to server registry entries
- Create tmux session before starting opencode server
- Start opencode server inside tmux session
- Use tmux session PID for `active-profile` file
- Add `last_used_at` timestamp tracking

```python
def _auto_init_profile() -> Optional[str]:
    """Create ephemeral profile with tmux-based isolation."""
    from .tmux import (
        is_tmux_available, create_tmux_session, send_tmux_keys,
        is_tmux_session_alive, kill_tmux_session, get_tmux_session_pid
    )
    
    # Check if tmux is available
    if not is_tmux_available():
        # Fallback to current behavior (PID-based)
        return _auto_init_profile_legacy()
    
    try:
        name = generate_profile_name()
        port = find_available_port()
        tmux_session = f"opencode-{name}"
        
        # Create tmux session
        if not create_tmux_session(tmux_session):
            return None
        
        # Start opencode server inside tmux
        server_cmd = f"opencode serve --port {port} --hostname 127.0.0.1"
        if not send_tmux_keys(tmux_session, server_cmd):
            kill_tmux_session(tmux_session)
            return None
        
        # Wait for health
        url = f"http://localhost:{port}"
        if not _wait_for_health(url):
            kill_tmux_session(tmux_session)
            return None
        
        # Get tmux shell PID for active-profile file
        tmux_pid = get_tmux_session_pid(tmux_session)
        if not tmux_pid:
            kill_tmux_session(tmux_session)
            return None
        
        # Register in registry with tmux info
        server_id = register_server(
            url=url,
            port=port,
            pid=tmux_pid,
            profile_name=name,
            mode="isolated",
            tmux_session=tmux_session,
        )
        
        # Save profile env
        env_data = _fork_default_profile(name, url, port, server_id)
        env_data["tmux_session"] = tmux_session
        save_profile_env(name, env_data)
        
        # Set env vars for this process
        os.environ["OPENCODE_SERVER_URL"] = url
        os.environ["OPENCODE_SERVER_MODE"] = "isolated"
        os.environ["OPENCODE_TOOL_PROFILE"] = name
        os.environ["OPENCODE_SERVER_ID"] = server_id
        
        # Output export commands to stderr
        export_cmd = _build_export_env(name, url, "isolated", server_id)
        print(export_cmd, file=sys.stderr)
        
        # Persist active profile to file (using tmux PID)
        set_active_profile(name, tmux_pid)
        
        return name
        
    except Exception:
        return None
```

#### 1.3 Update `registry.py` to track tmux and timestamps

Add fields to server registry:
- `tmux_session`: tmux session name
- `last_used_at`: timestamp of last API call
- `created_at`: timestamp of creation

#### 1.4 Update `api.py` to refresh `last_used_at`

On every `_get`/`_post` call, update `last_used_at` timestamp in registry.

### Phase 2: Cleaner Updates

#### 2.1 Update `cleaner.py` for tmux-aware cleanup

```python
def _clean_once() -> dict:
    """Run one cleanup cycle with tmux awareness."""
    stats = {"servers_killed": 0, "profiles_deleted": 0, "registry_cleaned": 0}
    registry = load_registry()
    profiles = list_profiles()
    
    # Check servers in registry
    servers_to_remove = []
    for server in registry.get("servers", []):
        server_id = server.get("id")
        pid = server.get("pid")
        tmux_session = server.get("tmux_session")
        status = server.get("status")
        last_used_at = server.get("last_used_at", 0)
        
        # Check if server is alive
        server_alive = pid and is_pid_alive(pid)
        
        # Check if tmux session is alive (if applicable)
        tmux_alive = False
        if tmux_session:
            from .tmux import is_tmux_session_alive
            tmux_alive = is_tmux_session_alive(tmux_session)
        
        # Check if stale (not used in 10 minutes)
        stale = (time.time() - last_used_at) > 600  # 10 minutes
        
        is_orphan = False
        reason = None
        
        if status == "running" and not server_alive:
            is_orphan = True
            reason = "server dead"
        elif status == "running" and tmux_session and not tmux_alive:
            is_orphan = True
            reason = "tmux session dead"
        elif status == "running" and not tmux_session and stale:
            is_orphan = True
            reason = "stale (no tmux, no recent use)"
        
        if is_orphan:
            _log(f"Orphan server: {server_id} ({reason})")
            if server_alive:
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
            if tmux_session and tmux_alive:
                from .tmux import kill_tmux_session
                kill_tmux_session(tmux_session)
            servers_to_remove.append(server_id)
            stats["servers_killed"] += 1
    
    # ... rest of cleanup logic
```

### Phase 3: Documentation Updates

#### 3.1 Update `README.md`

Add tmux to prerequisites:
```markdown
### Prerequisites

- Python 3.11+
- tmux (for profile isolation)
- OpenCode CLI installed (for server management)
- OpenCode server running on `localhost:4096` (or set `OPENCODE_SERVER_URL`)
```

Add installation instructions for tmux:
```markdown
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
```

#### 3.2 Update bundled skills

Update `opencode-tool/SKILL.md` to document:
- Tmux-based isolation
- How it works for Hermes
- Cleanup behavior
- Troubleshooting tmux issues

#### 3.3 Update `opencode-tool.md` quick reference

Add tmux-related commands and behavior.

### Phase 4: Testing

#### 4.1 Unit tests for tmux utilities

```python
# tests/test_tmux.py
import pytest
from opencode_tool.tmux import (
    is_tmux_available, create_tmux_session, send_tmux_keys,
    is_tmux_session_alive, kill_tmux_session
)

@pytest.fixture
def tmux_available():
    return is_tmux_available()

@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
class TestTmuxSession:
    def test_create_and_kill(self):
        session_name = "test-opencode-tool"
        assert create_tmux_session(session_name)
        assert is_tmux_session_alive(session_name)
        assert kill_tmux_session(session_name)
        assert not is_tmux_session_alive(session_name)
    
    def test_send_keys(self):
        session_name = "test-opencode-tool-keys"
        create_tmux_session(session_name)
        assert send_tmux_keys(session_name, "echo hello")
        kill_tmux_session(session_name)
```

#### 4.2 Integration tests

Test full profile lifecycle with tmux:
1. Create profile → verify tmux session created
2. Run command → verify server responds
3. Run another command → verify same tmux session used
4. Kill tmux session → verify cleaner removes profile

### Phase 5: Git Operations

#### 5.1 Commit changes

```bash
cd /media/christopher-sebastian/Sad-Drive/Backups/Code/Project/hermes-handy-tools

# Stage changes
git add src/opencode-tool/

# Commit
git commit -m "feat: add tmux-based profile isolation

- Add tmux utility functions for session management
- Update auto_init.py to create tmux sessions per profile
- Add last_used_at timestamp tracking for cleanup
- Update cleaner to detect tmux session liveness
- Add tmux to prerequisites in README
- Update bundled skills with tmux documentation
- Add unit tests for tmux utilities

Solves the issue where Hermes terminal() calls create new shells
that the cleaner incorrectly marks as orphaned, interrupting
long-running generations."
```

#### 5.2 Push to GitHub

```bash
git push origin main
```

### Phase 6: Local Skill Installation

#### 6.1 Reinstall skill from local repo

```bash
# Copy updated skills to Hermes
cp /media/christopher-sebastian/Sad-Drive/Backups/Code/Project/hermes-handy-tools/src/opencode-tool/opencode_tool/skills/*.md \
   ~/.hermes/skills/software-development/

# Verify installation
ls -la ~/.hermes/skills/software-development/opencode-*.md
```

#### 6.2 Test the installation

```bash
# Verify opencode-tool works
opencode-tool --version
opencode-tool profile list

# Test tmux isolation
opencode-tool run "test" 2>&1 | head -5
```

## Migration Notes

### Backward Compatibility

- If tmux is not installed, fall back to current PID-based behavior
- Existing profiles without `tmux_session` field continue to work
- Cleaner handles both tmux and non-tmux profiles

### Configuration

No configuration changes required. Tmux isolation is automatic when tmux is available.

### Troubleshooting

If tmux sessions accumulate:
```bash
# List opencode tmux sessions
tmux list-sessions | grep opencode

# Kill all opencode sessions
tmux list-sessions | grep opencode | cut -d: -f1 | xargs -I {} tmux kill-session -t {}

# Or use opencode-tool cleanup
opencode-tool profile cleanup
```

## Timeline

- Phase 1 (Core): 2-3 hours
- Phase 2 (Cleaner): 1 hour
- Phase 3 (Docs): 1 hour
- Phase 4 (Testing): 1-2 hours
- Phase 5 (Git): 15 minutes
- Phase 6 (Install): 15 minutes

**Total:** ~6-8 hours
