# Planner Subproject Agents Documentation

All root-level critical rules from the root `AGENTS.md` apply to this subproject.
Read `../../AGENTS.md` before working here.

## Contents

1. **[Design Overview](docs/DESIGN.md)** — Architecture and data model
2. **[CLI Reference](docs/CLI.md)** — Command reference
3. **[Web UI](docs/WEBUI.md)** — Dashboard design
4. **[Hermes Integration](docs/HERMES.md)** — Skills, roles, orchestration

## Root Critical Rules (Inherited)

- **Run start preflight** at session start
- **Never leave the project root** — this subproject is inside the repo
- **Ask before committing** — unless user grants unrestricted permission
- **Load rules dynamically** based on intent
- **Implementation starts with spec, design, tests** — always
- **Use `uv run` for Python** — never bare `python` or `pytest`
