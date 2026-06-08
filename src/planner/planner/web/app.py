"""Planner Web UI — FastAPI app with read/write task management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from planner.db import Database, DEFAULT_DB
from planner.models import TaskStatus

app = FastAPI(title="Planner", docs_url="/docs")

templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
)


def get_db() -> Database:
    db = Database()
    db.run_migrations()
    return db


# ─── Request models ─────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    project: str
    title: str
    body: str = ""
    priority: int = 5
    assignee: Optional[str] = None
    tags: list[str] = []
    after: list[str] = []


class TaskEdit(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None


class TaskReorder(BaseModel):
    position: int


class TaskComplete(BaseModel):
    result: str = ""


class TaskBlock(BaseModel):
    reason: str = ""


class TaskCancel(BaseModel):
    reason: str = ""


class TaskLog(BaseModel):
    message: str


class DepAdd(BaseModel):
    depends_on: str


# ─── Pages ──────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, project: Optional[str] = None):
    db = get_db()
    projects = db.list_projects()

    current = None
    tasks_by_status = {}
    active_task = None
    counts = {}
    goals = []

    if projects:
        # Default to first active project, or the one specified
        if project:
            current = db.get_project(project)
        if not current:
            current = projects[0]

        if current:
            counts = db.get_project_status(current.id)
            active_task = db.get_active_task(current.id)
            goals = db.list_goals(current.id)

            for status in TaskStatus:
                tasks = db.list_tasks(current.id, status=status, limit=200)
                tasks_with_meta = []
                for t in tasks:
                    deps = db.list_dependencies(t.id)
                    tags = db.get_tags(t.id)
                    # Enrich deps with status info
                    dep_details = []
                    for dep_id in deps["depends_on"]:
                        dep_task = db.get_task(dep_id)
                        if dep_task:
                            dep_details.append({"id": dep_id, "title": dep_task.title, "status": dep_task.status.value})
                        else:
                            dep_details.append({"id": dep_id, "title": "?", "status": "unknown"})
                    tasks_with_meta.append({
                        "task": t,
                        "tags": tags,
                        "depends_on": deps["depends_on"],
                        "dep_details": dep_details,
                        "blocked_by": deps["blocked_by"],
                    })
                tasks_by_status[status.value] = tasks_with_meta

    db.close()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "projects": projects,
            "current": current,
            "tasks_by_status": tasks_by_status,
            "active_task": active_task,
            "counts": counts,
            "goals": goals if current else [],
        },
    )


# ─── API: Projects ──────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


@app.get("/api/projects")
async def api_list_projects():
    db = get_db()
    projects = db.list_projects()
    db.close()
    return [{"id": p.id, "name": p.name, "status": p.status.value} for p in projects]


@app.post("/api/projects")
async def api_create_project(body: ProjectCreate):
    db = get_db()
    existing = db.get_project(body.name)
    if existing:
        db.close()
        raise HTTPException(409, f"Project already exists: {body.name}")
    p = db.create_project(body.name, body.description)
    db.close()
    return {"id": p.id, "name": p.name, "status": p.status.value}


@app.get("/api/projects/{name}")
async def api_get_project(name: str):
    db = get_db()
    p = db.get_project(name)
    if not p:
        db.close()
        raise HTTPException(404, f"Project not found: {name}")
    counts = db.get_project_status(p.id)
    active = db.get_active_task(p.id)
    db.close()
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "status": p.status.value, "counts": counts,
        "active_task": {"id": active.id, "title": active.title} if active else None,
    }


@app.delete("/api/projects/{name}")
async def api_delete_project(name: str):
    db = get_db()
    ok = db.delete_project(name)
    db.close()
    if not ok:
        raise HTTPException(404, f"Project not found: {name}")
    return {"success": True, "name": name}


# ─── API: Goals ──────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    title: str
    description: str = ""


@app.post("/api/projects/{name}/goals")
async def api_create_goal(name: str, body: GoalCreate):
    db = get_db()
    p = db.get_project(name)
    if not p:
        db.close()
        raise HTTPException(404, f"Project not found: {name}")
    g = db.create_goal(p.id, body.title, body.description)
    db.close()
    return {"id": g.id, "title": g.title, "status": g.status.value}


@app.get("/api/projects/{name}/goals")
async def api_list_goals(name: str):
    db = get_db()
    p = db.get_project(name)
    if not p:
        db.close()
        raise HTTPException(404, f"Project not found: {name}")
    goals = db.list_goals(p.id)
    db.close()
    return [{"id": g.id, "title": g.title, "status": g.status.value} for g in goals]


@app.post("/api/goals/{goal_id}/complete")
async def api_complete_goal(goal_id: str):
    db = get_db()
    ok = db.complete_goal(goal_id)
    db.close()
    if not ok:
        raise HTTPException(404, f"Goal not found: {goal_id}")
    return {"success": True, "goal_id": goal_id}


# ─── API: Tasks ─────────────────────────────────────────────────────────────


@app.get("/api/projects/{name}/tasks")
async def api_list_tasks(
    name: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: int = 100,
):
    db = get_db()
    p = db.get_project(name)
    if not p:
        db.close()
        raise HTTPException(404, f"Project not found: {name}")
    s = TaskStatus(status) if status else None
    tasks = db.list_tasks(p.id, s, assignee, limit)
    result = []
    for t in tasks:
        deps = db.list_dependencies(t.id)
        tags = db.get_tags(t.id)
        result.append({
            "id": t.id, "title": t.title, "body": t.body,
            "status": t.status.value, "priority": t.priority,
            "assignee": t.assignee, "tags": tags,
            "depends_on": deps["depends_on"], "blocked_by": deps["blocked_by"],
            "order_index": t.order_index,
        })
    db.close()
    return result


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    db = get_db()
    t = db.get_task(task_id)
    if not t:
        db.close()
        raise HTTPException(404, f"Task not found: {task_id}")
    deps = db.list_dependencies(t.id)
    tags = db.get_tags(t.id)
    logs = db.get_logs(t.id)
    db.close()
    return {
        "id": t.id, "title": t.title, "body": t.body,
        "status": t.status.value, "priority": t.priority,
        "assignee": t.assignee, "tags": tags,
        "depends_on": deps["depends_on"], "blocked_by": deps["blocked_by"],
        "logs": [{"message": l.message, "source": l.source.value, "at": l.created_at} for l in logs],
    }


@app.post("/api/tasks")
async def api_create_task(task: TaskCreate):
    db = get_db()
    p = db.get_project(task.project)
    if not p:
        db.close()
        raise HTTPException(404, f"Project not found: {task.project}")
    t = db.create_task(
        p.id, task.title, task.body, task.priority, task.assignee,
        tags=task.tags or None, depends_on=task.after or None,
    )
    db.close()
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.put("/api/tasks/{task_id}")
async def api_edit_task(task_id: str, edit: TaskEdit):
    db = get_db()
    t = db.edit_task(task_id, edit.title, edit.body, edit.priority, edit.assignee)
    if not t:
        db.close()
        raise HTTPException(404, f"Task not found: {task_id}")
    db.close()
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.put("/api/tasks/{task_id}/reorder")
async def api_reorder_task(task_id: str, reorder: TaskReorder):
    db = get_db()
    ok = db.move_task(task_id, reorder.position)
    db.close()
    if not ok:
        raise HTTPException(400, "Cannot reorder (task not planned?)")
    return {"success": True, "task_id": task_id, "position": reorder.position}


@app.post("/api/tasks/{task_id}/activate")
async def api_activate_task(task_id: str):
    db = get_db()
    t = db.activate_task(task_id)
    db.close()
    if not t:
        raise HTTPException(400, "Cannot activate (task not planned or deps unmet?)")
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.post("/api/tasks/{task_id}/complete")
async def api_complete_task(task_id: str, body: TaskComplete = TaskComplete()):
    db = get_db()
    t, activated = db.complete_task(task_id, body.result)
    db.close()
    if not t:
        raise HTTPException(400, "Cannot complete (task not active?)")
    return {
        "id": t.id, "title": t.title, "status": t.status.value,
        "activated": [{"id": a.id, "title": a.title} for a in activated],
    }


@app.post("/api/tasks/{task_id}/block")
async def api_block_task(task_id: str, body: TaskBlock = TaskBlock()):
    db = get_db()
    t = db.block_task(task_id, body.reason)
    db.close()
    if not t:
        raise HTTPException(400, "Cannot block (task not active?)")
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.post("/api/tasks/{task_id}/unblock")
async def api_unblock_task(task_id: str):
    db = get_db()
    t = db.unblock_task(task_id)
    db.close()
    if not t:
        raise HTTPException(400, "Cannot unblock (task not blocked?)")
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: str, body: TaskCancel = TaskCancel()):
    db = get_db()
    t = db.cancel_task(task_id, body.reason)
    db.close()
    if not t:
        raise HTTPException(400, "Cannot cancel")
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str):
    db = get_db()
    ok = db.delete_task(task_id)
    db.close()
    if not ok:
        raise HTTPException(400, "Cannot delete (only planned tasks)")
    return {"success": True, "task_id": task_id}


@app.post("/api/tasks/{task_id}/reset")
async def api_reset_task(task_id: str):
    """Reset a task back to planned status (from any status)."""
    db = get_db()
    t = db.reset_task(task_id)
    db.close()
    if not t:
        raise HTTPException(404, f"Task not found: {task_id}")
    return {"id": t.id, "title": t.title, "status": t.status.value}


@app.post("/api/tasks/{task_id}/log")
async def api_add_log(task_id: str, body: TaskLog):
    db = get_db()
    log = db.add_log(task_id, body.message)
    db.close()
    return {"success": True, "task_id": task_id, "message": body.message}


# ─── API: Dependencies ──────────────────────────────────────────────────────


@app.post("/api/tasks/{task_id}/deps")
async def api_add_dep(task_id: str, body: DepAdd):
    db = get_db()
    ok = db.add_dependency(task_id, body.depends_on)
    db.close()
    if not ok:
        raise HTTPException(400, "Failed (cycle or tasks not found)")
    return {"success": True}


@app.delete("/api/tasks/{task_id}/deps/{dep_id}")
async def api_remove_dep(task_id: str, dep_id: str):
    db = get_db()
    ok = db.remove_dependency(task_id, dep_id)
    db.close()
    if not ok:
        raise HTTPException(404, "Dependency not found")
    return {"success": True}
