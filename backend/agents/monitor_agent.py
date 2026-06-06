"""Monitor Agent — watches task progress and flags issues."""
import json
import datetime
from sqlalchemy.orm import Session
from backend.models import Project, Task, AgentAction, TaskStatus
from backend.agents.base import create_agent_action, parse_json_response
from backend.services import llm_service


async def run_monitor_agent(project_id: int, db: Session) -> dict:
    """Analyse all tasks in a project and flag risks / delays."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "Project not found"}

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    if not tasks:
        return {"status": "no_tasks", "message": "No tasks to monitor."}

    # Build a summary for the LLM
    now = datetime.datetime.utcnow()
    task_lines = []
    for t in tasks:
        overdue = ""
        if t.due_date and t.due_date < now and t.status not in ("done", "review"):
            overdue = " [OVERDUE]"
        task_lines.append(
            f"- [{t.status}] {t.title} (priority: {t.priority}, est: {t.estimated_hours}h"
            f"{', due: ' + t.due_date.strftime('%Y-%m-%d') if t.due_date else ''}){overdue}"
        )

    tasks_summary = "\n".join(task_lines)
    raw = await llm_service.monitor_tasks(project.name, tasks_summary)
    data = parse_json_response(raw)

    # Log findings
    risks = data.get("risks", [])
    recommendations = data.get("recommendations", [])
    health_score = data.get("health_score", 50)

    if risks or health_score < 70:
        severity = "critical" if health_score < 40 else ("warning" if health_score < 70 else "info")
        await create_agent_action(
            db, project_id, "monitor", "health_check",
            data.get("summary", f"Health score: {health_score}/100"),
            details={
                "health_score": health_score,
                "risks": risks,
                "recommendations": recommendations,
                "blocked_dependencies": data.get("blocked_dependencies", []),
                "task_count": len(tasks),
                "overdue_count": sum(1 for t in tasks if t.due_date and t.due_date < now
                                     and t.status not in ("done", "review")),
            },
            severity=severity,
        )

    return {
        "status": "monitored",
        "health_score": health_score,
        "risks": risks,
        "recommendations": recommendations,
        "summary": data.get("summary", ""),
    }
