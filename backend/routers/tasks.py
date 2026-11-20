"""Tasks router — CRUD with kanban-friendly ordering."""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.audit import audit
from backend.auth import contributor_up, pmo_lead_up
from backend.database import get_db
from backend.integrations.plane.guard import plane_ownership
from backend.models import Task, User
from backend.schemas import TaskCreate, TaskUpdate, TaskOut

router = APIRouter(prefix="/api/projects/{project_id}/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(project_id: int, db: Session = Depends(get_db)):
    tasks = (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.sort_order, Task.created_at)
        .all()
    )
    return tasks


@router.post("", response_model=TaskOut, dependencies=[Depends(pmo_lead_up)])
def create_task(project_id: int, body: TaskCreate, db: Session = Depends(get_db)):
    max_order = (
        db.query(Task.sort_order)
        .filter(Task.project_id == project_id)
        .order_by(Task.sort_order.desc())
        .first()
    )
    task = Task(
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status or "todo",
        priority=body.priority or "medium",
        assignee=body.assignee or "",
        estimated_hours=body.estimated_hours or 0,
        due_date=body.due_date,
        sort_order=(max_order[0] + 1) if max_order else 0,
        dependencies=body.dependencies or [],
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    return t


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(project_id: int, task_id: int, body: TaskUpdate, db: Session = Depends(get_db),
                actor: User = Depends(contributor_up)):
    t = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    update_data = body.model_dump(exclude_unset=True)
    if actor.role == "contributor":
        # Plan §1: a contributor may move a task between statuses and log
        # actual hours; every other field is plan editing, which is the
        # pmo_lead's. Checked before the Plane-ownership rule so a role
        # refusal is never masked by a business-rule conflict.
        refused = sorted(k for k in update_data if k not in ("status", "actual_hours"))
        if refused:
            raise HTTPException(
                403,
                "This action requires role pmo_lead, admin, but your role is "
                f"'contributor'. Fields refused: {', '.join(refused)}. "
                "A contributor may only send 'status' and 'actual_hours'.",
            )
    owned = plane_ownership(db, t)
    if owned:
        raise HTTPException(409, owned)
    for key, val in update_data.items():
        setattr(t, key, val)
    t.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db),
                actor: User = Depends(pmo_lead_up)):
    t = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    owned = plane_ownership(db, t)
    if owned:
        raise HTTPException(409, owned)
    audit(db, actor=actor.username, actor_role=actor.role, action="task_deleted",
          target_type="task", target_id=t.id,
          detail={"title": t.title, "project_id": project_id})
    db.delete(t)
    db.commit()
    return {"ok": True}
