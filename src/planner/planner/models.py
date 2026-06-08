"""Pydantic models for Planner entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


# --- Enums ---

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TaskStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class LogSource(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


# --- Models ---

class Project(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class Goal(BaseModel):
    id: str = Field(default_factory=_uuid)
    project_id: str
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class Task(BaseModel):
    id: str = Field(default_factory=_uuid)
    project_id: str
    goal_id: Optional[str] = None
    title: str
    body: str = ""
    status: TaskStatus = TaskStatus.PLANNED
    priority: int = 5
    parent_task_id: Optional[str] = None
    assignee: Optional[str] = None
    order_index: int = 0
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskDependency(BaseModel):
    task_id: str
    depends_on_id: str
    created_at: str = Field(default_factory=_now)


class TaskLog(BaseModel):
    id: int = 0
    task_id: str
    message: str
    source: LogSource = LogSource.AGENT
    created_at: str = Field(default_factory=_now)


class TaskTag(BaseModel):
    task_id: str
    tag: str


# --- Summary models ---

class ProjectSummary(BaseModel):
    project: Project
    task_counts: dict[str, int]  # status -> count
    goal_count: int
    active_task: Optional[Task] = None


class TaskWithDeps(BaseModel):
    task: Task
    depends_on: list[str] = []  # IDs of tasks this depends on
    blocked_by: list[str] = []  # IDs of incomplete tasks blocking this
    tags: list[str] = []
    log_count: int = 0
