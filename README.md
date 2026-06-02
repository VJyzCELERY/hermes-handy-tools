# Hermes Handy Tools

A collection of useful CLI tools and utilities for Hermes Agent workflows.

## Tools

| Tool | Description | Install |
|------|-------------|---------|
| [opencode-python](src/opencode-python/) | Python CLI for OpenCode server management | `cd src/opencode-python && pip install -e .` |

## Usage

After installation, each tool provides a CLI command:

```bash
# OpenCode Python CLI
opencode-python --help
opencode-python server status
opencode-python send "task"
opencode-python session status <session_id>
```

## Adding New Tools

1. Create a new directory in `src/` following the subproject template
2. Update this README to include the new tool in the table above
3. Install with `pip install -e .` from the tool's directory
