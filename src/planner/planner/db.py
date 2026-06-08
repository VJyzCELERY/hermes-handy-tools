"""SQLite database operations for Planner."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from planner.models import (
    Goal,
    GoalStatus,
    LogSource,
    Project,
    ProjectStatus,
    Task,
    TaskDependency,
    TaskLog,
    TaskStatus,
    _now,
    _uuid,
)

DEFAULT_DB = Path.home() / ".planner" / "planner.db"


class Database:
    """Synchronous SQLite database wrapper."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- Migration ---

    def run_migrations(self):
        """Apply all pending migrations."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

        applied = {
            row[0]
            for row in self.conn.execute("SELECT version FROM schema_migrations")
        }

        for version, sql in MIGRATIONS:
            if version not in applied:
                self.conn.executescript(sql)
                self.conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
                self.conn.commit()

    # --- Projects ---

    def create_project(self, name: str, description: str = "") -> Project:
        project = Project(name=name, description=description)
        self.conn.execute(
            "INSERT INTO projects (id, name, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project.id, project.name, project.description, project.status.value,
             project.created_at, project.updated_at),
        )
        self.conn.commit()
        return project

    def get_project(self, name: str) -> Optional[Project]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return Project(**dict(row))

    def get_project_by_id(self, project_id: str) -> Optional[Project]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return Project(**dict(row))

    def list_projects(self, status: Optional[ProjectStatus] = None) -> list[Project]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM projects WHERE status = ? ORDER BY name",
                (status.value,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM projects ORDER BY name"
            ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def archive_project(self, name: str) -> bool:
        cur = self.conn.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE name = ?",
            (ProjectStatus.ARCHIVED.value, _now(), name),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_project(self, name: str) -> bool:
        """Delete a project and all its tasks, goals, deps, logs, tags (CASCADE)."""
        cur = self.conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- Goals ---

    def create_goal(self, project_id: str, title: str, description: str = "") -> Goal:
        goal = Goal(project_id=project_id, title=title, description=description)
        self.conn.execute(
            "INSERT INTO goals (id, project_id, title, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (goal.id, goal.project_id, goal.title, goal.description,
             goal.status.value, goal.created_at, goal.updated_at),
        )
        self.conn.commit()
        return goal

    def list_goals(self, project_id: str, status: Optional[GoalStatus] = None) -> list[Goal]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM goals WHERE project_id = ? AND status = ? ORDER BY created_at",
                (project_id, status.value),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM goals WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [Goal(**dict(r)) for r in rows]

    def complete_goal(self, goal_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (GoalStatus.COMPLETED.value, _now(), goal_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # --- Tasks ---

    def create_task(
        self,
        project_id: str,
        title: str,
        body: str = "",
        priority: int = 5,
        assignee: Optional[str] = None,
        goal_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        depends_on: Optional[list[str]] = None,
    ) -> Task:
        # Get next order_index
        row = self.conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 FROM tasks WHERE project_id = ? AND status = 'planned'",
            (project_id,),
        ).fetchone()
        order_index = row[0]

        task = Task(
            project_id=project_id,
            title=title,
            body=body,
            priority=priority,
            assignee=assignee,
            goal_id=goal_id,
            order_index=order_index,
        )

        self.conn.execute(
            "INSERT INTO tasks "
            "(id, project_id, goal_id, title, body, status, priority, parent_task_id, "
            "assignee, order_index, estimated_minutes, actual_minutes, "
            "created_at, updated_at, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.project_id, task.goal_id, task.title, task.body,
             task.status.value, task.priority, task.parent_task_id, task.assignee,
             task.order_index, task.estimated_minutes, task.actual_minutes,
             task.created_at, task.updated_at, task.started_at, task.completed_at),
        )

        # Add tags
        if tags:
            for tag in tags:
                self.conn.execute(
                    "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)",
                    (task.id, tag),
                )

        # Add dependencies
        if depends_on:
            for dep_id in depends_on:
                self.conn.execute(
                    "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
                    (task.id, dep_id),
                )

        self.conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return Task(**dict(row))

    def list_tasks(
        self,
        project_id: str,
        status: Optional[TaskStatus] = None,
        assignee: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        query = "SELECT * FROM tasks WHERE project_id = ?"
        params: list = [project_id]

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)

        query += " ORDER BY priority ASC, order_index ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [Task(**dict(r)) for r in rows]

    def activate_task(self, task_id: str) -> Optional[Task]:
        """Activate a specific task."""
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.PLANNED:
            return None

        # Check dependencies
        blocked = self._get_incomplete_deps(task_id)
        if blocked:
            return None  # Still blocked

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, started_at = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.ACTIVE.value, now, now, task_id),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def find_next_ready(self, project_id: str) -> Optional[Task]:
        """Find the next planned task whose dependencies are all met."""
        planned = self.list_tasks(project_id, status=TaskStatus.PLANNED, limit=100)
        for task in planned:
            blocked = self._get_incomplete_deps(task.id)
            if not blocked:
                return task
        return None

    def activate_next(self, project_id: str) -> Optional[Task]:
        """Activate the next ready task in the queue."""
        task = self.find_next_ready(project_id)
        if task is None:
            return None
        return self.activate_task(task.id)

    def complete_task(self, task_id: str, result: str = "") -> tuple[Optional[Task], list[Task]]:
        """Complete a task and auto-activate any ready dependents.

        Returns (completed_task, list_of_newly_activated_tasks).
        """
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.ACTIVE:
            return None, []

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.COMPLETED.value, now, now, task_id),
        )

        # Log the result
        if result:
            self.conn.execute(
                "INSERT INTO task_logs (task_id, message, source, created_at) VALUES (?, ?, ?, ?)",
                (task_id, result, LogSource.AGENT.value, now),
            )

        self.conn.commit()

        # Auto-activate any planned tasks whose dependencies are now all met
        activated = self._auto_activate_ready(task.project_id)

        return self.get_task(task_id), activated

    def _auto_activate_ready(self, project_id: str) -> list[Task]:
        """Find all planned tasks with met deps and activate them."""
        activated = []
        while True:
            ready = self.find_next_ready(project_id)
            if ready is None:
                break
            t = self.activate_task(ready.id)
            if t:
                activated.append(t)
            else:
                break
        return activated

    def block_task(self, task_id: str, reason: str = "") -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.ACTIVE:
            return None

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.BLOCKED.value, now, task_id),
        )

        if reason:
            self.conn.execute(
                "INSERT INTO task_logs (task_id, message, source, created_at) VALUES (?, ?, ?, ?)",
                (task_id, f"BLOCKED: {reason}", LogSource.AGENT.value, now),
            )

        self.conn.commit()
        return self.get_task(task_id)

    def unblock_task(self, task_id: str) -> Optional[Task]:
        """Move a blocked task back to active."""
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.BLOCKED:
            return None

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.ACTIVE.value, now, task_id),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def cancel_task(self, task_id: str, reason: str = "") -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None:
            return None

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.CANCELLED.value, now, task_id),
        )

        if reason:
            self.conn.execute(
                "INSERT INTO task_logs (task_id, message, source, created_at) VALUES (?, ?, ?, ?)",
                (task_id, f"CANCELLED: {reason}", LogSource.AGENT.value, now),
            )

        self.conn.commit()
        return self.get_task(task_id)

    def reset_task(self, task_id: str) -> Optional[Task]:
        """Reset a task back to planned status (from any status)."""
        task = self.get_task(task_id)
        if task is None:
            return None

        now = _now()
        self.conn.execute(
            "UPDATE tasks SET status = ?, started_at = NULL, completed_at = NULL, "
            "updated_at = ? WHERE id = ?",
            (TaskStatus.PLANNED.value, now, task_id),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task (only planned)."""
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.PLANNED:
            return False

        self.conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
        self.conn.execute("DELETE FROM task_dependencies WHERE task_id = ? OR depends_on_id = ?", (task_id, task_id))
        self.conn.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return True

    def edit_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        priority: Optional[int] = None,
        assignee: Optional[str] = None,
    ) -> Optional[Task]:
        task = self.get_task(task_id)
        if task is None:
            return None

        updates = []
        params: list = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if body is not None:
            updates.append("body = ?")
            params.append(body)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if assignee is not None:
            updates.append("assignee = ?")
            params.append(assignee)

        if not updates:
            return task

        updates.append("updated_at = ?")
        params.append(_now())
        params.append(task_id)

        self.conn.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_task(task_id)

    def search_tasks(self, project_id: str, query: str) -> list[Task]:
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND (title LIKE ? OR body LIKE ?) "
            "ORDER BY priority ASC, order_index ASC",
            (project_id, pattern, pattern),
        ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def move_task(self, task_id: str, position: int) -> bool:
        """Move a task to a specific position in the planned queue."""
        task = self.get_task(task_id)
        if task is None or task.status != TaskStatus.PLANNED:
            return False

        # Get all planned tasks ordered
        planned = self.list_tasks(task.project_id, status=TaskStatus.PLANNED, limit=1000)
        ids = [t.id for t in planned if t.id != task_id]

        # Insert at position
        pos = max(0, min(position, len(ids)))
        ids.insert(pos, task_id)

        # Re-index
        for idx, tid in enumerate(ids):
            self.conn.execute(
                "UPDATE tasks SET order_index = ?, updated_at = ? WHERE id = ?",
                (idx, _now(), tid),
            )

        self.conn.commit()
        return True

    def prioritize_task(self, task_id: str) -> bool:
        """Move a task to the top of the queue."""
        return self.move_task(task_id, 0)

    # --- Dependencies ---

    def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        # Check both tasks exist
        if self.get_task(task_id) is None or self.get_task(depends_on_id) is None:
            return False

        # Check for cycles
        if self._would_create_cycle(task_id, depends_on_id):
            return False

        try:
            self.conn.execute(
                "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
                (task_id, depends_on_id),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already exists

    def remove_dependency(self, task_id: str, depends_on_id: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM task_dependencies WHERE task_id = ? AND depends_on_id = ?",
            (task_id, depends_on_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def list_dependencies(self, task_id: str) -> dict[str, list[str]]:
        """Return {depends_on: [...], blocked_by: [...]}."""
        depends_on = [
            row[0]
            for row in self.conn.execute(
                "SELECT depends_on_id FROM task_dependencies WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        ]
        blocked_by = [
            row[0]
            for row in self.conn.execute(
                "SELECT task_id FROM task_dependencies WHERE depends_on_id = ?",
                (task_id,),
            ).fetchall()
        ]
        return {"depends_on": depends_on, "blocked_by": blocked_by}

    def _get_incomplete_deps(self, task_id: str) -> list[str]:
        """Return IDs of incomplete tasks that this task depends on."""
        rows = self.conn.execute(
            "SELECT td.depends_on_id FROM task_dependencies td "
            "JOIN tasks t ON td.depends_on_id = t.id "
            "WHERE td.task_id = ? AND t.status != ?",
            (task_id, TaskStatus.COMPLETED.value),
        ).fetchall()
        return [row[0] for row in rows]

    def _would_create_cycle(self, task_id: str, depends_on_id: str) -> bool:
        """Check if adding this dependency would create a cycle."""
        # BFS from depends_on_id following existing edges backwards
        # If we reach task_id, it's a cycle
        visited = set()
        queue = [depends_on_id]

        while queue:
            current = queue.pop(0)
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            # Find what current depends on
            rows = self.conn.execute(
                "SELECT depends_on_id FROM task_dependencies WHERE task_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                queue.append(row[0])

        return False

    # --- Logs ---

    def add_log(self, task_id: str, message: str, source: LogSource = LogSource.AGENT) -> TaskLog:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO task_logs (task_id, message, source, created_at) VALUES (?, ?, ?, ?)",
            (task_id, message, source.value, now),
        )
        self.conn.commit()
        return TaskLog(id=cur.lastrowid, task_id=task_id, message=message, source=source, created_at=now)

    def get_logs(self, task_id: str, limit: int = 50) -> list[TaskLog]:
        rows = self.conn.execute(
            "SELECT * FROM task_logs WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
            (task_id, limit),
        ).fetchall()
        return [TaskLog(**dict(r)) for r in reversed(rows)]

    # --- Tags ---

    def add_tag(self, task_id: str, tag: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)",
                (task_id, tag),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_tags(self, task_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT tag FROM task_tags WHERE task_id = ?", (task_id,)
        ).fetchall()
        return [row[0] for row in rows]

    # --- Status summary ---

    def get_project_status(self, project_id: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM tasks WHERE project_id = ? GROUP BY status",
            (project_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_active_task(self, project_id: str) -> Optional[Task]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = ? LIMIT 1",
            (project_id, TaskStatus.ACTIVE.value),
        ).fetchall()
        if rows:
            return Task(**dict(rows[0]))
        return None


# --- Schema ---

MIGRATIONS = [
    (1, """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

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

        CREATE TABLE task_dependencies (
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            depends_on_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (task_id, depends_on_id)
        );
        CREATE INDEX idx_deps_depends_on ON task_dependencies(depends_on_id);

        CREATE TABLE task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'agent',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX idx_logs_task ON task_logs(task_id);

        CREATE TABLE task_tags (
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            PRIMARY KEY (task_id, tag)
        );
    """),
]
