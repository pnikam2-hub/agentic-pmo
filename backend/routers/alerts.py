"""Alert endpoints — test alert channels and manage webhook subscriptions."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.auth import require_auth
from backend.models import WebhookSubscription
from backend.services.alert_channels import (
    dispatch_alert, email_configured, webhook_configured,
)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class TestAlertRequest(BaseModel):
    subject: str = "Test alert from Agentic PMO"
    body: str = "This is a test alert. If you received this, your alert channels are working."
    severity: str = "info"
    project_name: str = "Test"


@router.get("/status")
def alert_status():
    """Check which alert channels are configured."""
    return {
        "email": email_configured(),
        "webhook": webhook_configured(),
    }


@router.post("/test")
async def test_alert(body: TestAlertRequest, auth_user: str = Depends(require_auth)):
    """Send a test alert to all configured channels."""
    results = await dispatch_alert(
        subject=body.subject,
        body=body.body,
        severity=body.severity,
        project_name=body.project_name,
    )
    return {"results": results}


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str] = ["alert", "monitor"]


@router.get("/webhooks")
def list_webhooks(db: Session = Depends(get_db), auth_user: str = Depends(require_auth)):
    hooks = db.query(WebhookSubscription).all()
    return [
        {"id": h.id, "name": h.name, "url": h.url, "events": h.events,
         "created_at": h.created_at.isoformat() if h.created_at else None}
        for h in hooks
    ]


@router.post("/webhooks")
def register_webhook(body: WebhookCreate, db: Session = Depends(get_db),
                      auth_user: str = Depends(require_auth)):
    hook = WebhookSubscription(name=body.name, url=body.url, events=body.events)
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return {"id": hook.id, "name": hook.name, "url": hook.url, "events": hook.events}


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, db: Session = Depends(get_db),
                   auth_user: str = Depends(require_auth)):
    hook = db.query(WebhookSubscription).filter(WebhookSubscription.id == webhook_id).first()
    if not hook:
        raise HTTPException(404, "Webhook not found")
    db.delete(hook)
    db.commit()
    return {"ok": True}
