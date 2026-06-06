"""Alert channels — email and webhook dispatch for agent alerts."""
import os
import json
import smtplib
import logging
from email.message import EmailMessage
from typing import Optional
import httpx

logger = logging.getLogger("agentic-pmo.alert_channels")

# ── Email config ────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

# ── Webhook config ──────────────────────────────────────────────────────
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


def email_configured() -> bool:
    """Check if email alert channel is configured."""
    return bool(SMTP_HOST and SMTP_USER and ALERT_EMAIL_TO)


def webhook_configured() -> bool:
    """Check if webhook alert channel is configured."""
    return bool(ALERT_WEBHOOK_URL)


async def send_email_alert(
    subject: str,
    body: str,
    severity: str = "info",
    project_name: str = "",
) -> dict:
    """Send an alert via email."""
    if not email_configured():
        return {"sent": False, "channel": "email", "reason": "not configured"}

    try:
        msg = EmailMessage()
        msg.set_content(f"Project: {project_name}\nSeverity: {severity}\n\n{body}")
        msg["Subject"] = f"[Agentic PMO] {subject}"
        msg["From"] = SMTP_FROM or SMTP_USER
        msg["To"] = ALERT_EMAIL_TO

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email alert sent to {ALERT_EMAIL_TO}: {subject}")
        return {"sent": True, "channel": "email", "to": ALERT_EMAIL_TO}
    except Exception as exc:
        logger.error(f"Failed to send email alert: {exc}")
        return {"sent": False, "channel": "email", "error": str(exc)}


async def send_webhook_alert(
    subject: str,
    body: str,
    severity: str = "info",
    project_name: str = "",
    details: dict = None,
) -> dict:
    """Send an alert via webhook POST."""
    if not webhook_configured():
        return {"sent": False, "channel": "webhook", "reason": "not configured"}

    payload = {
        "event": "agentic_pmo_alert",
        "severity": severity,
        "project": project_name,
        "subject": subject,
        "body": body,
        "details": details or {},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                ALERT_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        logger.info(f"Webhook alert sent to {ALERT_WEBHOOK_URL}: {subject}")
        return {"sent": True, "channel": "webhook", "url": ALERT_WEBHOOK_URL}
    except Exception as exc:
        logger.error(f"Failed to send webhook alert: {exc}")
        return {"sent": False, "channel": "webhook", "error": str(exc)}


async def dispatch_alert(
    subject: str,
    body: str,
    severity: str = "info",
    project_name: str = "",
    details: dict = None,
) -> list[dict]:
    """Dispatch an alert to all configured channels. Returns results."""
    results = []

    if email_configured():
        result = await send_email_alert(subject, body, severity, project_name)
        results.append(result)

    if webhook_configured():
        result = await send_webhook_alert(subject, body, severity, project_name, details)
        results.append(result)

    if not results:
        results.append({"sent": False, "channel": "none", "reason": "no channels configured"})

    return results
