# Subproject Agents Documentation

All root-level critical rules from the root `AGENTS.md` apply to this subproject.
Read `../../AGENTS.md` before working here.

This document serves as an index for all AI agent-related documentation specific to this subproject.

## Contents
1. **[Agent Rules](docs/agents/agent_rules.md)**:
   - Detailed workflows governing AI agents in this subproject.

2. **[Examples](docs/examples/example_main.py)**:
   - Example code demonstrating the integration or functionality of agents.

## Root Critical Rules (Inherited)

- **Run start preflight** at session start
- **Never leave the project root** — this subproject is inside the repo
- **Ask before committing** — unless user grants unrestricted permission
- **Load rules dynamically** based on intent (code → 002-code-standards, tests → 003-testing, etc.)
- **Implementation starts with spec, design, tests** — always
- **Use templates** from `.agents/templates/` before generating documents
- **Run preflight scripts** before corresponding commands
- **Use `uv run` for Python** — never bare `python` or `pytest`
- **Use `gh.py` for ALL PR operations** — fall back to raw `gh` only if `gh.py` lacks the subcommand
