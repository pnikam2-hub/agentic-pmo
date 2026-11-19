"""Inbound Plane webhooks: verify the signature, dedupe the delivery, refresh what changed.

Three rules govern this file, each learned from how Plane actually behaves:

1. **Verify the signature before parsing anything else.** The HMAC is the only authentication on
   this endpoint — it cannot sit behind the JWT dependency, because Plane has no user session.

2. **Accept a delivery only once.** Plane retries with exponential backoff, so the same event will
   arrive more than once; `delivery_id` is the dedupe key.

3. **Return 2xx even when the processing fails.** Plane treats a 4xx as a permanent rejection and
   disables a webhook after five non-2xx in a row. A swallowed error here is recoverable — the
   nightly reconcile repairs it — whereas a disabled webhook is silently dead. So failures are
   recorded in `plane_webhook_events` with status `error`, not raised at the caller.
"""
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from backend.integrations.plane import sync
from backend.models import PlaneLink, PlaneProjectLink

# Plane computes its signature over `json.dumps(payload)` with default separators, but sends the
# body through httpx, which serialises compactly. The two are not byte-identical, so a strict
# HMAC-over-raw-body check fails. Try the plausible canonicalisations and record which one matched.
SIGNATURE_SCHEMES = ("raw", "dumps", "compact", "dumps_sorted", "compact_sorted")


def _variants(raw: bytes, parsed: dict) -> dict:
    return {
        "raw": raw,
        "dumps": json.dumps(parsed).encode(),
        "compact": json.dumps(parsed, separators=(",", ":")).encode(),
        "dumps_sorted": json.dumps(parsed, sort_keys=True).encode(),
        "compact_sorted": json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode(),
    }


def verify(raw: bytes, signature: str, secret: str) -> str | None:
    """Return the name of the canonicalisation that matched, or None."""
    if not signature or not secret:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    for scheme, payload in _variants(raw, parsed).items():
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature.strip()):
            return scheme
    return None


def normalise(payload: dict) -> tuple[str, str, dict]:
    """Map both payload generations onto (entity, action, data).

    v1 (the AGPL tree): {"event": "issue", "action": "updated", "data": {...}}
    v2 (commercial/cloud): {"event": "workitem.updated", "data": {...}}
    """
    event = (payload.get("event") or "").strip()
    data = payload.get("data") or {}
    action = (payload.get("action") or "").strip().lower()

    if "." in event:
        head, _, tail = event.partition(".")
        return head, (action or tail), data

    if not action:
        action = {"post": "created", "patch": "updated", "delete": "deleted",
                  "create": "created", "update": "updated"}.get(
            (payload.get("action") or "").lower(), "")
    return event, action, data


WORK_ITEM_EVENTS = {"issue", "workitem", "work_item"}


def handle(db: Session, payload: dict) -> dict:
    """Refresh the PMO task behind an event. Never raises; returns what it did."""
    entity, action, data = normalise(payload)
    entity_id = data.get("id") or payload.get("entity_id")

    if entity not in WORK_ITEM_EVENTS:
        return {"handled": False, "reason": f"event '{entity}' is recorded but not acted on"}

    if action in ("deleted", "delete", "archived"):
        # A deletion in Plane must not delete a client's plan locally; the nightly reconcile
        # reports it as a stale link instead.
        return {"handled": False, "reason": f"action '{action}' leaves the link stale, not deleted"}

    if action not in {"created", "create", "updated", "update"}:
        return {"handled": False, "reason": f"unrecognised action '{action}'"}

    if not entity_id:
        return {"handled": False, "reason": "no entity id in payload"}

    link = db.query(PlaneLink).filter(PlaneLink.plane_work_item_id == str(entity_id)).first()
    client = sync.make_client()

    if link is not None:
        project_link = (db.query(PlaneProjectLink)
                        .filter(PlaneProjectLink.project_id == link.project_id).first())
        if project_link is None:
            return {"handled": False, "reason": "work item linked to a project with no Plane link"}
        result = sync.pull_work_item(db, project_link, client, str(entity_id))
        return {"handled": True, "mode": "single_item", **result}

    # A work item we have never seen: it belongs to a linked project only if the payload says so.
    plane_project_id = data.get("project") or data.get("project_id")
    if not plane_project_id:
        return {"handled": False, "reason": "unknown work item and no project in payload"}
    project_link = (db.query(PlaneProjectLink)
                    .filter(PlaneProjectLink.plane_project_id == str(plane_project_id)).first())
    if project_link is None:
        return {"handled": False, "reason": "project is not linked to this PMO"}
    stats = sync.pull(db, project_link, client)
    return {"handled": True, "mode": "project_pull", **stats}
