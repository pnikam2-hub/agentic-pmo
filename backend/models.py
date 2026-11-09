"""Agentic PMO — SQLAlchemy ORM models."""
import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from backend.database import Base
import enum


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"
    blocked = "blocked"


class ProjectStatus(str, enum.Enum):
    planning = "planning"
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AgentType(str, enum.Enum):
    plan = "plan"
    monitor = "monitor"
    alert = "alert"


# ── Project ──────────────────────────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    goal = Column(Text, default="")       # The brief the AI plan agent uses
    status = Column(String(20), default=ProjectStatus.planning.value)
    priority = Column(String(20), default=Priority.medium.value)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    tags = Column(JSON, default=list)     # e.g. ["green-fuel", "manufacturing"]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan",
                         order_by="Task.created_at")
    milestones = relationship("Milestone", back_populates="project", cascade="all, delete-orphan")
    agent_actions = relationship("AgentAction", back_populates="project", cascade="all, delete-orphan",
                                  order_by="AgentAction.created_at.desc()")
    project_pack = relationship("ProjectPack", back_populates="project",
                                uselist=False, cascade="all, delete-orphan")


# ── Task ─────────────────────────────────────────────────────────────────────
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default=TaskStatus.todo.value)
    priority = Column(String(20), default=Priority.medium.value)
    assignee = Column(String(100), default="")
    estimated_hours = Column(Float, default=0.0)
    actual_hours = Column(Float, default=0.0)
    due_date = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    dependencies = Column(JSON, default=list)  # list of task IDs
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="tasks")


# ── Milestone ────────────────────────────────────────────────────────────────
class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    due_date = Column(DateTime, nullable=True)
    status = Column(String(20), default=TaskStatus.todo.value)
    required_task_ids = Column(JSON, default=list)  # tasks that must be done
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="milestones")


# ── Webhook Subscription ─────────────────────────────────────────────────
class WebhookSubscription(Base):
    __tablename__ = "webhooks"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    events = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Resource(Base):
    __tablename__ = "resources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    role = Column(String(100), default="")
    availability = Column(Float, default=40.0)  # hours per week
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ── Agent Action (AI audit trail) ────────────────────────────────────────────
class AgentAction(Base):
    __tablename__ = "agent_actions"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    agent_type = Column(String(20), default=AgentType.plan.value)
    action_type = Column(String(100), default="")   # e.g. "plan_generated", "delay_detected"
    summary = Column(Text, default="")
    details = Column(JSON, default=dict)             # structured payload
    severity = Column(String(20), default="info")    # info / warning / critical
    resolved = Column(Integer, default=0)            # 0 = open, 1 = resolved
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="agent_actions")


# ── Project ↔ Domain Pack (one pack per project) ─────────────────────────────
class ProjectPack(Base):
    __tablename__ = "project_packs"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    pack_id = Column(String(80), nullable=False)
    pack_name = Column(String(200), default="")
    applied_at = Column(DateTime, default=datetime.datetime.utcnow)
    # snapshot of what was applied, so the project keeps its domain context even
    # if the pack definition changes later
    snapshot = Column(JSON, default=dict)

    project = relationship("Project", back_populates="project_pack")

