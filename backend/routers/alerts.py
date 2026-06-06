"""Alert endpoints — test alert channels and manage webhook subscriptions."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.auth import require_auth
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


class WebhookSubscription(BaseModel):
    name: str
    url: str
    events: list[str] = ["alert", "monitor"]


_webhooks = {}  # Simple in-memory store for MVP


@router.get("/webhooks")
def list_webhooks(auth_user: str = Depends(require_auth)):
    return [{"id": k, **v} for k, v in _webhooks.items()]


@router.post("/webhooks")
def register_webhook(body: WebhookSubscription, auth_user: str = Depends(require_auth)):
    idx = len(_webhooks) + 1
    _webhooks[str(idx)] = body.model_dump()
    return {"id": str(idx), **body.model_dump()}


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, auth_user: str = Depends(require_auth)):
    if webhook_id not in _webhooks:
        raise HTTPException(404, "Webhook not found")
    del _webhooks[webhook_id]
    return {"ok": True}
