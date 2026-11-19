"""Public webhook receiver for Plane.

Deliberately a separate router from the rest of the integration, because this is the one endpoint
that must not sit behind the JWT dependency — Plane authenticates with an HMAC signature, not a user
session.
"""
import datetime
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.integrations.plane import config as plane_config
from backend.integrations.plane import webhook as plane_webhook
from backend.models import PlaneWebhookEvent

logger = logging.getLogger("agentic-pmo.plane.webhook")

router = APIRouter(prefix="/api/integrations/plane", tags=["plane-webhook"])


@router.post("/webhook")
async def receive_plane_event(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    secret = plane_config.webhook_secret()
    if not secret:
        # Fail closed: without a secret every delivery is unverifiable, so none are accepted.
        raise HTTPException(503, "Plane webhook secret is not configured")

    signature = request.headers.get("x-plane-signature", "")
    scheme = plane_webhook.verify(raw, signature, secret)
    if scheme is None:
        logger.warning("Rejected Plane webhook with an invalid signature")
        raise HTTPException(401, "invalid signature")

    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "body is not valid JSON")

    delivery_id = request.headers.get("x-plane-delivery") or payload.get("delivery_id") or ""
    if delivery_id:
        seen = (db.query(PlaneWebhookEvent)
                .filter(PlaneWebhookEvent.delivery_id == delivery_id).first())
        if seen:
            return {"status": "duplicate", "delivery_id": delivery_id}

    entity, action, data = plane_webhook.normalise(payload)
    row = PlaneWebhookEvent(
        delivery_id=delivery_id or None,
        event=entity,
        action=action,
        entity_id=str((data or {}).get("id") or payload.get("entity_id") or "")[:64] or None,
        workspace_slug=(payload.get("workspace_slug") or "")[:80],
        signature_scheme=scheme,
        status="received",
    )
    db.add(row)
    db.commit()
    row_id = row.id

    try:
        result = plane_webhook.handle(db, payload)
        row.status = "ok" if result.get("handled") else "ignored"
        row.detail = result
    except Exception as exc:  # noqa: BLE001 — see module docstring in webhook.py
        db.rollback()
        logger.exception("Plane webhook processing failed")
        row = db.query(PlaneWebhookEvent).filter(PlaneWebhookEvent.id == row_id).first()
        row.status = "error"
        row.detail = {"error": f"{type(exc).__name__}: {exc}"[:400]}

    row.processed_at = datetime.datetime.utcnow()
    db.commit()
    return {"status": row.status, **(row.detail or {})}
