"""Agents router — triggers AI agents and returns actions log."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.audit import audit
from backend.auth import contributor_up, pmo_lead_up
from backend.database import get_db
from backend.models import AgentAction, User
from backend.schemas import PlanRequest, PlanResponse, AgentActionOut
from backend.agents.plan_agent import run_plan_agent
from backend.agents.monitor_agent import run_monitor_agent
from backend.agents.alert_agent import run_alert_agent

router = APIRouter(prefix="/api/projects/{project_id}/agents", tags=["agents"])


def _audit_run(db, actor: User, project_id: int, agent: str):
    """Record who triggered an agent, durably and before the run starts.

    Unlike the other audit sites there is no handler-level commit to
    piggyback on: the commit lives inside the agent, and monitor only makes
    one when it finds risks (a healthy or task-less project writes nothing),
    which would silently roll the audit row back at request end. The row is
    therefore the handler's own transaction — and because it precedes the
    run, it records the trigger even when the run itself then fails."""
    audit(db, actor=actor.username, actor_role=actor.role, action="agent_run",
          target_type="project", target_id=project_id, detail={"agent": agent})
    db.commit()


@router.post("/plan")
async def trigger_plan(project_id: int, body: PlanRequest, db: Session = Depends(get_db),
                       actor: User = Depends(pmo_lead_up)):
    """Run the Plan Agent on a project."""
    from backend.models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _audit_run(db, actor, project_id, "plan")
    result = await run_plan_agent(project_id, db, body.additional_context)
    return result


@router.post("/monitor")
async def trigger_monitor(project_id: int, db: Session = Depends(get_db),
                          actor: User = Depends(pmo_lead_up)):
    """Run the Monitor Agent to assess project health."""
    from backend.models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _audit_run(db, actor, project_id, "monitor")
    result = await run_monitor_agent(project_id, db)
    return result


@router.post("/alert")
async def trigger_alert(project_id: int, anomaly: str = "", db: Session = Depends(get_db),
                        actor: User = Depends(pmo_lead_up)):
    """Run the Alert Agent — pass an optional anomaly description."""
    from backend.models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    _audit_run(db, actor, project_id, "alert")
    result = await run_alert_agent(project_id, db, anomaly_description=anomaly)
    return result


@router.get("/actions", response_model=list[AgentActionOut])
def list_actions(project_id: int, db: Session = Depends(get_db)):
    """Get all agent actions for a project."""
    actions = (
        db.query(AgentAction)
        .filter(AgentAction.project_id == project_id)
        .order_by(AgentAction.created_at.desc())
        .limit(100)
        .all()
    )
    return actions


@router.patch("/actions/{action_id}/resolve", dependencies=[Depends(contributor_up)])
def resolve_action(project_id: int, action_id: int, db: Session = Depends(get_db)):
    """Mark an agent action as resolved. Contributor rather than pmo_lead:
    acknowledging a recommendation records a decision, it does not edit the
    plan the agent proposed."""
    action = db.query(AgentAction).filter(
        AgentAction.id == action_id,
        AgentAction.project_id == project_id,
    ).first()
    if not action:
        raise HTTPException(404, "Action not found")
    action.resolved = 1
    action.resolved_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"ok": True}
