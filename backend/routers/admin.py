"""Admin router — user management and the audit trail. Admin role only."""
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.audit import audit
from backend.auth import (
    admin_only, hash_password, other_active_admins, validate_password, validate_role,
)
from backend.database import get_db
from backend.models import AuditLog, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_only)])

LAST_ADMIN_MESSAGE = (
    "Cannot demote or deactivate the last active admin — the system would have "
    "no way to administer users or roles afterwards."
)


class UserOut(BaseModel):
    """Explicit field list — password_hash must never serialise out."""
    id: int
    username: str
    email: Optional[str] = None
    display_name: str
    role: str
    is_active: bool
    source: str
    token_version: int
    created_at: datetime.datetime
    last_login_at: Optional[datetime.datetime] = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    display_name: str = ""
    role: str = "viewer"
    password: str


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    display_name: Optional[str] = None


class PasswordResetRequest(BaseModel):
    new_password: str


class AuditOut(BaseModel):
    id: int
    at: datetime.datetime
    actor: str
    actor_role: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: dict
    ip: Optional[str] = None

    model_config = {"from_attributes": True}


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user


def _other_active_admins(db: Session, user: User) -> int:
    """Thin wrapper over backend.auth.other_active_admins.

    The real definition lives in backend.auth so the admin router and the SSO
    callback share one notion of "last admin"; this wrapper exists so the
    stale-read simulation in test_rbac.py can monkeypatch only the pre-check.
    """
    return other_active_admins(db, user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    """Create a local user with a set password. Local, because oidc users are
    provisioned by the SSO flow in a later phase, never by hand."""
    try:
        validate_role(body.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        validate_password(body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    username = body.username.lower()
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(422, "Email must not be empty")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, f"Username '{username}' already exists")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, f"Email '{email}' already exists")

    user = User(
        username=username,
        email=email,
        display_name=body.display_name or username,
        password_hash=hash_password(body.password),
        role=body.role,
        source="local",
    )
    db.add(user)
    db.flush()   # assign the id before the audit row references it
    audit(db, actor=actor.username, actor_role=actor.role, action="user_created",
          target_type="user", target_id=user.id,
          detail={"username": username, "email": email, "role": body.role})
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    target = _get_user(db, user_id)
    if body.role is not None:
        try:
            validate_role(body.role)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    demoting = body.role is not None and body.role != "admin"
    deactivating = body.is_active is False
    removing_admin = target.role == "admin" and target.is_active == 1 and (demoting or deactivating)
    if removing_admin and _other_active_admins(db, target) == 0:
        raise HTTPException(400, LAST_ADMIN_MESSAGE)

    changes = {}
    if body.role is not None and body.role != target.role:
        changes["role"] = {"from": target.role, "to": body.role}
        target.role = body.role
    if body.is_active is not None and bool(target.is_active) != body.is_active:
        changes["is_active"] = {"from": bool(target.is_active), "to": body.is_active}
        target.is_active = 1 if body.is_active else 0
    if body.display_name is not None and body.display_name != target.display_name:
        changes["display_name"] = {"from": target.display_name, "to": body.display_name}
        target.display_name = body.display_name

    if not changes:
        return target   # nothing requested actually changed; no audit noise

    # A role change or a deactivation must not leave already-issued tokens
    # carrying the old authority, so every live token dies with the change.
    if "role" in changes or changes.get("is_active", {}).get("to") is False:
        target.token_version += 1

    if removing_admin:
        # The pre-check above can read a stale count: two concurrent requests
        # may each see the other admin before either commits. Re-verify the
        # invariant here, after the mutation and before commit, so a stale read
        # cannot remove the final admin. Correctness relies on SQLite's
        # serialised writer — the second writer blocks until the first commits,
        # so this post-write count sees the committed state. A move to Postgres
        # needs `SELECT … FOR UPDATE` on the admin rows instead, since its
        # writers do not serialise reads the same way.
        remaining_admins = other_active_admins(db, target)
        if remaining_admins == 0:
            db.rollback()
            raise HTTPException(400, LAST_ADMIN_MESSAGE)

    action = "user_deactivated" if changes.get("is_active", {}).get("to") is False else "user_updated"
    audit(db, actor=actor.username, actor_role=actor.role, action=action,
          target_type="user", target_id=target.id, detail={"changes": changes})
    db.commit()
    db.refresh(target)
    return target


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: int,
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    """Admin reset — no old password needed. The new value is never logged or
    audited; only the fact that a reset happened."""
    target = _get_user(db, user_id)
    try:
        validate_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    target.password_hash = hash_password(body.new_password)
    target.token_version += 1   # the user's old tokens die with their old password
    audit(db, actor=actor.username, actor_role=actor.role, action="user_password_reset",
          target_type="user", target_id=target.id, detail={"username": target.username})
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    """Soft delete: the row stays, is_active goes to 0, tokens die. Hard delete
    would orphan the audit trail's ability to name who acted."""
    target = _get_user(db, user_id)
    if target.is_active != 1:
        return {"ok": True}   # already inactive; deleting twice changes nothing
    removing_admin = target.role == "admin"
    if removing_admin and _other_active_admins(db, target) == 0:
        raise HTTPException(400, LAST_ADMIN_MESSAGE)
    target.is_active = 0
    target.token_version += 1
    if removing_admin:
        # Same stale-read re-check as update_user: re-count after the mutation
        # and before commit, so a concurrent request that passed the pre-check
        # against a stale count cannot leave the tenant with no admin.
        remaining_admins = other_active_admins(db, target)
        if remaining_admins == 0:
            db.rollback()
            raise HTTPException(400, LAST_ADMIN_MESSAGE)
    audit(db, actor=actor.username, actor_role=actor.role, action="user_deactivated",
          target_type="user", target_id=target.id, detail={"username": target.username})
    db.commit()
    return {"ok": True}


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    limit: int = Query(100, ge=1, le=500),
    actor: str = Query(""),
    action: str = Query(""),
    db: Session = Depends(get_db),
):
    """The audit trail, newest first. ids are monotonic, so ordering by id
    descending is ordering by insertion without timestamp ties."""
    q = db.query(AuditLog)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.id.desc()).limit(limit).all()
