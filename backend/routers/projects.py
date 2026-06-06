"""Projects router — CRUD + listing."""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Project, Task
from backend.schemas import ProjectCreate, ProjectUpdate, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    result = []
    for p in projects:
        task_count = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0
        done_count = db.query(func.count(Task.id)).filter(
            Task.project_id == p.id, Task.status == "done"
        ).scalar() or 0
        out = ProjectOut.model_validate(p)
        out.task_count = task_count
        out.done_count = done_count
        result.append(out)
    return result


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    task_count = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0
    done_count = db.query(func.count(Task.id)).filter(
        Task.project_id == p.id, Task.status == "done"
    ).scalar() or 0
    out = ProjectOut.model_validate(p)
    out.task_count = task_count
    out.done_count = done_count
    return out


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(
        name=body.name,
        description=body.description,
        goal=body.goal,
        priority=body.priority,
        tags=body.tags,
        start_date=body.start_date,
        end_date=body.end_date,
        status="planning",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    out = ProjectOut.model_validate(p)
    out.task_count = 0
    out.done_count = 0
    return out


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(p, key, val)
    p.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(p)
    task_count = db.query(func.count(Task.id)).filter(Task.project_id == p.id).scalar() or 0
    done_count = db.query(func.count(Task.id)).filter(
        Task.project_id == p.id, Task.status == "done"
    ).scalar() or 0
    out = ProjectOut.model_validate(p)
    out.task_count = task_count
    out.done_count = done_count
    return out


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)
    db.commit()
    return {"ok": True}
