"""Base agent class — shared logic for all PMO agents."""
import json
import datetime
from sqlalchemy.orm import Session
from backend.models import Project, Task, AgentAction, Milestone
from backend.services import llm_service


async def create_agent_action(
    db: Session,
    project_id: int,
    agent_type: str,
    action_type: str,
    summary: str,
    details: dict = None,
    severity: str = "info",
) -> AgentAction:
    action = AgentAction(
        project_id=project_id,
        agent_type=agent_type,
        action_type=action_type,
        summary=summary,
        details=details or {},
        severity=severity,
        created_at=datetime.datetime.utcnow(),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM output (handles markdown fences)."""
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
