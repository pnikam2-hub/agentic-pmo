"""Agents router — triggers AI agents and returns actions log."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import AgentAction
from backend.schemas import PlanRequest, PlanResponse, AgentActionOut
from backend.agents.plan_agent import run_plan_agent
from backend.agents.monitor_agent import run_monitor_agent
from backend.agents.alert_agent import run_alert_agent

router = APIRouter(prefix="/api/projects/{project_id}/agents", tags=["agents"])


@router.post("/plan")
async def trigger_plan(project_id: int, body: PlanRequest, db: Session = Depends(get_db)):
    """Run the Plan Agent on a project."""
    result = await run_plan_agent(project_id, db, body.additional_context)
    return result


@router.post("/monitor")
async def trigger_monitor(project_id: int, db: Session = Depends(get_db)):
    """Run the Monitor Agent to assess project health."""
    result = await run_monitor_agent(project_id, db)
    return result


@router.post("/alert")
async def trigger_alert(project_id: int, anomaly: str = "", db: Session = Depends(get_db)):
    """Run the Alert Agent — pass an optional anomaly description."""
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


@router.patch("/actions/{action_id}/resolve")
def resolve_action(project_id: int, action_id: int, db: Session = Depends(get_db)):
    """Mark an agent action as resolved."""
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
