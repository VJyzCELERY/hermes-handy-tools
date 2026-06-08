# Design Overview

## What is Planner?

Planner is a SQLite-backed task management system for Hermes Agent workflows. It replaces the markdown-based development-log system with a proper database, while keeping the same philosophical workflow: plan → activate → execute → complete.

## Why?

The existing development-log system uses stacked markdown files with regex-based parsing. This causes:

- **Brittle parsing** — manual edits silently break the system
- **No atomic operations** — concurrent agents can corrupt files
- **Poor performance** — 800KB files parsed on every operation
- **No task dependencies** — can't express "B depends on A"
- **No web UI** — only CLI/script access
- **Roles are convention** — orchestrator/worker behavior isn't enforced

Planner fixes all of these with SQLite storage, proper data models, and a web dashboard.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Planner                        │
├─────────────┬─────────────┬─────────────────────┤
│   CLI       │   Web UI    │   Hermes Skill      │
│  (Click)    │  (FastAPI)  │   (SKILL.md)        │
├─────────────┴─────────────┴─────────────────────┤
│              Core (db.py, models.py)             │
├─────────────────────────────────────────────────┤
│              SQLite Database                     │
└─────────────────────────────────────────────────┘
```

### Components

1. **CLI** (`cli.py`) — Click-based command line interface
2. **Core** (`db.py`, `models.py`) — Database operations and data models
3. **Web UI** (`web/`) — FastAPI + Jinja2 + SortableJS dashboard
4. **Skill** (`skill/`) — Hermes Agent integration instructions

### Data Flow

```
User/Hermes → CLI/API → Core → SQLite
                         ↓
                    Web UI (reads)
```

## Data Model

See [DATA_MODEL.md](DATA_MODEL.md) for full schema.

### Key Entities

- **Project** — Top-level container (e.g., "tinycua", "handy-tools")
- **Goal** — Long-term objective within a project
- **Task** — Unit of work with status, priority, assignee
- **Dependency** — DAG edge between tasks
- **Log** — Activity record for a task
- **Tag** — Flexible labeling (milestone, step, etc.)

### Status Flow

```
planned ──→ active ──→ completed
   │           │
   │           ├──→ blocked (with reason)
   │           │
   │           └──→ cancelled
   │
   └──→ cancelled
```

## Task Activation Rules

### Linear Mode (Default)

- One active task at a time
- FIFO queue: top of planned = next
- Priority overrides order (lower number = higher priority)

### Parallel Mode (When Dependencies Allow)

- Multiple tasks can be active simultaneously
- A task can activate only when ALL its dependencies are completed
- System finds ready tasks (no unmet deps) and activates them

### Activation Algorithm

```python
def find_next_ready(project_id):
    """Find the next task that can be activated."""
    planned = get_planned_tasks(project_id, order_by=("priority", "order_index"))
    
    for task in planned:
        deps = get_dependencies(task.id)
        if all(dep.status == "completed" for dep in deps):
            return task
    
    return None  # No ready tasks (blocked by dependencies)
```

## Directory Structure

```
src/planner/
├── __init__.py
├── cli.py              # Click CLI entry point
├── db.py               # SQLite operations
├── models.py           # Pydantic models
├── orchestrator.py     # Orchestrator/worker role logic
├── web/
│   ├── __init__.py
│   ├── app.py          # FastAPI app
│   ├── api.py          # REST API endpoints
│   ├── static/         # JS/CSS (SortableJS, vanilla JS)
│   └── templates/      # Jinja2 HTML
├── migrations/         # Schema migrations
├── skill/              # Hermes skill files
│   └── SKILL.md
├── docs/               # This documentation
│   ├── DESIGN.md       # This file
│   ├── DATA_MODEL.md   # Database schema
│   ├── CLI.md          # Command reference
│   ├── WEBUI.md        # Dashboard design
│   └── HERMES.md       # Integration guide
└── tests/
    ├── unit/
    └── integration/
```

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Storage | SQLite via `aiosqlite` | Atomic, concurrent-safe, zero-config |
| CLI | Click | Mature, composable, type-safe |
| Web backend | FastAPI | Async, auto-docs, Pydantic integration |
| Web frontend | Vanilla JS + SortableJS | No build step, lightweight |
| CSS | Pico CSS (CDN) | Minimal, classless, clean |
| Templates | Jinja2 | FastAPI native, simple |
| Models | Pydantic v2 | Validation, serialization, CLI integration |

## Migration from Development-Log

The old system stays untouched. A future `planner import` command will read existing dev-log markdown files and populate the SQLite database. This is deferred — start fresh, handle migration later.

## Design Principles

1. **Simple first** — SQLite over Postgres, vanilla JS over React
2. **Owned by you** — not a Hermes built-in, fully customizable
3. **Roles built-in** — orchestrator/worker enforced by the system
4. **DAG-capable** — linear by default, parallel when possible
5. **Web UI as first-class** — not an afterthought
6. **Skill-bundled** — installation gives you CLI + skill together
