"""Scheduler — periodic monitor runs and automated health checks."""
import os
import json
import logging
import datetime
from typing import Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.database import SessionLocal
from backend.models import Project
from backend.agents.monitor_agent import run_monitor_agent
from backend.services.alert_channels import dispatch_alert

logger = logging.getLogger("agentic-pmo.scheduler")

scheduler = AsyncIOScheduler()
_job_registered = False

# Config from .env
MONITOR_INTERVAL_MINUTES = int(os.getenv("MONITOR_INTERVAL_MINUTES", "0"))
# Nightly reconcile of every linked Plane project; empty disables it.
RECONCILE_TIME = os.getenv("PLANE_RECONCILE_TIME", "02:30").strip()


async def _run_plane_reconcile():
    """Full pull with relations for every linked project — repairs what webhooks missed."""
    from backend.integrations.plane.sync import reconcile_for_project
    from backend.models import PlaneProjectLink

    logger.info("Plane reconcile: starting")
    db: Session = SessionLocal()
    try:
        links = db.query(PlaneProjectLink).all()
        for link in links:
            try:
                stats = reconcile_for_project(db, link.project_id)
                logger.info(
                    "Plane reconcile: project %s — %s updated, %s unchanged, %s stale",
                    link.project_id, stats.get("updated"), stats.get("unchanged"),
                    stats.get("stale_links"),
                )
                if stats.get("diverged"):
                    await dispatch_alert(
                        subject=f"Plane reconcile: {stats['diverged']} task(s) had drifted",
                        body=(
                            f"Project {link.project_id} ({link.plane_project_name}) was out of step "
                            f"with Plane and has been corrected by the nightly reconcile.\n"
                            f"updated={stats.get('updated')} unchanged={stats.get('unchanged')} "
                            f"stale={stats.get('stale_links')}\n"
                        ),
                        severity="info",
                        project_name=link.plane_project_name or str(link.project_id),
                        details=stats,
                    )
            except Exception as e:  # one broken project must not stop the rest
                logger.error("Plane reconcile failed for project %s: %s", link.project_id, e)
    finally:
        db.close()
    logger.info("Plane reconcile: complete")


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
    """Start the background scheduler if anything is configured."""
    global _job_registered
    if _job_registered:
        return

    registered = False

    if MONITOR_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            _run_scheduled_monitor,
            trigger=IntervalTrigger(minutes=MONITOR_INTERVAL_MINUTES),
            id="monitor_all_projects",
            replace_existing=True,
            name="Monitor all active projects",
        )
        registered = True
        logger.info(f"Scheduler: monitoring every {MONITOR_INTERVAL_MINUTES} minutes")

    if RECONCILE_TIME:
        hour, _, minute = RECONCILE_TIME.partition(":")
        try:
            scheduler.add_job(
                _run_plane_reconcile,
                trigger=CronTrigger(hour=int(hour), minute=int(minute or 0)),
                id="plane_reconcile",
                replace_existing=True,
                name="Nightly Plane reconcile",
            )
            registered = True
            logger.info(f"Scheduler: Plane reconcile daily at {hour}:{minute or '00'} UTC")
        except ValueError:
            logger.warning(f"PLANE_RECONCILE_TIME={RECONCILE_TIME!r} is not HH:MM; reconcile disabled")

    if registered:
        scheduler.start()
        _job_registered = True
    else:
        logger.info(
            "Scheduler not started. Set MONITOR_INTERVAL_MINUTES or PLANE_RECONCILE_TIME to enable."
        )


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


import json
