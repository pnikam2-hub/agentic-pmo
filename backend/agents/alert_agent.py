"""Alert Agent — assesses anomalies and generates actionable alerts."""
import datetime
from sqlalchemy.orm import Session
from backend.models import Project, AgentAction
from backend.agents.base import create_agent_action, parse_json_response
from backend.services import llm_service
from backend.services.alert_channels import dispatch_alert


async def run_alert_agent(
    project_id: int,
    db: Session,
    anomaly_description: str = "",
) -> dict:
    """Assess a situation and generate an alert recommendation."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "Project not found"}

    # Auto-detect anomalies if no description given
    if not anomaly_description:
        anomaly_description = await _auto_detect_anomalies(project_id, db)

    raw = await llm_service.alert_on_anomaly(project.name, anomaly_description)
    data = parse_json_response(raw)

    severity = data.get("severity", "info")

    action = await create_agent_action(
        db, project_id, "alert", "anomaly_detected",
        data.get("summary", "Alert triggered"),
        details={
            "trigger": data.get("trigger", anomaly_description[:200]),
            "recommended_response": data.get("recommended_response", ""),
            "timeline_impact": data.get("timeline_impact", ""),
        },
        severity=severity,
    )

    # Dispatch to configured alert channels
    if project:
        await dispatch_alert(
            subject=f"[{severity.upper()}] {project.name}: {data.get('summary', 'Alert')[:80]}",
            body=(
                f"Project: {project.name}\n"
                f"Severity: {severity}\n"
                f"Trigger: {data.get('trigger', 'Unknown')}\n"
                f"Summary: {data.get('summary', '')}\n"
                f"Recommended response: {data.get('recommended_response', 'None')}\n"
                f"Timeline impact: {data.get('timeline_impact', 'Unknown')}"
            ),
            severity=severity,
            project_name=project.name,
            details={
                "trigger": data.get("trigger", ""),
                "recommended_response": data.get("recommended_response", ""),
                "timeline_impact": data.get("timeline_impact", ""),
            },
        )

    return {
        "status": "alerted",
        "severity": severity,
        "trigger": data.get("trigger", ""),
        "recommended_response": data.get("recommended_response", ""),
        "timeline_impact": data.get("timeline_impact", ""),
        "summary": data.get("summary", ""),
        "action_id": action.id,
    }


async def _auto_detect_anomalies(project_id: int, db: Session) -> str:
    """Scan project data for anything unusual."""
    from backend.models import Task
    now = datetime.datetime.utcnow()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()

    clues = []
    overdue = [t for t in tasks if t.due_date and t.due_date < now
               and t.status not in ("done", "review")]
    if overdue:
        clues.append(f"{len(overdue)} overdue tasks")

    blocked = [t for t in tasks if t.status == "blocked"]
    if blocked:
        clues.append(f"{len(blocked)} blocked tasks")

    no_estimate = [t for t in tasks if t.estimated_hours <= 0]
    if no_estimate:
        clues.append(f"{len(no_estimate)} tasks without time estimates")

    if not clues:
        clues.append("No obvious anomalies detected — routine check")

    return f"Project has {len(tasks)} tasks. Anomalies: {'; '.join(clues)}"
