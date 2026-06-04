# opencode-tool Profile & Server Lifecycle Design v4

## Core Concept: Profiles with Auto-Init

Every opencode-tool operation runs within a **profile**.
A profile = a named configuration + its own server instance.

## Shell Session Tracking

Environment variable: `OPENCODE_TOOL_PROFILE`

```
  Set → this shell has an active profile (all commands use it)
  Not set → no active profile (commands auto-initialize)
```

Set via:
```bash
eval $(opencode-tool profile set)           # auto-generated name
eval $(opencode-tool profile set myproject) # specific name
```

## Auto-Initialization

When ANY opencode-tool command runs (except `profile set`):

```
  1. Check OPENCODE_TOOL_PROFILE env var
  2. If set → use that profile
  3. If not set → auto-initialize:
     a. Generate random profile name (e.g., "coral-fox-42")
     b. Create profile directory
     c. Find available port
     d. Start server
     e. Register in registry
     f. Execute the command
```

The auto-initialized profile is ephemeral — it runs the command
but doesn't set the shell env var. If you want persistence across
commands, use `profile set` first.

## Profile Lifecycle

### profile set (renamed from switch)

```bash
# Create new profile with random name
eval $(opencode-tool profile set)

# Create with specific name
eval $(opencode-tool profile set myproject)

# Create collaborate profile
eval $(opencode-tool profile set --collaborate myuser)

# Connect to specific server
eval $(opencode-tool profile set --collaborate myuser --url http://localhost:4096)
```

Output (for eval):
```bash
export OPENCODE_SERVER_URL=http://localhost:12345
export OPENCODE_SERVER_ID=server_abc123
export OPENCODE_SERVER_MODE=isolated
export OPENCODE_TOOL_PROFILE=myproject
```

### profile create (alias for set, without eval output)

```bash
# Create profile (no env output)
opencode-tool profile create myproject

# Create with options
opencode-tool profile create myproject --port 12345
opencode-tool profile create myproject --from .env
```

### profile list / status / delete / current

```bash
opencode-tool profile list          # all profiles
opencode-tool profile status [name] # profile details
opencode-tool profile delete name   # remove profile
opencode-tool profile current       # show active profile
```

## Random Name Generation

Format: `<adjective>-<noun>-<number>`

```python
ADJECTIVES = ["coral", "amber", "jade", "ruby", "onyx", "pearl", "ivory", ...]
NOUNS = ["fox", "hawk", "lynx", "wolf", "bear", "deer", "hawk", ...]

def generate_profile_name() -> str:
    import random
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    num = random.randint(1, 999)
    return f"{adj}-{noun}-{num}"
```

## Port Conflict Detection

```python
def find_available_port(start: int = 16384, max_attempts: int = 100) -> int:
    """Find an available port."""
    import socket

    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RuntimeError(f"No available port in {start}-{start+max_attempts}")

def is_port_available(port: int, registry: dict) -> bool:
    """Check port is free (OS + registry)."""
    # Check OS
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False

    # Check registry
    for server in registry.get("servers", []):
        if server.get("port") == port and server.get("status") == "running":
            return False

    return True
```

## Flow Examples

### Example 1: Fresh shell, auto-init

```bash
# Shell opens — no env var set
$ opencode-tool run "analyze this code"

# Auto-initializes:
# 1. Generate name: "amber-lynx-742"
# 2. Create profile at ~/.opencode-tool/profiles/amber-lynx-742/
# 3. Find port: 16384 (free)
# 4. Start server on :16384
# 5. Register in registry
# 6. Execute command
# 7. Return result

# Note: OPENCODE_TOOL_PROFILE is NOT set in shell
# Next command will auto-init again (ephemeral)
```

### Example 2: Persistent profile

```bash
$ eval $(opencode-tool profile set myproject)
Profile created: myproject
Server started on port 12345
export OPENCODE_SERVER_URL=http://localhost:12345
export OPENCODE_TOOL_PROFILE=myproject

$ opencode-tool run "fix the bug"
# Uses myproject profile → server on :12345

$ opencode-tool run "now test it"
# Same profile → same server
```

### Example 3: Collaboration

```bash
$ eval $(opencode-tool profile set --collaborate myuser)
Connected to existing server at http://localhost:4096
export OPENCODE_SERVER_URL=http://localhost:4096
export OPENCODE_SERVER_MODE=collaborate
export OPENCODE_TOOL_PROFILE=myuser

$ opencode-tool hitl detect ses_abc123
# Uses REST API only (collaborate mode)
```

### Example 4: Random name

```bash
$ eval $(opencode-tool profile set)
Profile created: coral-fox-42
Server started on port 23456
export OPENCODE_SERVER_URL=http://localhost:23456
export OPENCODE_TOOL_PROFILE=coral-fox-42
```

## Commands

### profile group
```bash
opencode-tool profile set [name] [--port PORT] [--dir PATH]
                               [--collaborate NAME [--url URL]]
                               [--from .env]
opencode-tool profile create [name] [same options as set]
opencode-tool profile list
opencode-tool profile status [name]
opencode-tool profile delete <name>
opencode-tool profile current
```

### env group (simplified)
```bash
opencode-tool env get        # show current profile env
opencode-tool env clear      # deactivate profile
opencode-tool env load .env  # load .env into profile
```

### server group (enhanced)
```bash
opencode-tool server start [--port PORT] [--dir PATH]
opencode-tool server stop [<server_id> | --all]
opencode-tool server list
opencode-tool server status [<server_id>]
```

### hitl group (unchanged)
```bash
opencode-tool hitl detect <session_id> [--json]
opencode-tool hitl respond <session_id> <answer> [--json]
opencode-tool hitl dismiss <session_id> [--json]
```

## Auto-Init Detection

```python
def get_active_profile() -> Optional[str]:
    """Check if shell has active profile."""
    return os.environ.get("OPENCODE_TOOL_PROFILE")

def auto_init_profile() -> str:
    """Create ephemeral profile, return name."""
    name = generate_profile_name()
    # Create profile directory
    # Find available port
    # Start server
    # Register in registry
    # Return name (NOT set in env)
    return name

def ensure_profile() -> str:
    """Get or create profile. Returns profile name."""
    profile = get_active_profile()
    if profile:
        return profile
    return auto_init_profile()
```

## File Structure

```
~/.opencode-tool/
├── profiles/
│   ├── default/
│   │   ├── env.json
│   │   └── .env
│   ├── myproject/
│   │   ├── env.json
│   │   └── .env
│   └── coral-fox-42/
│       ├── env.json
│       └── .env
├── registry.json
└── config.json

~/.config/opencode-tool-cli/
└── config.json
```

## Implementation Order

Phase 1: Profile system (set/create/list/delete/current)
Phase 2: Registry + port detection
Phase 3: Server lifecycle (start/stop) with port conflict handling
Phase 4: Auto-init on command run
Phase 5: HITL commands (mode-aware)

## Config Updates

```python
DEFAULT_CONFIG = {
    # Existing
    "opencode_server_url": "http://localhost:4096",
    "monitor_retry_timeout": 60,
    "default_model": "mimo-v2.5",
    "default_variant": "high",
    # New
    "auto_init": True,              # Auto-create profile if none active
    "default_port_start": 16384,    # Start of port range
    "max_port_attempts": 100,       # Max port conflict retries
    "registry_cleanup_hours": 24,   # Remove stopped servers after N hours
}
```
