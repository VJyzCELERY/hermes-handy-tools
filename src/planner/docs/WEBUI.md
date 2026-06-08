# Web UI Design

## Overview

Full drag-and-drop dashboard with read/write operations. FastAPI + Jinja2 + Vanilla JS + SortableJS. No build step.

**Default port: 7749**

## Tech Stack

| Component | Technology | Source |
|-----------|-----------|--------|
| Backend | FastAPI | Python package |
| Templates | Jinja2 | FastAPI native |
| Drag-and-drop | SortableJS | CDN |
| CSS | Pico CSS | CDN |
| JS | Vanilla | Inline in template |

## Pages

### Dashboard (`/`)

Single-page view with project tabs, status columns, and task cards.

```
┌──────────────────────────────────────────────────────────────────┐
│  📋 Planner — tinycua                    [API Docs]              │
│  [tinycua] [handy-tools]                                         │
├──────────────────────────────────────────────────────────────────┤
│  42 planned   1 active   31 completed   2 blocked                │
│  [+ New Task]                                                     │
├──────────────┬──────────────┬──────────────┬─────────────────────┤
│  PLANNED     │  ACTIVE      │  BLOCKED     │  COMPLETED          │
│              │              │              │                     │
│  ┌─────────┐ │  ┌─────────┐ │  ┌─────────┐ │  ┌─────────┐       │
│  │ Step 7  │ │  │ Step 6  │ │  │ Step 9  │ │  │ Step 5  │       │
│  │ P:3     │ │  │ ★ RUN   │ │  │ (blocked)│ │  │ ✓ Done  │       │
│  │ @worker │ │  └─────────┘ │  └─────────┘ │  └─────────┘       │
│  │[▶][✏][✕]│ │  [✓][⏸][✕]  │  [▶][✕]      │                     │
│  └─────────┘ │              │              │                     │
│  ┌─────────┐ │              │              │                     │
│  │ Step 8  │ │              │              │                     │
│  └─────────┘ │              │              │                     │
└──────────────┴──────────────┴──────────────┴─────────────────────┘
```

### Features

- **Drag-and-drop reorder**: Sort tasks within Planned column
- **Cross-column drag**: Move tasks between status columns
- **Inline actions**: Activate, complete, block, cancel, edit, delete buttons
- **New Task modal**: Create tasks with title, body, priority, assignee, tags
- **Edit modal**: Modify task fields in-place
- **Complete modal**: Add result summary when completing
- **Project tabs**: Switch between projects
- **Status bar**: Quick counts per status
- **Keyboard**: Escape closes modals

## API Endpoints

### Projects

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all projects |
| GET | `/api/projects/{name}` | Get project details + counts |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{name}/tasks` | List tasks (filterable by status/assignee) |
| GET | `/api/tasks/{id}` | Get task details + deps + logs |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Edit task fields |
| PUT | `/api/tasks/{id}/reorder` | Move task to position |
| POST | `/api/tasks/{id}/activate` | Activate task |
| POST | `/api/tasks/{id}/complete` | Complete task (with result) |
| POST | `/api/tasks/{id}/block` | Block task (with reason) |
| POST | `/api/tasks/{id}/cancel` | Cancel task |
| DELETE | `/api/tasks/{id}` | Delete planned task |
| POST | `/api/tasks/{id}/log` | Add log entry |

### Dependencies

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tasks/{id}/deps` | Add dependency |
| DELETE | `/api/tasks/{id}/deps/{dep_id}` | Remove dependency |

## Drag-and-Drop Behavior

- **Reorder within Planned**: Changes `order_index`, re-indexes column
- **Move to Active**: Triggers activation with dependency check
- **Move to Completed**: Shows completion modal for result summary
- **Move to Cancelled**: Cancels the task
- **Failed moves**: Toast notification with error reason

## Planned (Not Yet Implemented)

- SSE real-time updates (`/api/events`)
- Dependency graph visualization
- Separate task detail page
- Goal management in UI
- Activity log panel
