"""Templates router — list and apply green fuel / manufacturing project templates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.auth import require_auth
from backend.templates import GREEN_FUEL_TEMPLATES

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates():
    """List all available project templates."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "category": t["category"],
            "description": t["description"],
            "estimated_duration": t["estimated_duration"],
            "tags": t["tags"],
            "phase_count": len(t["suggested_phases"]),
            "total_tasks": sum(len(p["tasks"]) for p in t["suggested_phases"]),
            "total_estimated_hours": sum(
                sum(task["estimated_hours"] for task in phase["tasks"])
                for phase in t["suggested_phases"]
            ),
        }
        for t in GREEN_FUEL_TEMPLATES
    ]


@router.get("/{template_id}")
def get_template(template_id: str):
    """Get full template details including all phases and tasks."""
    for t in GREEN_FUEL_TEMPLATES:
        if t["id"] == template_id:
            return t
    raise HTTPException(404, "Template not found")


class ApplyTemplateRequest(BaseModel):
    project_id: int


@router.post("/{template_id}/apply")
def apply_template(template_id: str, body: ApplyTemplateRequest,
                   db: Session = Depends(get_db),
                   auth_user: str = Depends(require_auth)):
    """Apply a template to an existing project — creates all tasks."""
    from backend.models import Project, Task

    template = None
    for t in GREEN_FUEL_TEMPLATES:
        if t["id"] == template_id:
            template = t
            break
    if not template:
        raise HTTPException(404, "Template not found")

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Check if project already has tasks
    existing = db.query(Task).filter(Task.project_id == project.id).count()
    if existing > 0:
        raise HTTPException(400,
            f"Project already has {existing} tasks. Remove them before applying a template.")

    # Apply tags from template
    project.tags = list(set(project.tags or []) | set(template["tags"]))
    project.goal = template["goal"]

    # Create tasks
    sort = 0
    created = 0
    for phase in template["suggested_phases"]:
        phase_name = phase["name"]
        for task_data in phase["tasks"]:
            task = Task(
                project_id=project.id,
                title=f"[{phase_name}] {task_data['title']}",
                description=f"Template: {template['name']} — Phase: {phase_name}",
                status="todo",
                priority=task_data.get("priority", "medium"),
                estimated_hours=float(task_data.get("estimated_hours", 0)),
                sort_order=sort,
            )
            db.add(task)
            created += 1
            sort += 1

    db.commit()
    return {"status": "applied", "template": template["name"],
            "tasks_created": created, "total_hours": sort}
