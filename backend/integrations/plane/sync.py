"""Plane → PMO pull.

Phase 1 of the integration: read-only. It creates or updates the PMO tasks that Plane owns, records
the join in `plane_links`, and imports the typed dependency edges as the PMO's task-id list so the
Monitor agent can finally see a predecessor relationship.

Nothing here writes to Plane. Deletions on the Plane side are reported as stale links rather than
applied locally: a transient API error must never delete a client's plan.
"""
import datetime
import hashlib
import html as html_lib
import json
import re

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

HASH_FIELDS = ("name", "priority", "state", "target_date", "start_date", "archived_at",
               "description_html")

_TAG_RE = re.compile(r"<[^>]+>")
_ESTIMATE_RE = re.compile(r"estimate:\s*([0-9]+(?:\.[0-9]+)?)\s*h", re.IGNORECASE)


def _strip_html(value) -> str:
    """Plane returns description_html, not description_stripped, on the v1 work-item read."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _estimate_hours(text: str) -> float:
    """Pull the pack's estimate back out of the description.

    Plane has no hours field, so when the PMO pushes a pack it writes "Estimate: 80 h" into the
    description. Reading that back keeps the PMO's health and capacity maths meaningful instead of
    scoring every task as zero hours.
    """
    match = _ESTIMATE_RE.search(text or "")
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


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


def _apply_item(db: Session, link: PlaneProjectLink, states: dict, members: dict,
                item: dict, existing_map: dict, next_sort: int) -> tuple[str, int]:
    """Create or update the PMO task a single work item owns. Returns (outcome, next_sort)."""
    wid = item["id"]
    digest = _content_hash(item)
    plain = _strip_html(item.get("description_html"))
    fields = {
        "title": (item.get("name") or "Untitled")[:300],
        "status": _status_for(item, states),
        "priority": PRIORITY_TO_PMO.get((item.get("priority") or "medium").lower(), "medium"),
        "assignee": _assignee_label(item, members),
        "due_date": _parse_date(item.get("target_date")),
        "description": plain[:2000],
        "estimated_hours": _estimate_hours(plain),
    }
    state_name = states.get(item.get("state"), {}).get("name", "")[:80]

    record = existing_map.get(wid)
    if record is None:
        task = Task(project_id=link.project_id, sort_order=next_sort, **fields)
        db.add(task)
        db.flush()
        db.add(PlaneLink(
            project_id=link.project_id, task_id=task.id,
            plane_work_item_id=wid, plane_sequence_id=item.get("sequence_id"),
            plane_state_name=state_name,
            content_hash=digest, last_pulled_at=datetime.datetime.utcnow(),
        ))
        return "created", next_sort + 1

    if record.content_hash == digest:
        record.last_pulled_at = datetime.datetime.utcnow()
        return "unchanged", next_sort

    task = db.query(Task).filter(Task.id == record.task_id).first()
    if task is None:
        return "stale_links", next_sort

    for key, value in fields.items():
        setattr(task, key, value)
    task.updated_at = datetime.datetime.utcnow()
    record.content_hash = digest
    record.last_pulled_at = datetime.datetime.utcnow()
    record.plane_state_name = state_name
    record.plane_sequence_id = item.get("sequence_id")
    return "updated", next_sort


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
        outcome, next_sort = _apply_item(db, link, states, members, item, existing, next_sort)
        stats[outcome] = stats.get(outcome, 0) + 1

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


def pull_work_item(db: Session, link: PlaneProjectLink, client: PlaneClient,
                   work_item_id: str) -> dict:
    """Refresh exactly one work item — the webhook path, where a full pull would be wasteful.

    Costs 2–3 API calls instead of ~4 for a whole project, and it is the only way an edit made in
    Plane reaches the PMO in seconds rather than at the next scheduled reconcile.
    """
    before = client.calls
    item = client.work_item(link.plane_project_id, work_item_id)
    states = {s["id"]: {"name": s.get("name", ""), "group": s.get("group", "")}
              for s in client.states(link.plane_project_id)}
    members = {}
    try:
        for m in client.paginate("/members/"):
            members[m.get("member")] = m.get("display_name") or m.get("email") or m.get("member")
    except Exception:
        members = {}

    existing = {l.plane_work_item_id: l for l in
                db.query(PlaneLink).filter(PlaneLink.project_id == link.project_id).all()}
    next_sort = (
        db.query(Task.sort_order).filter(Task.project_id == link.project_id)
        .order_by(Task.sort_order.desc()).first()
    )
    next_sort = (next_sort[0] + 1) if next_sort else 0

    outcome, _ = _apply_item(db, link, states, members, item, existing, next_sort)
    db.commit()
    return {
        "work_item_id": work_item_id,
        "outcome": outcome,
        "api_calls": client.calls - before,
    }


def reconcile_for_project(db: Session, project_id: int, client: PlaneClient | None = None) -> dict:
    """Full pull with relations: the nightly safety net under the webhooks.

    Webhooks can be missed — Plane disables a hook after five failed deliveries, and any event
    delivered while the PMO was restarting is simply gone. This compares every linked work item
    against Plane and reports how many had diverged, rather than trusting the event stream.
    """
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise ValueError(f"project {project_id} is not linked to a Plane project")
    stats = pull(db, link, make_client() if client is None else client, include_relations=True)
    stats["project_id"] = project_id
    stats["diverged"] = stats.get("updated", 0)
    return stats


def sync_project(db: Session, project_id: int, include_relations: bool = False,
                 client: PlaneClient | None = None) -> dict:
    link = db.query(PlaneProjectLink).filter(PlaneProjectLink.project_id == project_id).first()
    if link is None:
        raise ValueError(f"project {project_id} is not linked to a Plane project")
    return pull(db, link, client or make_client(), include_relations=include_relations)
