# Planner

SQLite-backed task planner with web UI and Hermes Agent integration.

## Features

- **Multi-project**: Manage multiple projects from one database
- **DAG support**: Task dependencies with linear default, parallel when possible
- **Web UI**: Full drag-and-drop dashboard
- **Hermes integration**: Orchestrator/worker roles, background execution
- **Profile assignment**: Assign tasks to specific Hermes profiles

## Installation

```bash
cd src/planner
uv sync
```

## Usage

```bash
planner project create "my-project" --description "..."
planner task add --project my-project --title "Task 1" --body "..."
planner task activate --project my-project
planner web --port 8080
```

## Documentation

See `docs/` for design documents and architecture.
