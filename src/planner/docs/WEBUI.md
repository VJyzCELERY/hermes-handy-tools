# Web UI Design

## Overview

Full drag-and-drop dashboard. FastAPI + Jinja2 + Vanilla JS + SortableJS. No build step.

## Tech Stack

| Component | Technology | Source |
|-----------|-----------|--------|
| Backend | FastAPI | Python package |
| Templates | Jinja2 | FastAPI native |
| Drag-and-drop | SortableJS | CDN |
| CSS | Pico CSS | CDN |
| JS | Vanilla | Local static/ |
| Real-time | SSE | FastAPI StreamingResponse |

## Pages

### 1. Dashboard (`/`)

Project list with task counts.

```
┌─────────────────────────────────────────────────┐
│  Planner                              [+ New]    │
├─────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐              │
│  │ tinycua       │  │ handy-tools  │              │
│  │ 42 planned    │  │ 5 planned    │              │
│  │ 1 active      │  │ 0 active     │              │
│  │ 31 done       │  │ 3 done       │              │
│  │ [Open →]      │  │ [Open →]     │              │
│  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────┘
```

### 2. Project View (`/p/<project>`)

Three-column layout with drag-and-drop.

```
┌─────────────────────────────────────────────────────────────────┐
│  tinycua                                         [Settings ⚙]   │
├───────────┬───────────────┬───────────────┬─────────────────────┤
│  GOALS    │  PLANNED      │  ACTIVE       │  COMPLETED          │
│           │               │               │                     │
│  ▸ MVP    │  ┌─────────┐ │  ┌─────────┐ │  ┌─────────┐        │
│    3/5    │  │ Step 7  │←│  │ Step 6  │ │  │ Step 5  │        │
│           │  │ P:3     │ │  │ ★ RUN   │ │  │ ✓ Done  │        │
│  ▸ v2.0   │  └─────────┘ │  └─────────┘ │  └─────────┘        │
│    0/3    │  ┌─────────┐ │               │                     │
│           │  │ Step 8  │ │               │                     │
│           │  │ P:3     │ │               │                     │
│           │  └─────────┘ │               │                     │
│           │               │               │                     │
│  [+Goal]  │  [+ Task]    │               │  [Load more...]     │
├───────────┴───────────────┴───────────────┴─────────────────────┤
│  ACTIVITY LOG                                                   │
│  14:32 — Step 6 started                                         │
│  14:15 — Step 5 completed: "Review passed"                      │
└─────────────────────────────────────────────────────────────────┘
```

**Drag-and-drop**: Drag between columns. Dragging to ACTIVE triggers activation (with dependency check). Dragging within PLANNED reorders the queue.

### 3. Task Detail (`/p/<project>/t/<task_id>`)

Modal or separate page with full task view: status, priority, assignee, dependencies, body (markdown), tags, and log timeline.

### 4. Dependency Graph (`/p/<project>/graph`)

Visual DAG rendered with Canvas/SVG. Clickable nodes link to task detail.

## API Endpoints

### Projects

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List all projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{id}` | Get project details |
| PATCH | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project |

### Goals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{id}/goals` | List goals |
| POST | `/api/projects/{id}/goals` | Create goal |
| PATCH | `/api/goals/{id}` | Update goal |
| DELETE | `/api/goals/{id}` | Delete goal |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{id}/tasks` | List tasks |
| POST | `/api/projects/{id}/tasks` | Create task |
| GET | `/api/tasks/{id}` | Get task details |
| PATCH | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/activate` | Activate task |
| POST | `/api/tasks/{id}/complete` | Complete task |
| POST | `/api/tasks/{id}/block` | Block task |
| POST | `/api/tasks/{id}/cancel` | Cancel task |
| POST | `/api/tasks/{id}/log` | Add log entry |
| PATCH | `/api/tasks/{id}/move` | Move/reorder task |
| PATCH | `/api/tasks/{id}/prioritize` | Move to top |

### Dependencies

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tasks/{id}/deps` | List dependencies |
| POST | `/api/tasks/{id}/deps` | Add dependency |
| DELETE | `/api/tasks/{id}/deps/{dep_id}` | Remove dependency |

### Real-time

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events` | SSE stream for live updates |

## Drag-and-Drop Behavior

- **Reorder within Planned**: Changes `order_index`, re-indexes column
- **Move to Active**: Triggers activation with dependency check
- **Move to Completed**: Sets completed_at, clears active state
- **Blocked**: Collapsible section below main columns with block reason

## SSE Events

```json
{"event": "task.created", "data": {"id": "abc123", "project": "tinycua"}}
{"event": "task.activated", "data": {"id": "abc123"}}
{"event": "task.completed", "data": {"id": "abc123"}}
{"event": "task.moved", "data": {"id": "abc123", "from": "planned", "to": "active"}}
```

Frontend subscribes with `EventSource('/api/events')` and updates DOM accordingly.
