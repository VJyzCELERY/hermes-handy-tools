# opencode-python

Python CLI for OpenCode server management. Replaces individual shell scripts with a unified CLI tool.

## For Agents: Installation

```bash
# Clone the repository
git clone https://github.com/VJyzCELERY/hermes-handy-tools.git
cd hermes-handy-tools/src/opencode-python

# Install in development mode
pip install -e .

# Verify installation
opencode-python --version
```

## For Agents: Getting Skills

The CLI includes built-in skills that can be exported:

```bash
# List available skills
opencode-python skills list

# Get a specific skill (outputs formatted markdown)
opencode-python skills get opencode-python-cli

# Get all skills
opencode-python skills get

# Export skills to a file
opencode-python skills export /path/to/output.md

# Export specific skill
opencode-python skills export --name opencode-python-cli /path/to/output.md

# Export to stdout (for piping)
opencode-python skills export
```

## For Agents: Quick Start

```bash
# Check server status
opencode-python server status

# Start server if not running
opencode-python server serve

# Send a message
opencode-python send "Implement the auth module"

# Check session status
opencode-python session status <session_id>

# Monitor until blocked/idle
opencode-python session status <session_id> --monitor

# Resolve permissions
opencode-python permission list --all
opencode-python permission grant <session_id> once

# Resolve questions
opencode-python question get <session_id>
opencode-python question reply <request_id> "Answer"

# Steer a session (interrupt + send)
opencode-python send -s <session_id> --steer "New direction"

# Interrupt a session
opencode-python session interrupt <session_id>

# Configuration
opencode-python config get
opencode-python config set opencode_server_url http://localhost:4096
```

## Commands Reference

### Server Management
- `opencode-python server status` - Check server status
- `opencode-python server serve` - Start server (localhost only)
- `opencode-python server stop` - Stop server (localhost only)

### Session Management
- `opencode-python session status <session_id>` - Check session status
- `opencode-python session status <session_id> --monitor` - Monitor until blocked/idle
- `opencode-python session interrupt <session_id>` - Abort a running session

### Permission Management
- `opencode-python permission list <session_id>` - List pending for session
- `opencode-python permission list --all` - List all pending
- `opencode-python permission grant <session_id> once|always|reject` - Grant permission

### Question Management
- `opencode-python question get <session_id>` - List pending questions
- `opencode-python question reply <request_id> "Answer"` - Reply to questions
- `opencode-python question reject <request_id>` - Reject question

### Send Messages
- `opencode-python send "task"` - New session
- `opencode-python send -s <session_id> "Continue"` - Continue session
- `opencode-python send -s <session_id> --steer "New dir"` - Interrupt + steer
- `opencode-python send --dir /path "task"` - With working directory
- `opencode-python send -m opencode-go/mimo-v2.5 -v high "task"` - Model + variant

### Skills Management
- `opencode-python skills list` - List available skills
- `opencode-python skills get [name]` - Get skill content
- `opencode-python skills export [file]` - Export skills to file

### Configuration
- `opencode-python config get` - Show all config
- `opencode-python config get <key>` - Get specific value
- `opencode-python config set <key> <value>` - Set config value
- `opencode-python config path` - Show config file path

## Configuration

Config stored at `~/.config/opencode-python-cli/config.json`:

```json
{
  "opencode_server_url": "http://localhost:4096"
}
```

Environment variable `OPENCODE_SERVER_URL` takes precedence.
