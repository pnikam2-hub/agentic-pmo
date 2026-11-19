"""Plane integration endpoints — link a PMO project to a Plane project and pull its work items."""
import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.integrations.plane import config as plane_config
from backend.integrations.plane.client import PlaneError
from backend.integrations.plane.sync import make_client, sync_project
from backend.models import (PlaneLink, PlaneProjectLink, PlanePushRun, PlaneWebhookEvent,
                            Project, Task)

router = APIRouter(prefix="/api/integrations/plane", tags=["plane"])


class LinkRequest(BaseModel):
    project_id: int
    plane_project_id: str


@router.get("/status")
def status(db: Session = Depends(get_db)):
    info = plane_config.status()
    linked = db.query(PlaneProjectLink).count()
    mirrored = db.query(PlaneLink).count()
    info.update({"linked_projects": linked, "mirrored_work_items": mirrored})
    return info


@router.get("/plane-projects")
def list_plane_projects():
    """Projects available in the Plane workspace, for the link picker."""
    if not plane_config.configured():
        raise HTTPException(400, "Plane integration is not configured (PLANE_WORKSPACE / API key)")
    try:
        client = make_client()
        projects = client.projects()
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc
    return [
        {
            "id": p["id"],
            "name": p.get("name"),
            "identifier": p.get("identifier"),
            "created_at": p.get("created_at"),
        }
        for p in projects
    ]


@router.post("/link")
def link_project(body: LinkRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if project is None:
        raise HTTPException(404, "PMO project not found")
    if not plane_config.configured():
        raise HTTPException(400, "Plane integration is not configured")

    try:
        client = make_client()
        match = next((p for p in client.projects() if p["id"] == body.plane_project_id), None)
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc
    if match is None:
        raise HTTPException(404, "Plane project not found in the configured workspace")

    existing = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project.id).first()
    if existing and existing.plane_project_id != body.plane_project_id:
        raise HTTPException(
            409,
            "This PMO project is already linked to a different Plane project; unlink it first",
        )
    if existing is None:
        existing = PlaneProjectLink(project_id=project.id)
        db.add(existing)
    existing.workspace_slug = plane_config.workspace()
    existing.plane_project_id = match["id"]
    existing.plane_project_name = match.get("name", "")
    existing.plane_identifier = match.get("identifier", "")
    db.commit()
    db.refresh(existing)
    return {
        "project_id": project.id,
        "plane_project_id": existing.plane_project_id,
        "plane_project_name": existing.plane_project_name,
        "workspace": existing.workspace_slug,
    }


@router.get("/link/{project_id}")
def get_link(project_id: int, db: Session = Depends(get_db)):
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise HTTPException(404, "No Plane link for this project")
    tasks = db.query(Task).filter(Task.project_id == project_id).count()
    mirrored = db.query(PlaneLink).filter(PlaneLink.project_id == project_id).count()
    return {
        "project_id": project_id,
        "workspace": link.workspace_slug,
        "plane_project_id": link.plane_project_id,
        "plane_project_name": link.plane_project_name,
        "last_synced_at": link.last_synced_at,
        "last_sync_stats": link.last_sync_stats or {},
        "tasks_total": tasks,
        "mirrored_work_items": mirrored,
    }


@router.delete("/link/{project_id}")
def unlink_project(project_id: int, delete_mirrored_tasks: bool = False,
                   db: Session = Depends(get_db)):
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise HTTPException(404, "No Plane link for this project")
    removed = 0
    if delete_mirrored_tasks:
        for pl in db.query(PlaneLink).filter(PlaneLink.project_id == project_id).all():
            task = db.query(Task).filter(Task.id == pl.task_id).first()
            if task is not None:
                db.delete(task)
                removed += 1
    db.delete(link)
    db.commit()
    return {"ok": True, "unlinked": project_id, "tasks_deleted": removed}


@router.post("/reconcile/{project_id}")
def reconcile(project_id: int, db: Session = Depends(get_db)):
    """Full pull with relations — the nightly safety net under the webhook stream."""
    from backend.integrations.plane.sync import reconcile_for_project

    try:
        return reconcile_for_project(db, project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/events")
def recent_events(limit: int = 25, db: Session = Depends(get_db)):
    rows = (db.query(PlaneWebhookEvent)
            .order_by(PlaneWebhookEvent.id.desc()).limit(min(limit, 200)).all())
    return [
        {
            "id": r.id,
            "delivery_id": r.delivery_id,
            "event": r.event,
            "action": r.action,
            "entity_id": r.entity_id,
            "status": r.status,
            "signature_scheme": r.signature_scheme,
            "detail": r.detail,
            "received_at": r.received_at,
            "processed_at": r.processed_at,
        }
        for r in rows
    ]


@router.post("/push/{project_id}")
def push(project_id: int, background: BackgroundTasks, dry_run: bool = True,
         db: Session = Depends(get_db)):
    """Send PMO tasks that Plane has never seen. Defaults to a dry run; writes nothing unless asked."""
    from backend.integrations.plane import push as plane_push

    if not plane_push.enabled():
        raise HTTPException(
            403, "Plane push is disabled. Set PLANE_PUSH_ENABLED=1 to allow writes to Plane."
        )
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise HTTPException(404, "project is not linked to a Plane project")

    if dry_run:
        return plane_push.plan_push(db, link)

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
    running = (db.query(PlanePushRun)
               .filter(PlanePushRun.project_id == project_id,
                       PlanePushRun.status == "running",
                       PlanePushRun.started_at > cutoff)
               .first())
    if running is not None:
        raise HTTPException(409, f"push run {running.id} is still in progress")

    run = PlanePushRun(project_id=project_id, status="running")
    db.add(run)
    db.commit()
    background.add_task(plane_push.run_push_job, run.id)
    plan = plane_push.plan_push(db, link)
    return {
        "run_id": run.id,
        "status": "running",
        "will_create": plan["tasks_to_create"],
        "relations_to_create": plan["relations_to_create"],
        "estimated_minutes": plan["estimated_minutes"],
    }


@router.get("/push/runs/{project_id}")
def push_runs(project_id: int, limit: int = 10, db: Session = Depends(get_db)):
    rows = (db.query(PlanePushRun)
            .filter(PlanePushRun.project_id == project_id)
            .order_by(PlanePushRun.id.desc()).limit(min(limit, 50)).all())
    return [
        {
            "id": r.id,
            "status": r.status,
            "stats": r.stats,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in rows
    ]


@router.post("/sync/{project_id}")
def sync(project_id: int, include_relations: bool = False, db: Session = Depends(get_db)):
    """Pull Plane work items into this PMO project. Read-only on the Plane side."""
    try:
        stats = sync_project(db, project_id, include_relations=include_relations)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"project_id": project_id, "synced_at": datetime.datetime.utcnow(), **stats}
