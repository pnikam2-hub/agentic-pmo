"""Agentic PMO — Pydantic schemas for API request/response."""
import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Project ──────────────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=200, min_length=1)
    description: str = ""
    goal: str = ""
    priority: str = "medium"
    tags: list[str] = []
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    goal: str
    status: str
    priority: str
    tags: list
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    task_count: int = 0
    done_count: int = 0
    model_config = {"from_attributes": True}


# ── Task ─────────────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str = Field(..., max_length=300)
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    assignee: str = ""
    estimated_hours: float = 0.0
    due_date: Optional[datetime.datetime] = None
    dependencies: list[int] = []


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    due_date: Optional[datetime.datetime] = None
    sort_order: Optional[int] = None
    dependencies: Optional[list[int]] = None


class TaskOut(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    status: str
    priority: str
    assignee: str
    estimated_hours: float
    actual_hours: float
    due_date: Optional[datetime.datetime] = None
    sort_order: int
    dependencies: list
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model_config = {"from_attributes": True}


# ── Milestone ────────────────────────────────────────────────────────────────
class MilestoneCreate(BaseModel):
    title: str = Field(..., max_length=300)
    description: str = ""
    due_date: Optional[datetime.datetime] = None
    required_task_ids: list[int] = []


class MilestoneOut(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    due_date: Optional[datetime.datetime] = None
    status: str
    required_task_ids: list
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


# ── Resource ─────────────────────────────────────────────────────────────────
class ResourceCreate(BaseModel):
    name: str = Field(..., max_length=200)
    role: str = ""
    availability: float = 40.0
    project_id: Optional[int] = None


class ResourceOut(BaseModel):
    id: int
    name: str
    role: str
    availability: float
    project_id: Optional[int] = None
    created_at: datetime.datetime
    model_config = {"from_attributes": True}


# ── Agent Action ─────────────────────────────────────────────────────────────
class AgentActionOut(BaseModel):
    id: int
    project_id: int
    agent_type: str
    action_type: str
    summary: str
    details: dict
    severity: str
    resolved: int
    created_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None
    model_config = {"from_attributes": True}


# ── Plan Request / Response ──────────────────────────────────────────────────
class PlanRequest(BaseModel):
    project_id: int
    additional_context: str = ""


class PlanResponse(BaseModel):
    plan: str
    tasks: list[TaskOut]
    actions: list[AgentActionOut]


# ── Dashboard ────────────────────────────────────────────────────────────────
class DashboardOut(BaseModel):
    total_projects: int = 0
    active_projects: int = 0
    total_tasks: int = 0
    done_tasks: int = 0
    blocked_tasks: int = 0
    overdue_tasks: int = 0
    recent_actions: list[AgentActionOut] = []
    projects: list[ProjectOut] = []
