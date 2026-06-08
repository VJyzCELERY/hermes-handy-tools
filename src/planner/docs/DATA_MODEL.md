# Data Model

## Schema

All tables use TEXT primary keys (UUIDs) for portability and human-readability.

### projects

Top-level container for goals and tasks.

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### goals

Long-term objectives within a project. Tasks can optionally link to a goal.

```sql
CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_goals_project ON goals(project_id);
```

### tasks

The core entity. Each task belongs to a project and optionally to a goal.

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    goal_id TEXT REFERENCES goals(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    priority INTEGER NOT NULL DEFAULT 5,
    parent_task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    assignee TEXT,
    order_index INTEGER NOT NULL DEFAULT 0,
    estimated_minutes INTEGER,
    actual_minutes INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_goal ON tasks(goal_id);
CREATE INDEX idx_tasks_status ON tasks(project_id, status);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee);
```

### task_dependencies

DAG edges. Task A depends on task B means A cannot activate until B completes.

```sql
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (task_id, depends_on_id)
);

CREATE INDEX idx_deps_depends_on ON task_dependencies(depends_on_id);
```

**Cycle prevention**: Before adding a dependency, verify no cycle would be created.

### task_logs

Activity log entries.

```sql
CREATE TABLE task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'agent',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_logs_task ON task_logs(task_id);
```

### task_tags

Flexible labeling.

```sql
CREATE TABLE task_tags (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (task_id, tag)
);
```

## Relationships

```
projects 1──→ N goals
projects 1──→ N tasks
goals    1──→ N tasks (optional)
tasks    1──→ N task_dependencies (as task_id)
tasks    1──→ N task_dependencies (as depends_on_id)
tasks    1──→ N task_logs
tasks    1──→ N task_tags
tasks    1──→ N tasks (parent_task_id — subtask hierarchy)
```

## Key Queries

### Get next ready task

```sql
SELECT t.*
FROM tasks t
WHERE t.project_id = ? 
  AND t.status = 'planned'
  AND NOT EXISTS (
    SELECT 1 FROM task_dependencies td
    JOIN tasks dep ON td.depends_on_id = dep.id
    WHERE td.task_id = t.id AND dep.status != 'completed'
  )
ORDER BY t.priority ASC, t.order_index ASC
LIMIT 1;
```

### Get project status summary

```sql
SELECT status, COUNT(*) as count
FROM tasks
WHERE project_id = ?
GROUP BY status;
```

### Check for dependency cycles

```sql
WITH RECURSIVE reachability AS (
    SELECT task_id, depends_on_id, 1 as depth
    FROM task_dependencies
    WHERE task_id = ?
    UNION ALL
    SELECT r.task_id, td.depends_on_id, r.depth + 1
    FROM reachability r
    JOIN task_dependencies td ON r.depends_on_id = td.task_id
    WHERE r.depth < 100
)
SELECT 1 FROM reachability WHERE depends_on_id = ?;
```

## Migration Strategy

Schema changes via numbered migration scripts in `migrations/`:

```
migrations/
├── 001_initial.py
├── 002_add_field.py
└── ...
```

Each migration has `up(conn)` and `down(conn)` functions. Tracked in `schema_migrations` table.
