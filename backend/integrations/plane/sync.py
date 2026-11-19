"""Plane → PMO pull.

Phase 1 of the integration: read-only. It creates or updates the PMO tasks that Plane owns, records
the join in `plane_links`, and imports the typed dependency edges as the PMO's task-id list so the
Monitor agent can finally see a predecessor relationship.

Nothing here writes to Plane. Deletions on the Plane side are reported as stale links rather than
applied locally: a transient API error must never delete a client's plan.
"""
import datetime
import hashlib
import json

from sqlalchemy.orm import Session

from backend.integrations.plane import config as plane_config
from backend.integrations.plane.client import PlaneClient
from backend.models import PlaneLink, PlaneProjectLink, Task

# Plane state group → PMO status. A state whose name says blocked/on hold wins over its group,
# because teams routinely model "blocked" as a started state.
STATE_GROUP_TO_STATUS = {
    "backlog": "todo",
    "unstarted": "todo",
    "started": "in_progress",
    "completed": "done",
    "cancelled": "todo",
}

PRIORITY_TO_PMO = {
    "urgent": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "medium",
}

HASH_FIELDS = ("name", "priority", "state", "target_date", "start_date", "archived_at")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _content_hash(item: dict) -> str:
    payload = {k: item.get(k) for k in HASH_FIELDS}
    payload["assignees"] = sorted(item.get("assignees") or [])
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _status_for(item: dict, states: dict) -> str:
    state_meta = states.get(item.get("state"), {})
    name = (state_meta.get("name") or "").lower()
    if "block" in name:
        return "blocked"
    if "review" in name or "qa" in name:
        return "review"
    return STATE_GROUP_TO_STATUS.get(state_meta.get("group", ""), "todo")


def _assignee_label(item: dict, members: dict) -> str:
    ids = item.get("assignees") or []
    if not ids:
        return ""
    labels = [members.get(a, a) for a in ids]
    return ", ".join(labels)[:100]


def pull(db: Session, link: PlaneProjectLink, client: PlaneClient,
         include_relations: bool = False) -> dict:
    planes_pid = link.plane_project_id
    stats = {
        "created": 0, "updated": 0, "unchanged": 0,
        "relations_linked": 0, "stale_links": 0, "items_seen": 0,
        "api_calls_before": client.calls,
    }

    state_rows = client.states(planes_pid)
    states = {s["id"]: {"name": s.get("name", ""), "group": s.get("group", "")} for s in state_rows}

    members = {}
    try:
        for m in client.paginate("/members/"):
            members[m.get("member")] = m.get("display_name") or m.get("email") or m.get("member")
    except Exception:
        # member expansion is a nicety; never fail a pull over it
        members = {}

    items = client.work_items(planes_pid)
    stats["items_seen"] = len(items)

    existing = {l.plane_work_item_id: l for l in
                db.query(PlaneLink).filter(PlaneLink.project_id == link.project_id).all()}

    next_sort = (
        db.query(Task.sort_order).filter(Task.project_id == link.project_id)
        .order_by(Task.sort_order.desc()).first()
    )
    next_sort = (next_sort[0] + 1) if next_sort else 0

    seen = set()
    for item in items:
        wid = item["id"]
        seen.add(wid)
        digest = _content_hash(item)
        fields = {
            "title": (item.get("name") or "Untitled")[:300],
            "status": _status_for(item, states),
            "priority": PRIORITY_TO_PMO.get((item.get("priority") or "medium").lower(), "medium"),
            "assignee": _assignee_label(item, members),
            "due_date": _parse_date(item.get("target_date")),
            "description": (item.get("description_stripped") or "")[:2000],
        }

        record = existing.get(wid)
        if record is None:
            task = Task(project_id=link.project_id, sort_order=next_sort, **fields)
            next_sort += 1
            db.add(task)
            db.flush()
            db.add(PlaneLink(
                project_id=link.project_id, task_id=task.id,
                plane_work_item_id=wid, plane_sequence_id=item.get("sequence_id"),
                plane_state_name=states.get(item.get("state"), {}).get("name", "")[:80],
                content_hash=digest, last_pulled_at=datetime.datetime.utcnow(),
            ))
            stats["created"] += 1
            continue

        if record.content_hash == digest:
            stats["unchanged"] += 1
            record.last_pulled_at = datetime.datetime.utcnow()
            continue

        task = db.query(Task).filter(Task.id == record.task_id).first()
        if task is None:
            stats["stale_links"] += 1
            continue
        for key, value in fields.items():
            setattr(task, key, value)
        task.updated_at = datetime.datetime.utcnow()
        record.content_hash = digest
        record.last_pulled_at = datetime.datetime.utcnow()
        record.plane_state_name = states.get(item.get("state"), {}).get("name", "")[:80]
        record.plane_sequence_id = item.get("sequence_id")
        stats["updated"] += 1

    db.flush()

    if include_relations:
        stats["relations_linked"] = _pull_relations(db, link, client, seen)

    stats["stale_links"] += len(set(existing) - seen)
    stats["api_calls"] = client.calls - stats.pop("api_calls_before")
    link.last_synced_at = datetime.datetime.utcnow()
    link.last_sync_stats = stats
    db.commit()
    return stats


def _pull_relations(db: Session, link: PlaneProjectLink, client: PlaneClient, seen: set) -> int:
    """Import blocked_by edges as the PMO's task-id dependency list."""
    links = db.query(PlaneLink).filter(PlaneLink.project_id == link.project_id).all()
    by_plane_id = {l.plane_work_item_id: l for l in links}
    edges = 0
    for l in links:
        if l.plane_work_item_id not in seen:
            continue
        payload = client.relations(link.plane_project_id, l.plane_work_item_id)
        blockers = [r.get("issue_id") for r in payload.get("blocked_by", []) if r.get("issue_id")]
        dep_task_ids = sorted({
            by_plane_id[b].task_id for b in blockers if b in by_plane_id
        })
        task = db.query(Task).filter(Task.id == l.task_id).first()
        if task is None:
            continue
        if list(task.dependencies or []) != dep_task_ids:
            task.dependencies = dep_task_ids
            task.updated_at = datetime.datetime.utcnow()
        edges += len(dep_task_ids)
    return edges


def make_client() -> PlaneClient:
    return PlaneClient(
        base_url=plane_config.base_url(),
        workspace=plane_config.workspace(),
        api_key=plane_config.api_key(),
    )


def sync_project(db: Session, project_id: int, include_relations: bool = False,
                 client: PlaneClient | None = None) -> dict:
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise ValueError(f"project {project_id} is not linked to a Plane project")
    return pull(db, link, client or make_client(), include_relations=include_relations)
