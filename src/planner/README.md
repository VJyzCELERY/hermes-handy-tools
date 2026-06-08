# Planner

SQLite-backed task planner with web UI and Hermes Agent integration.

## Features

- **Multi-project**: Manage multiple projects from one database
- **DAG support**: Task dependencies with linear default, parallel when possible
- **Web UI**: Full drag-and-drop dashboard with write operations
- **Hermes integration**: Native tool + orchestrator/worker roles
- **Profile assignment**: Assign tasks to specific Hermes profiles

## Installation

```bash
cd src/planner
uv sync
```

## Usage

### CLI

```bash
planner project create "my-project" --description "..."
planner task add --project my-project --title "Task 1" --body "..."
planner task activate --project my-project
planner web --port 7749
```

### Hermes Custom Tool

The planner registers as a native Hermes tool. After installation:

```bash
# 1. Install the planner
cd src/planner && uv sync

# 2. Set the project path for the tool
export PLANNER_DIR="$(pwd)"

# 3. Restart Hermes (/reset) to pick up the new tool
```

Then in Hermes:
```
planner(action="project_create", args={"name": "my-project"})
planner(action="task_add", args={"project": "my-project", "title": "Step 1"})
planner(action="task_activate", args={"project": "my-project"})
```

### Web UI

```bash
planner web --port 7749
# Open http://localhost:7749
```

The dashboard supports full read/write operations:
- **Drag-and-drop** to reorder tasks within columns
- **Cross-column drag** to change task status (planned → active → completed)
- **New Task** button to create tasks inline
- **Edit** button to modify task title, body, priority, assignee
- **Activate/Complete/Block/Cancel** buttons for status transitions
- **Delete** button to remove planned tasks

API docs available at http://localhost:7749/docs (Swagger UI).

## Documentation

See `docs/` for design documents and architecture.

- [Design Overview](docs/DESIGN.md) — Architecture and data model
- [CLI Reference](docs/CLI.md) — Command reference
- [Web UI](docs/WEBUI.md) — Dashboard design
- [Hermes Integration](docs/HERMES.md) — Custom tool, skill, orchestration
