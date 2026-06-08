"""Planner CLI — Click-based command line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from planner.db import Database, DEFAULT_DB
from planner.models import GoalStatus, ProjectStatus, TaskStatus


def get_db(db_path: Optional[str]) -> Database:
    db = Database(db_path)
    db.run_migrations()
    return db


def output(data, quiet: bool = False, as_json: bool = False):
    """Print output as text or JSON."""
    if quiet:
        return
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, str):
            click.echo(data)
        elif isinstance(data, list):
            for item in data:
                click.echo(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")


@click.group()
@click.option("--db", "db_path", default=None, help="Database file path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", is_flag=True, help="Suppress output")
@click.pass_context
def main(ctx, db_path, as_json, quiet):
    """Planner — SQLite-backed task planner."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["as_json"] = as_json
    ctx.obj["quiet"] = quiet


# ─── Project ──────────────────────────────────────────────────────────────────

@main.group()
def project():
    """Manage projects."""
    pass


@project.command("create")
@click.argument("name")
@click.option("--description", "-d", default="")
@click.pass_context
def project_create(ctx, name, description):
    """Create a new project."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.create_project(name, description)
        output(f"Created project: {p.name} ({p.id})", **_flags(ctx))


@project.command("list")
@click.option("--status", type=click.Choice(["active", "archived"]), default=None)
@click.pass_context
def project_list(ctx, status):
    """List all projects."""
    with get_db(ctx.obj["db_path"]) as db:
        s = ProjectStatus(status) if status else None
        projects = db.list_projects(s)
        if ctx.obj["as_json"]:
            output([{"id": p.id, "name": p.name, "status": p.status.value} for p in projects], **_flags(ctx))
        else:
            if not projects:
                output("No projects found.", **_flags(ctx))
                return
            header = f"{'NAME':<20} {'STATUS':<10} {'ID':<10}"
            output(header, **_flags(ctx))
            output("-" * len(header), **_flags(ctx))
            for p in projects:
                output(f"{p.name:<20} {p.status.value:<10} {p.id:<10}", **_flags(ctx))


@project.command("show")
@click.argument("name")
@click.pass_context
def project_show(ctx, name):
    """Show project details with task counts."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(name)
        if not p:
            output(f"Project not found: {name}", **_flags(ctx))
            sys.exit(1)

        counts = db.get_project_status(p.id)
        goals = db.list_goals(p.id)
        active = db.get_active_task(p.id)

        if ctx.obj["as_json"]:
            output({
                "id": p.id, "name": p.name, "description": p.description,
                "status": p.status.value, "task_counts": counts,
                "goal_count": len(goals),
                "active_task": {"id": active.id, "title": active.title} if active else None,
            }, **_flags(ctx))
        else:
            output(f"Project: {p.name} ({p.id})", **_flags(ctx))
            output(f"  Status: {p.status.value}", **_flags(ctx))
            if p.description:
                output(f"  Description: {p.description}", **_flags(ctx))
            output(f"  Goals: {len(goals)}", **_flags(ctx))
            output(f"  Tasks: {counts}", **_flags(ctx))
            if active:
                output(f"  Active: [{active.id}] {active.title}", **_flags(ctx))
            else:
                output("  Active: (none)", **_flags(ctx))


@project.command("archive")
@click.argument("name")
@click.pass_context
def project_archive(ctx, name):
    """Archive a project."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.archive_project(name):
            output(f"Archived: {name}", **_flags(ctx))
        else:
            output(f"Project not found: {name}", **_flags(ctx))
            sys.exit(1)


# ─── Goal ─────────────────────────────────────────────────────────────────────

@main.group()
def goal():
    """Manage goals."""
    pass


@goal.command("add")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--title", "-t", required=True)
@click.option("--description", "-d", default="")
@click.pass_context
def goal_add(ctx, project_name, title, description):
    """Add a goal to a project."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)
        g = db.create_goal(p.id, title, description)
        output(f"Created goal: [{g.id}] {g.title}", **_flags(ctx))


@goal.command("list")
@click.option("--project", "-p", "project_name", required=True)
@click.pass_context
def goal_list(ctx, project_name):
    """List goals for a project."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)
        goals = db.list_goals(p.id)
        if ctx.obj["as_json"]:
            output([{"id": g.id, "title": g.title, "status": g.status.value} for g in goals], **_flags(ctx))
        else:
            if not goals:
                output("No goals.", **_flags(ctx))
                return
            for g in goals:
                output(f"  [{g.id}] {g.title} ({g.status.value})", **_flags(ctx))


@goal.command("complete")
@click.argument("goal_id")
@click.pass_context
def goal_complete(ctx, goal_id):
    """Mark a goal as completed."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.complete_goal(goal_id):
            output(f"Goal completed: {goal_id}", **_flags(ctx))
        else:
            output(f"Goal not found: {goal_id}", **_flags(ctx))
            sys.exit(1)


# ─── Task ─────────────────────────────────────────────────────────────────────

@main.group()
def task():
    """Manage tasks."""
    pass


@task.command("add")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--title", "-t", required=True)
@click.option("--body", "-b", default="")
@click.option("--priority", default=5, type=int)
@click.option("--assignee", "-a", default=None)
@click.option("--tag", multiple=True)
@click.option("--after", multiple=True, help="Task ID this depends on")
@click.pass_context
def task_add(ctx, project_name, title, body, priority, assignee, tag, after):
    """Add a task to the planned queue."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)
        t = db.create_task(
            p.id, title, body, priority, assignee,
            tags=list(tag) if tag else None,
            depends_on=list(after) if after else None,
        )
        output(f"Created task: [{t.id}] {t.title} (priority={t.priority})", **_flags(ctx))


@task.command("list")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--status", type=click.Choice(["planned", "active", "completed", "blocked", "cancelled"]))
@click.option("--assignee", "-a", default=None)
@click.option("--limit", default=20, type=int)
@click.option("--offset", default=0, type=int)
@click.pass_context
def task_list(ctx, project_name, status, assignee, limit, offset):
    """List tasks for a project."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)
        s = TaskStatus(status) if status else None
        tasks = db.list_tasks(p.id, s, assignee, limit, offset)

        if ctx.obj["as_json"]:
            output([
                {"id": t.id, "title": t.title, "status": t.status.value,
                 "priority": t.priority, "assignee": t.assignee}
                for t in tasks
            ], **_flags(ctx))
        else:
            if not tasks:
                output("No tasks.", **_flags(ctx))
                return
            for t in tasks:
                assign = f" @{t.assignee}" if t.assignee else ""
                output(f"  [{t.id}] {t.title} (P:{t.priority} {t.status.value}{assign})", **_flags(ctx))


@task.command("show")
@click.argument("task_id")
@click.pass_context
def task_show(ctx, task_id):
    """Show full task details."""
    with get_db(ctx.obj["db_path"]) as db:
        t = db.get_task(task_id)
        if not t:
            output(f"Task not found: {task_id}", **_flags(ctx))
            sys.exit(1)

        deps = db.list_dependencies(t.id)
        tags = db.get_tags(t.id)
        logs = db.get_logs(t.id)

        if ctx.obj["as_json"]:
            output({
                "id": t.id, "title": t.title, "body": t.body,
                "status": t.status.value, "priority": t.priority,
                "assignee": t.assignee, "tags": tags,
                "depends_on": deps["depends_on"],
                "blocked_by": deps["blocked_by"],
                "logs": [{"message": l.message, "source": l.source.value, "at": l.created_at} for l in logs],
            }, **_flags(ctx))
        else:
            output(f"[{t.id}] {t.title}", **_flags(ctx))
            output(f"  Status: {t.status.value}  Priority: {t.priority}", **_flags(ctx))
            if t.assignee:
                output(f"  Assignee: {t.assignee}", **_flags(ctx))
            if tags:
                output(f"  Tags: {', '.join(tags)}", **_flags(ctx))
            if deps["depends_on"]:
                output(f"  Depends on: {', '.join(deps['depends_on'])}", **_flags(ctx))
            if deps["blocked_by"]:
                output(f"  Blocks: {', '.join(deps['blocked_by'])}", **_flags(ctx))
            if t.body:
                output(f"  Body:", **_flags(ctx))
                for line in t.body.split("\n"):
                    output(f"    {line}", **_flags(ctx))
            if logs:
                output(f"  Logs:", **_flags(ctx))
                for l in logs:
                    output(f"    [{l.created_at}] {l.message}", **_flags(ctx))


@task.command("activate")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--task-id", default=None, help="Specific task to activate")
@click.pass_context
def task_activate(ctx, project_name, task_id):
    """Activate the next ready task, or a specific task."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)

        if task_id:
            t = db.activate_task(task_id)
        else:
            t = db.activate_next(p.id)

        if not t:
            output("No ready tasks to activate.", **_flags(ctx))
            sys.exit(1)

        output(f"Activated: [{t.id}] {t.title}", **_flags(ctx))


@task.command("complete")
@click.option("--result", "-r", default="")
@click.pass_context
def task_complete(ctx, result):
    """Complete the active task."""
    with get_db(ctx.obj["db_path"]) as db:
        # Find the active task across all projects
        rows = db.conn.execute(
            "SELECT * FROM tasks WHERE status = 'active' LIMIT 1"
        ).fetchall()
        if not rows:
            output("No active task to complete.", **_flags(ctx))
            sys.exit(1)

        from planner.models import Task
        t = Task(**dict(rows[0]))
        completed = db.complete_task(t.id, result)
        if completed:
            output(f"Completed: [{completed.id}] {completed.title}", **_flags(ctx))
        else:
            output("Failed to complete task.", **_flags(ctx))
            sys.exit(1)


@task.command("block")
@click.option("--reason", "-r", default="")
@click.pass_context
def task_block(ctx, reason):
    """Block the active task."""
    with get_db(ctx.obj["db_path"]) as db:
        rows = db.conn.execute(
            "SELECT * FROM tasks WHERE status = 'active' LIMIT 1"
        ).fetchall()
        if not rows:
            output("No active task to block.", **_flags(ctx))
            sys.exit(1)

        from planner.models import Task
        t = Task(**dict(rows[0]))
        blocked = db.block_task(t.id, reason)
        if blocked:
            output(f"Blocked: [{blocked.id}] {blocked.title}", **_flags(ctx))
        else:
            output("Failed to block task.", **_flags(ctx))
            sys.exit(1)


@task.command("cancel")
@click.argument("task_id")
@click.option("--reason", "-r", default="")
@click.pass_context
def task_cancel(ctx, task_id, reason):
    """Cancel a task."""
    with get_db(ctx.obj["db_path"]) as db:
        cancelled = db.cancel_task(task_id, reason)
        if cancelled:
            output(f"Cancelled: {task_id}", **_flags(ctx))
        else:
            output(f"Task not found: {task_id}", **_flags(ctx))
            sys.exit(1)


@task.command("delete")
@click.argument("task_id")
@click.pass_context
def task_delete(ctx, task_id):
    """Delete a planned task."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.delete_task(task_id):
            output(f"Deleted: {task_id}", **_flags(ctx))
        else:
            output("Can only delete planned tasks.", **_flags(ctx))
            sys.exit(1)


@task.command("edit")
@click.argument("task_id")
@click.option("--title", "-t", default=None)
@click.option("--body", "-b", default=None)
@click.option("--priority", default=None, type=int)
@click.option("--assignee", "-a", default=None)
@click.pass_context
def task_edit(ctx, task_id, title, body, priority, assignee):
    """Edit a task."""
    with get_db(ctx.obj["db_path"]) as db:
        t = db.edit_task(task_id, title, body, priority, assignee)
        if t:
            output(f"Updated: [{t.id}] {t.title}", **_flags(ctx))
        else:
            output(f"Task not found: {task_id}", **_flags(ctx))
            sys.exit(1)


@task.command("log")
@click.option("--task-id", default=None, help="Task ID (defaults to active task)")
@click.option("--message", "-m", required=True)
@click.pass_context
def task_log(ctx, task_id, message):
    """Add a log entry to a task."""
    with get_db(ctx.obj["db_path"]) as db:
        if not task_id:
            rows = db.conn.execute(
                "SELECT id FROM tasks WHERE status = 'active' LIMIT 1"
            ).fetchall()
            if not rows:
                output("No active task.", **_flags(ctx))
                sys.exit(1)
            task_id = rows[0][0]

        log = db.add_log(task_id, message)
        output(f"Logged to [{task_id}]: {message}", **_flags(ctx))


@task.command("search")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--query", "-q", required=True)
@click.pass_context
def task_search(ctx, project_name, query):
    """Search tasks by title or body."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)

        tasks = db.search_tasks(p.id, query)
        if ctx.obj["as_json"]:
            output([{"id": t.id, "title": t.title, "status": t.status.value} for t in tasks], **_flags(ctx))
        else:
            if not tasks:
                output("No matches.", **_flags(ctx))
                return
            for t in tasks:
                output(f"  [{t.id}] {t.title} ({t.status.value})", **_flags(ctx))


@task.command("prioritize")
@click.argument("task_id")
@click.pass_context
def task_prioritize(ctx, task_id):
    """Move a task to the top of the queue."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.prioritize_task(task_id):
            output(f"Prioritized: {task_id}", **_flags(ctx))
        else:
            output("Can only prioritize planned tasks.", **_flags(ctx))
            sys.exit(1)


@task.command("move")
@click.argument("task_id")
@click.option("--position", "-pos", required=True, type=int)
@click.pass_context
def task_move(ctx, task_id, position):
    """Move a task to a specific position."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.move_task(task_id, position):
            output(f"Moved {task_id} to position {position}", **_flags(ctx))
        else:
            output("Can only move planned tasks.", **_flags(ctx))
            sys.exit(1)


# ─── Dependencies ─────────────────────────────────────────────────────────────

@task.group("dep")
def task_dep():
    """Manage task dependencies."""
    pass


@task_dep.command("add")
@click.argument("task_id")
@click.option("--depends-on", required=True)
@click.pass_context
def dep_add(ctx, task_id, depends_on):
    """Add a dependency (task depends on another)."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.add_dependency(task_id, depends_on):
            output(f"Added dependency: {task_id} depends on {depends_on}", **_flags(ctx))
        else:
            output("Failed to add dependency (cycle detected or tasks not found).", **_flags(ctx))
            sys.exit(1)


@task_dep.command("remove")
@click.argument("task_id")
@click.option("--depends-on", required=True)
@click.pass_context
def dep_remove(ctx, task_id, depends_on):
    """Remove a dependency."""
    with get_db(ctx.obj["db_path"]) as db:
        if db.remove_dependency(task_id, depends_on):
            output(f"Removed dependency: {task_id} no longer depends on {depends_on}", **_flags(ctx))
        else:
            output("Dependency not found.", **_flags(ctx))
            sys.exit(1)


@task_dep.command("list")
@click.argument("task_id")
@click.pass_context
def dep_list(ctx, task_id):
    """List dependencies for a task."""
    with get_db(ctx.obj["db_path"]) as db:
        deps = db.list_dependencies(task_id)
        if ctx.obj["as_json"]:
            output(deps, **_flags(ctx))
        else:
            if deps["depends_on"]:
                output(f"  Depends on: {', '.join(deps['depends_on'])}", **_flags(ctx))
            if deps["blocked_by"]:
                output(f"  Blocks: {', '.join(deps['blocked_by'])}", **_flags(ctx))
            if not deps["depends_on"] and not deps["blocked_by"]:
                output("  No dependencies.", **_flags(ctx))


# ─── Status ───────────────────────────────────────────────────────────────────

@main.command("status")
@click.option("--project", "-p", "project_name", required=True)
@click.pass_context
def status(ctx, project_name):
    """Show project overview."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)

        counts = db.get_project_status(p.id)
        active = db.get_active_task(p.id)
        planned = db.list_tasks(p.id, status=TaskStatus.PLANNED, limit=5)
        blocked = db.list_tasks(p.id, status=TaskStatus.BLOCKED, limit=5)

        if ctx.obj["as_json"]:
            output({
                "project": p.name,
                "counts": counts,
                "active": {"id": active.id, "title": active.title} if active else None,
                "next_planned": [{"id": t.id, "title": t.title} for t in planned],
                "blocked": [{"id": t.id, "title": t.title} for t in blocked],
            }, **_flags(ctx))
        else:
            parts = []
            for s in ["planned", "active", "completed", "blocked", "cancelled"]:
                if s in counts:
                    parts.append(f"{counts[s]} {s}")
            output(f"\n{p.name} — {', '.join(parts)}\n", **_flags(ctx))

            if active:
                output(f"ACTIVE:  [{active.id}] {active.title}", **_flags(ctx))
            else:
                output("ACTIVE:  (none)", **_flags(ctx))

            if planned:
                output("\nNEXT:", **_flags(ctx))
                for t in planned:
                    assign = f" @{t.assignee}" if t.assignee else ""
                    output(f"  [{t.id}] {t.title} (P:{t.priority}{assign})", **_flags(ctx))

            if blocked:
                output("\nBLOCKED:", **_flags(ctx))
                for t in blocked:
                    output(f"  [{t.id}] {t.title}", **_flags(ctx))

            output("", **_flags(ctx))


# ─── Dispatch (for orchestrator) ──────────────────────────────────────────────

@main.command("dispatch")
@click.option("--project", "-p", "project_name", required=True)
@click.option("--profile", default=None, help="Filter by assignee profile")
@click.pass_context
def dispatch(ctx, project_name, profile):
    """Get next task for a worker (dispatch)."""
    with get_db(ctx.obj["db_path"]) as db:
        p = db.get_project(project_name)
        if not p:
            output(f"Project not found: {project_name}", **_flags(ctx))
            sys.exit(1)

        # If profile specified, find next ready task assigned to that profile
        if profile:
            tasks = db.list_tasks(p.id, status=TaskStatus.PLANNED, assignee=profile, limit=100)
            task = None
            for t in tasks:
                if not db._get_incomplete_deps(t.id):
                    task = t
                    break
        else:
            task = db.find_next_ready(p.id)

        if not task:
            output("No ready tasks.", **_flags(ctx))
            sys.exit(1)

        if ctx.obj["as_json"]:
            deps = db.list_dependencies(task.id)
            tags = db.get_tags(task.id)
            output({
                "id": task.id, "title": task.title, "body": task.body,
                "priority": task.priority, "assignee": task.assignee,
                "tags": tags, "depends_on": deps["depends_on"],
            }, **_flags(ctx))
        else:
            output(f"TASK: [{task.id}] {task.title}", **_flags(ctx))
            output(f"PRIORITY: {task.priority}", **_flags(ctx))
            if task.assignee:
                output(f"ASSIGNEE: {task.assignee}", **_flags(ctx))
            tags = db.get_tags(task.id)
            if tags:
                output(f"TAGS: {', '.join(tags)}", **_flags(ctx))
            if task.body:
                output(f"\nBODY:\n{task.body}", **_flags(ctx))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _flags(ctx) -> dict:
    return {"as_json": ctx.obj["as_json"], "quiet": ctx.obj["quiet"]}


if __name__ == "__main__":
    main()
