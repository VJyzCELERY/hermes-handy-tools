# Web UI Improvements Plan

Status: DONE
Created: 2026-06-08

## Context

The web UI (port 7749) works for basic CRUD but has gaps:
- Can't drag from Active → Blocked
- No way to set task dependencies from the UI
- Task IDs not visible on cards (needed for dep references)
- No auto-activation when a dependency completes
- No visual indication of dependency chains

---

## Changes Required

### 1. Fix Drag Transitions (db.py + dashboard.html)

**db.py** — no changes needed, `block_task()` already works from active.

**dashboard.html SortableJS handler** — currently handles:
- planned → active ✓
- planned → completed ✓
- planned → cancelled ✓
- any → planned (reset) ✓

Missing:
- active → blocked ✗
- active → completed ✓ (via modal)
- active → cancelled ✗
- blocked → active (unblock) ✗
- blocked → planned ✗
- blocked → cancelled ✗

**Fix**: Rewrite the `onEnd` handler to map `(from_status, to_status)` → API call:

```
from → to    | action
-------------|------------------
any  → planned | POST /reset
planned → active | POST /activate
planned → completed | open complete modal
planned → cancelled | POST /cancel
active → blocked | POST /block
active → completed | open complete modal
active → cancelled | POST /cancel
blocked → active | POST /activate (unblock)
blocked → planned | POST /reset
blocked → cancelled | POST /cancel
completed → planned | POST /reset
cancelled → planned | POST /reset
```

Invalid combos (same column reorder) just do `PUT /reorder`.

### 2. Show Task IDs on Cards (dashboard.html)

Add short ID display to every task card:
```html
<div class="task-meta">
    <span class="task-id">#{{ item.task.id }}</span>   <!-- NEW -->
    <span class="priority">P:{{ item.task.priority }}</span>
    ...
</div>
```

Style: monospace, subtle color, easy to copy.

### 3. Dependency Management UI (dashboard.html + app.py)

**app.py** — endpoints already exist:
- `POST /api/tasks/{id}/deps` (body: `{depends_on: "task_id"}`)
- `DELETE /api/tasks/{id}/deps/{dep_id}`

**dashboard.html** — add to each task card:
- "🔗 Deps" button opens a dependency modal
- Modal shows: current deps (with remove buttons), input to add new dep by task ID
- Show task ID picker: list of all planned tasks in project with their IDs

**New modal:**
```
┌─ Dependencies for [Task A #abc123] ─────────┐
│                                               │
│  Current dependencies:                        │
│    #def456 Task B  [✕ remove]                 │
│    #ghi789 Task C  [✕ remove]                 │
│                                               │
│  Add dependency (enter task ID):               │
│  [__________] [+ Add]                         │
│                                               │
│  Available tasks:                              │
│    #def456 Task B (planned)                    │
│    #ghi789 Task C (planned)                    │
│    #jkl012 Task D (active)                     │
│                                               │
│  [Close]                                       │
└───────────────────────────────────────────────┘
```

### 4. Auto-Activate on Complete (db.py + app.py)

**db.py** — add `_auto_activate_ready(project_id)`:
- After `complete_task()`, find all planned tasks whose deps are now met
- Activate them automatically
- Return list of newly activated tasks

**app.py** — update `api_complete_task`:
- After completing, return `activated: [...]` in response
- Frontend shows toast: "Auto-activated: Task X, Task Y"

**Flow:**
```
Task B (active) → complete
  → DB: B.status = completed
  → DB: find planned tasks where all deps are completed
  → DB: activate Task A (depends on B, B now done)
  → API returns: {completed: B, activated: [A]}
  → Frontend: toast "B completed. A auto-activated."
```

### 5. Visual Dependency Indicators (dashboard.html)

On task cards, show dep status:
- `depends on: #def456 ✓` (green, completed)
- `depends on: #def456 ▶` (blue, active)
- `depends on: #def456 ○` (gray, planned)
- `blocks: #ghi789` (show what this task blocks)

This already partially exists (`{% if item.depends_on %}`) but needs status coloring.

---

## Implementation Order

1. Fix drag transitions in SortableJS handler (quick)
2. Show task IDs on cards (quick)
3. Add `_auto_activate_ready()` to db.py
4. Update `api_complete_task` to return activated tasks
5. Add dependency modal UI
6. Add dep status coloring to task cards
7. Test end-to-end

## Files to Modify

| File | Changes |
|------|---------|
| `planner/db.py` | Add `_auto_activate_ready()`, modify `complete_task()` |
| `planner/web/app.py` | Update `api_complete_task` response |
| `planner/web/templates/dashboard.html` | Fix drag handler, add task IDs, add dep modal, add dep coloring |

## Verification

- Drag active → blocked: works
- Drag blocked → active: works
- Drag completed → planned: works (reset)
- Create Task A depends on Task B, complete B → A auto-activates
- Dependency modal: add/remove deps, see available tasks with IDs
- Task IDs visible on all cards
