"""Dashboard router — aggregates stats across all projects."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Project, Task, AgentAction
from backend.schemas import DashboardOut, ProjectOut, AgentActionOut
import datetime

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    now = datetime.datetime.utcnow()

    total_projects = db.query(func.count(Project.id)).scalar() or 0
    active_projects = db.query(func.count(Project.id)).filter(
        Project.status.in_(["planning", "active"])
    ).scalar() or 0

    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    done_tasks = db.query(func.count(Task.id)).filter(Task.status == "done").scalar() or 0
    blocked_tasks = db.query(func.count(Task.id)).filter(Task.status == "blocked").scalar() or 0
    overdue_tasks = db.query(func.count(Task.id)).filter(
        Task.due_date < now,
        Task.status.notin_(["done", "review"]),
    ).scalar() or 0

    # Recent agent actions
    actions_raw = (
        db.query(AgentAction)
        .order_by(AgentAction.created_at.desc())
        .limit(10)
        .all()
    )

    # Projects with task counts
    projects = db.query(Project).order_by(Project.updated_at.desc()).limit(20).all()
    project_outs = []
    for p in projects:
        tc = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0
        dc = db.query(func.count(Task.id)).filter(
            Task.project_id == p.id, Task.status == "done"
        ).scalar() or 0
        out = ProjectOut.model_validate(p)
        out.task_count = tc
        out.done_count = dc
        project_outs.append(out)

    return DashboardOut(
        total_projects=total_projects,
        active_projects=active_projects,
        total_tasks=total_tasks,
        done_tasks=done_tasks,
        blocked_tasks=blocked_tasks,
        overdue_tasks=overdue_tasks,
        recent_actions=[AgentActionOut.model_validate(a) for a in actions_raw],
        projects=project_outs,
    )
