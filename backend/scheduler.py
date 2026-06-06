"""Scheduler — periodic monitor runs and automated health checks."""
import os
import json
import logging
import datetime
from typing import Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.database import SessionLocal
from backend.models import Project
from backend.agents.monitor_agent import run_monitor_agent
from backend.services.alert_channels import dispatch_alert

logger = logging.getLogger("agentic-pmo.scheduler")

scheduler = AsyncIOScheduler()
_job_registered = False

# Config from .env
MONITOR_INTERVAL_MINUTES = int(os.getenv("MONITOR_INTERVAL_MINUTES", "0"))


async def _run_scheduled_monitor():
    """Run the monitor agent on all active projects."""
    logger.info("Scheduled monitor: checking all active projects...")
    db: Session = SessionLocal()
    try:
        projects = (
            db.query(Project)
            .filter(Project.status.in_(["planning", "active"]))
            .all()
        )
        for project in projects:
            try:
                result = await run_monitor_agent(project.id, db)
                health = result.get("health_score", 50)
                risks = result.get("risks", [])

                # Send alert for critical health scores
                if health < 50:
                    await dispatch_alert(
                        subject=f"🚨 Project health critical: {project.name} ({health}/100)",
                        body=(
                            f"Project: {project.name}\n"
                            f"Health Score: {health}/100\n"
                            f"Risks: {json.dumps(risks, indent=2) if risks else 'None'}\n"
                            f"Time: {datetime.datetime.now(datetime.UTC).isoformat()}"
                        ),
                        severity="critical" if health < 30 else "warning",
                        project_name=project.name,
                        details={"health_score": health, "risks": risks},
                    )
            except Exception as e:
                logger.error(f"Scheduled monitor failed for project {project.id}: {e}")
    finally:
        db.close()
    logger.info("Scheduled monitor complete.")


def start_scheduler():
    """Start the background scheduler if configured."""
    global _job_registered
    if _job_registered:
        return

    if MONITOR_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            _run_scheduled_monitor,
            trigger=IntervalTrigger(minutes=MONITOR_INTERVAL_MINUTES),
            id="monitor_all_projects",
            replace_existing=True,
            name="Monitor all active projects",
        )
        scheduler.start()
        logger.info(f"Scheduler started: monitoring every {MONITOR_INTERVAL_MINUTES} minutes")
        _job_registered = True
    else:
        logger.info("Scheduler not started. Set MONITOR_INTERVAL_MINUTES in .env to enable.")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


import json
