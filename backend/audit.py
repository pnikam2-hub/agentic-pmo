"""Audit trail — one row per security-relevant action.

The rule: an audit row records who did what to which object, and never contains
a password, a password hash, or a token. Those are secrets, not facts.
"""
from sqlalchemy.orm import Session

from backend.models import AuditLog

# Every action name the codebase may write. audit() refuses anything outside
# this tuple, so a typo in an action string fails loudly at build time instead
# of silently creating a new action name that nothing queries.
ACTIONS = (
    "login_success",
    "login_failed",
    "access_denied",         # a role guard refused an authenticated request
    "password_changed",      # a user changed their own password
    "user_created",
    "user_updated",          # role / display_name / is_active change via admin
    "user_password_reset",   # admin reset, no old password needed
    "user_deactivated",
    "project_created",
    "project_updated",
    "project_deleted",
    "task_deleted",
    "agent_run",
    "plane_push",
    "plane_sync",
    "plane_linked",
)


def audit(
    db: Session,
    actor: str,
    action: str,
    target_type: str = None,
    target_id: str = None,
    detail: dict = None,
    actor_role: str = None,
    ip: str = None,
):
    """Append one audit row. Adds to the session but does not commit — the
    caller's request owns the transaction and decides when it is durable."""
    if action not in ACTIONS:
        raise ValueError(
            f"Unknown audit action '{action}'. Known actions: {', '.join(ACTIONS)}"
        )
    row = AuditLog(
        actor=actor,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail or {},
        ip=ip,
    )
    db.add(row)
    return row
