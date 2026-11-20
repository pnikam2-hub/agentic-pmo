"""Audit trail — one row per security-relevant action.

The rule: an audit row records who did what to which object, and never contains
a password, a password hash, or a token. Those are secrets, not facts.
"""
from sqlalchemy.orm import Session

from backend.audit_chain import canonical_payload, hash_link, head
from backend.models import AuditChain, AuditLog

# Every action name the codebase may write. audit() refuses anything outside
# this tuple, so a typo in an action string fails loudly at build time instead
# of silently creating a new action name that nothing queries.
ACTIONS = (
    "login_success",
    "login_failed",
    "login_throttled",       # per-identifier lockout refused a login before password check
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
    "sso_login",
    "sso_login_failed",
    "sso_user_provisioned",
    "sso_user_linked",
    "sso_role_updated",
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
    """Append one audit row and its hash-chain link, in the caller's transaction.

    Adds to the session but does not commit — the caller's request owns the
    transaction and decides when it is durable, so the audit row and its link
    land together or not at all.

    The link is what makes the trail tamper-evident: its ``hash`` commits to the
    audit row's contents and to the previous link's hash, so a later edit, an
    insertion, or a gap *within* the chain breaks it. What the chain cannot
    prove is the deletion of a *suffix* — the last N rows truncate to a shorter,
    still-clean chain — which is why backend.audit_chain.append_anchor records
    the head outside the database.
    """
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
    db.flush()   # assign the audit id (and its at timestamp) before the link references them
    seq, prev_hash = head(db)
    db.add(AuditChain(
        seq=seq + 1,
        audit_id=row.id,
        prev_hash=prev_hash,
        hash=hash_link(prev_hash, canonical_payload(row)),
    ))
    return row
