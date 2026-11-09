"""Domain packs router — list packs, inspect them, attach one to a project."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import require_auth
from backend.models import Project, Task, ProjectPack
from backend import packs as packlib

router = APIRouter(prefix="/api", tags=["packs"])


@router.get("/packs")
def list_packs():
    """Summaries of every installed domain pack."""
    return packlib.all_summaries()


@router.get("/packs/{pack_id}")
def get_pack(pack_id: str, full: bool = False):
    """Pack detail. Omit `?full=1` to drop the WBS task list."""
    pack = packlib.load(pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")
    summary = packlib.summarise(pack_id) or {}
    out = {
        **summary,
        "agent_context": pack["agent_context"],
        "playbook": pack["playbook"],
        "risks": pack["risks"],
        "kpis": pack["kpis"],
        "rules": pack["rules"],
        "checklists": pack["checklists"],
        "phases": [{"index": i, "name": n} for i, n in packlib.phases_of(pack).items()],
    }
    if full:
        out["wbs"] = pack["wbs"]
    return out


class ApplyPackRequest(BaseModel):
    project_id: int
    create_tasks: bool = True
    replace_tasks: bool = False


@router.post("/packs/{pack_id}/apply")
def apply_pack(pack_id: str, body: ApplyPackRequest,
               db: Session = Depends(get_db),
               auth_user: str = Depends(require_auth)):
    """Attach a domain pack to a project, optionally seeding its WBS as tasks."""
    pack = packlib.load(pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    existing_tasks = db.query(Task).filter(Task.project_id == project.id).count()
    if body.create_tasks and existing_tasks and not body.replace_tasks:
        raise HTTPException(
            400,
            f"Project already has {existing_tasks} tasks. Pass replace_tasks=true to reseed, "
            f"or create_tasks=false to attach the pack without changing tasks.",
        )

    created = 0
    if body.create_tasks:
        if body.replace_tasks and existing_tasks:
            db.query(Task).filter(Task.project_id == project.id).delete()
            db.flush()

        phase_names = packlib.phases_of(pack)
        sort = 0
        for t in pack["wbs"].get("tasks", []):
            phase_name = phase_names.get(int(t.get("phase", 0) or 0), "Phase 1")
            description = t.get("description", "") or ""
            if t.get("deliverables"):
                description += f"\n\nDeliverable: {t['deliverables']}"
            if t.get("acceptance_criteria"):
                description += f"\nAcceptance: {t['acceptance_criteria']}"
            db.add(Task(
                project_id=project.id,
                title=f"[{phase_name}] {t.get('title', 'Task')}",
                description=description.strip(),
                status="todo",
                priority=t.get("priority", "medium"),
                estimated_hours=float(t.get("estimated_hours", 0) or 0),
                sort_order=sort,
            ))
            created += 1
            sort += 1

    # tags
    project.tags = sorted(set(project.tags or []) | set(pack["tags"] or []))

    # one pack per project — replace any previous attachment
    db.query(ProjectPack).filter(ProjectPack.project_id == project.id).delete()
    db.add(ProjectPack(
        project_id=project.id,
        pack_id=pack_id,
        pack_name=pack["name"],
        snapshot={
            "name": pack["name"],
            "risk_count": len(pack["risks"]),
            "kpi_count": len(pack["kpis"]),
            "rule_count": len(pack["rules"]),
            "top_risks": packlib.top_risks(pack, 12),
            "kpi_names": [k.get("name") for k in pack["kpis"][:20]],
        },
    ))
    db.commit()

    return {
        "status": "applied",
        "pack": pack["name"],
        "pack_id": pack_id,
        "tasks_created": created,
        "risks": len(pack["risks"]),
        "kpis": len(pack["kpis"]),
        "rules": len(pack["rules"]),
    }


@router.get("/projects/{project_id}/pack")
def project_pack(project_id: int, db: Session = Depends(get_db)):
    """The domain pack attached to a project, if any."""
    row = db.query(ProjectPack).filter(ProjectPack.project_id == project_id).first()
    if not row:
        return {"attached": False}
    snap = row.snapshot or {}
    return {
        "attached": True,
        "pack_id": row.pack_id,
        "name": row.pack_name,
        "applied_at": row.applied_at,
        "risk_count": snap.get("risk_count", 0),
        "kpi_count": snap.get("kpi_count", 0),
        "rule_count": snap.get("rule_count", 0),
        "top_risks": snap.get("top_risks", []),
        "kpi_names": snap.get("kpi_names", []),
    }


@router.delete("/projects/{project_id}/pack")
def detach_pack(project_id: int, db: Session = Depends(get_db),
                auth_user: str = Depends(require_auth)):
    row = db.query(ProjectPack).filter(ProjectPack.project_id == project_id).first()
    if not row:
        raise HTTPException(404, "No pack attached")
    db.delete(row)
    db.commit()
    return {"status": "detached"}
