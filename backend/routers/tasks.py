"""Tasks router — CRUD with kanban-friendly ordering."""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Task
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


@router.post("", response_model=TaskOut)
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
def update_task(project_id: int, task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(t, key, val)
    t.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    return {"ok": True}
