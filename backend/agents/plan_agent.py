"""Plan Agent — turns project briefs into structured execution plans."""
import json
import datetime
from sqlalchemy.orm import Session
from backend.models import Project, Task, Milestone, Priority, TaskStatus
from backend.agents.base import create_agent_action, parse_json_response
from backend.services import llm_service


async def run_plan_agent(project_id: int, db: Session, additional_context: str = "") -> dict:
    """Generate a full project plan from the project brief."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "Project not found"}

    # If project already has tasks, don't regenerate — return existing
    existing_tasks = db.query(Task).filter(Task.project_id == project_id).count()
    if existing_tasks > 0:
        tasks = db.query(Task).filter(Task.project_id == project_id).all()
        return {
            "status": "already_planned",
            "message": f"Project already has {existing_tasks} tasks.",
            "tasks": tasks,
        }

    context = f"{project.goal}\n{project.description}\n{additional_context}"

    raw = await llm_service.generate_plan(project.name, project.goal or project.name, context)
    data = parse_json_response(raw)

    created_tasks = []
    created_milestones = []
    title_to_task = {}

    # Create phases → tasks
    phases = data.get("phases", [])
    if not phases:
        # If LLM didn't return structured data, create default tasks
        phases = [{"name": "Phase 1: Execution", "tasks": [
            {"title": f"Initiate {project.name}", "description": "Kick off project work",
             "estimated_hours": 8, "priority": "high"},
        ]}]

    sort = 0
    for phase in phases:
        phase_name = phase.get("name", "Phase")
        tasks_list = phase.get("tasks", [])

        for t in tasks_list:
            task = Task(
                project_id=project_id,
                title=t.get("title", f"Task for {phase_name}"),
                description=t.get("description", ""),
                status=TaskStatus.todo.value,
                priority=t.get("priority", Priority.medium.value),
                estimated_hours=float(t.get("estimated_hours", 4)),
                sort_order=sort,
                due_date=None,
            )
            if t.get("dependencies"):
                task.dependencies = t["dependencies"]
            db.add(task)
            db.flush()
            created_tasks.append(task)
            title_to_task[task.title] = task.id
            sort += 1

    # Resolve dependency titles to IDs
    for task in created_tasks:
        if task.dependencies:
            resolved = []
            for dep_title in task.dependencies:
                if isinstance(dep_title, str) and dep_title in title_to_task:
                    resolved.append(title_to_task[dep_title])
            task.dependencies = resolved

    # Create milestones
    for m in data.get("milestones", []):
        milestone = Milestone(
            project_id=project_id,
            title=m.get("title", "Milestone"),
            description=m.get("description", ""),
            due_date=None,
            status=TaskStatus.todo.value,
        )
        db.add(milestone)
        db.flush()
        created_milestones.append(milestone)

    # Log the agent action
    summary = data.get("summary", f"Generated plan for {project.name}")
    await create_agent_action(
        db, project_id, "plan", "plan_generated",
        summary,
        details={
            "phases": len(phases),
            "tasks_created": len(created_tasks),
            "milestones_created": len(created_milestones),
            "total_estimated_hours": data.get("total_estimated_hours", 0),
        },
        severity="info",
    )

    project.status = "active"
    db.commit()

    return {
        "status": "planned",
        "plan_summary": data.get("summary", ""),
        "total_estimated_hours": data.get("total_estimated_hours", 0),
        "tasks": created_tasks,
        "milestones": created_milestones,
    }
