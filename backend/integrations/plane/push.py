"""PMO → Plane push (Phase 2).

This is the only code in the integration that writes to Plane, so it is deliberately narrow:

- **Create only.** A task that already has a plane_links row is skipped, never updated. Plane owns the
  work item once it exists; overwriting it from here is exactly the divergence the boundary forbids.
- **Idempotent on plane_links.** Re-running a push after a failure finishes the job instead of
  duplicating the board.
- **Behind a flag.** `PLANE_PUSH_ENABLED` must be on; the router refuses otherwise.
- **Dry run first.** `plan_push()` performs no writes and returns exactly what a push would create,
  which is what makes it safe to try against a client's board.

Modules are not created: the PMO has no phase field on a task (the pack's phases exist only in the
pack's WBS file), so there is nothing to group by. Work items and typed relations are what this sends.
"""
import datetime
import re

from sqlalchemy.orm import Session

from backend.integrations.plane import config as plane_config
from backend.integrations.plane.client import PlaneClient, PlaneError
from backend.integrations.plane.sync import _content_hash, make_client
from backend.models import PlaneLink, PlaneProjectLink, Task

STATUS_TO_STATE = {
    "todo": ("Todo", "Backlog"),
    "in_progress": ("In Progress", "Started"),
    "review": ("In Review", "In Progress"),
    "done": ("Done", "Completed"),
    "blocked": ("Blocked", "In Progress"),
}

PRIORITY_TO_PLANE = {
    "critical": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


def enabled() -> bool:
    return plane_config.push_enabled()


def _state_index(client: PlaneClient, plane_project_id: str) -> dict:
    """name (lower) → id, plus group → id as a fallback."""
    index = {}
    for state in client.states(plane_project_id):
        index[(state.get("name") or "").lower()] = state["id"]
        index.setdefault(f"group:{(state.get('group') or '').lower()}", state["id"])
    return index


def _pick_state(task_status: str, states: dict) -> str | None:
    names, fallback = STATUS_TO_STATE.get(task_status, ("Todo", "Backlog"))
    for name in (names, fallback):
        hit = states.get(name.lower())
        if hit:
            return hit
    return states.get("group:backlog") or states.get("group:unstarted")


def _description_html(task: Task) -> str:
    """Include the estimate as text — Plane has no hours field, and the pull reads it back out."""
    parts = [f"<p>{(task.description or '').strip()}</p>"] if task.description else []
    meta = [
        f"<b>Status:</b> {task.status}",
        f"<b>Estimate:</b> {float(task.estimated_hours or 0):g} h",
        f"<b>PMO task:</b> {task.id}",
    ]
    if task.assignee:
        meta.insert(1, f"<b>Assignee:</b> {task.assignee}")
    parts.append("<p>" + "<br>".join(meta) + "</p>")
    return "".join(parts)


def _linked_task_ids(db: Session, project_id: int) -> set[int]:
    rows = db.query(PlaneLink.task_id).filter(PlaneLink.project_id == project_id).all()
    return {r[0] for r in rows}


def plan_push(db: Session, link: PlaneProjectLink) -> dict:
    """What a push would create. Reads the database only — no Plane calls, no writes."""
    tasks = (db.query(Task).filter(Task.project_id == link.project_id)
             .order_by(Task.sort_order, Task.id).all())
    linked = _linked_task_ids(db, link.project_id)
    unlinked = [t for t in tasks if t.id not in linked]

    by_id = {t.id: t for t in tasks}
    relation_edges = 0
    for task in unlinked:
        for dep in (task.dependencies or []):
            if dep in by_id:
                relation_edges += 1

    return {
        "project_id": link.project_id,
        "plane_project_id": link.plane_project_id,
        "tasks_total": len(tasks),
        "tasks_to_create": len(unlinked),
        "tasks_already_linked": len(tasks) - len(unlinked),
        "relations_to_create": relation_edges,
        "estimated_api_calls": len(unlinked) + relation_edges,
        # 1.05 s pacing on a 60/min token limit
        "estimated_minutes": round((len(unlinked) + relation_edges) * 1.05 / 60, 1),
        "sample": [t.title[:90] for t in unlinked[:8]],
        "dry_run": True,
    }


def push_project(db: Session, link: PlaneProjectLink, client: PlaneClient,
                 progress=None) -> dict:
    """Create Plane work items for tasks that have no link yet, then wire their relations."""
    stats = {
        "created": 0, "skipped": 0, "relations_created": 0,
        "errors": [], "api_calls_before": client.calls, "dry_run": False,
    }
    states = _state_index(client, link.plane_project_id)
    linked = _linked_task_ids(db, link.project_id)
    tasks = (db.query(Task).filter(Task.project_id == link.project_id)
             .order_by(Task.sort_order, Task.id).all())
    todo = [t for t in tasks if t.id not in linked]

    for n, task in enumerate(todo, start=1):
        body = {
            "name": (task.title or "Untitled")[:300],
            "description_html": _description_html(task),
            "priority": PRIORITY_TO_PLANE.get((task.priority or "medium").lower(), "medium"),
        }
        state_id = _pick_state(task.status, states)
        if state_id:
            body["state"] = state_id
        try:
            item = client.post(f"/projects/{link.plane_project_id}/work-items/", body)
        except PlaneError as exc:
            stats["errors"].append(f"{task.id} {task.title[:40]}: {str(exc)[:180]}")
            continue
        db.add(PlaneLink(
            project_id=link.project_id, task_id=task.id,
            plane_work_item_id=item["id"], plane_sequence_id=item.get("sequence_id"),
            plane_state_name=next((s for s, i in states.items() if i == state_id), "")[:80],
            content_hash=_content_hash(item), last_pulled_at=datetime.datetime.utcnow(),
        ))
        db.commit()
        stats["created"] += 1
        if progress and n % 20 == 0:
            progress(n, len(todo))

    # relations, second pass: both ends must exist in Plane now
    plane_ids = {l.task_id: l.plane_work_item_id for l in
                 db.query(PlaneLink).filter(PlaneLink.project_id == link.project_id).all()}
    for task in todo:
        targets = [plane_ids[d] for d in (task.dependencies or [])
                   if d in plane_ids and plane_ids[d] != plane_ids.get(task.id)]
        if not targets:
            continue
        try:
            client.post(
                f"/projects/{link.plane_project_id}/work-items/{plane_ids[task.id]}/relations/",
                {"relation_type": "blocked_by", "issues": targets},
            )
            stats["relations_created"] += len(targets)
        except PlaneError as exc:
            stats["errors"].append(f"relations for {task.id}: {str(exc)[:180]}")

    stats["skipped"] = len(tasks) - len(todo)
    stats["api_calls"] = client.calls - stats.pop("api_calls_before")
    stats["finished_at"] = datetime.datetime.utcnow().isoformat()
    return stats


def push_project_by_id(db: Session, project_id: int, client: PlaneClient | None = None) -> dict:
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise ValueError(f"project {project_id} is not linked to a Plane project")
    return push_project(db, link, client or make_client())


def run_push_job(run_id: int) -> None:
    """Background entry point: own session, own transaction, status always recorded."""
    from backend.database import SessionLocal
    from backend.models import PlanePushRun

    db: Session = SessionLocal()
    try:
        run = db.get(PlanePushRun, run_id)
        if run is None:
            return
        try:
            stats = push_project_by_id(db, run.project_id)
            run.stats = stats
            run.status = "partial" if stats.get("errors") else "ok"
        except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
            db.rollback()
            run = db.get(PlanePushRun, run_id)
            run.status = "error"
            run.error = f"{type(exc).__name__}: {exc}"[:1000]
        run.finished_at = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close()
