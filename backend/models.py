"""Agentic PMO — SQLAlchemy ORM models."""
import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Enum as SAEnum,
    UniqueConstraint,
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
    plane_project_link = relationship("PlaneProjectLink", back_populates="project",
                                      uselist=False, cascade="all, delete-orphan")
    plane_links = relationship("PlaneLink", back_populates="project",
                               cascade="all, delete-orphan")


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
    plane_link = relationship("PlaneLink", back_populates="task", uselist=False,
                              cascade="all, delete-orphan")


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


# ── Plane ↔ PMO links ────────────────────────────────────────────────────────
# One Plane project per PMO project, and one row per mirrored work item. These tables are the
# join key the two systems lacked: without them a pull either duplicates tasks or cannot tell
# which local task a Plane work item already owns.
class PlaneProjectLink(Base):
    __tablename__ = "plane_project_links"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    workspace_slug = Column(String(80), nullable=False)
    plane_project_id = Column(String(64), nullable=False)
    plane_project_name = Column(String(200), default="")
    plane_identifier = Column(String(20), default="")
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_stats = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("workspace_slug", "plane_project_id", name="uq_plane_project"),
    )

    project = relationship("Project", back_populates="plane_project_link")


class PlaneLink(Base):
    __tablename__ = "plane_links"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, unique=True)
    plane_work_item_id = Column(String(64), nullable=False)
    plane_sequence_id = Column(Integer, nullable=True)
    plane_state_name = Column(String(80), default="")
    plane_module = Column(String(200), default="")
    content_hash = Column(String(64), default="")
    last_pulled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "plane_work_item_id", name="uq_plane_work_item"),
    )

    project = relationship("Project", back_populates="plane_links")
    task = relationship("Task", back_populates="plane_link")


class PlaneWebhookEvent(Base):
    __tablename__ = "plane_webhook_events"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(String(80), nullable=True, unique=True)
    event = Column(String(60), default="")
    action = Column(String(30), default="")
    entity_id = Column(String(64), nullable=True)
    workspace_slug = Column(String(80), default="")
    signature_scheme = Column(String(30), default="")
    status = Column(String(20), default="received")   # ok | ignored | error | duplicate
    detail = Column(JSON, default=dict)
    received_at = Column(DateTime, default=datetime.datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)


class PlanePushRun(Base):
    """Audit trail for PMO → Plane pushes.

    A push writes to a live client board and takes minutes, so it runs as a background job. Without a
    row per run there is no way to answer "what did we send, and did it finish".
    """
    __tablename__ = "plane_push_runs"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(String(20), default="running")   # running | ok | partial | error
    stats = Column(JSON, default=dict)
    error = Column(Text, default="")
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

