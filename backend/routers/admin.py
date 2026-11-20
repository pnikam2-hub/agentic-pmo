"""Admin router — user management and the audit trail. Admin role only."""
import datetime
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.audit import audit
from backend import audit_chain
from backend.auth import (
    admin_only, hash_password, other_active_admins, validate_password, validate_role,
)
from backend.database import get_db
from backend.models import AuditChain, AuditLog, User

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


@router.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db)):
    """Recompute the chain and compare the head against the anchor.

    Returns the verify dict merged with the anchor comparison. An empty or
    pre-chain database returns ok=True — there is nothing to have tampered with
    yet — so this can never 500 on a fresh trail. On a clean check the head is
    re-anchored, which is what lets the next suffix truncation be detected.
    """
    result = audit_chain.verify(db)
    result.update(audit_chain.check_anchor(db))
    if result["ok"] and result.get("match", True):
        audit_chain.append_anchor(db)
    return result


@router.get("/audit/head")
def audit_head(db: Session = Depends(get_db)):
    """The current chain head, plus whether an anchor is configured."""
    seq, hash_ = audit_chain.head(db)
    return {"seq": seq, "hash": hash_, "anchor_configured": bool(audit_chain.anchor_path())}


# ── Audit export (CSV) ─────────────────────────────────────────────────────
# The column order is the contract this endpoint publishes; the header row below
# is generated from the same tuple so the two can never drift apart.
CSV_COLUMNS = (
    "at", "id", "seq", "actor", "actor_role", "action",
    "target_type", "target_id", "ip", "hash", "prev_hash", "detail",
)


def _csv_field(value: str) -> str:
    """RFC 4180-encode one cell.

    A field is quoted when it contains a comma, a double quote, a newline, or
    leading/trailing whitespace; inside a quoted field a double quote is
    doubled. The quoting is written here rather than delegated to the stdlib
    csv.writer, because csv.writer's minimal quoting does not quote a bare
    leading/trailing space — and the export is the artefact most likely to be
    emailed around, so it must survive every spreadsheet's parser exactly.
    """
    if value == "":
        return value
    if (
        "," in value
        or '"' in value
        or "\n" in value
        or "\r" in value
        or value != value.strip()
    ):
        return '"' + value.replace('"', '""') + '"'
    return value


def _csv_row(values) -> str:
    return ",".join(_csv_field(v) for v in values) + "\r\n"


def _cell(value) -> str:
    """A CSV cell from a possibly-None value — None exports as empty."""
    return "" if value is None else str(value)


def _detail_json(detail) -> str:
    """The audit detail as compact JSON — no newlines — so it stays one cell."""
    return json.dumps(detail or {}, separators=(",", ":"), default=str)


def _parse_since(value: str) -> datetime.datetime:
    """Parse an ISO date/datetime, normalised to naive UTC.

    ``AuditLog.at`` is stored naive-UTC (``datetime.utcnow``), so a ``since``
    carrying a timezone offset must be folded to naive UTC before comparison or
    the filter would silently miss everything.
    """
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            422, f"Invalid 'since' value '{value}' — expected an ISO date or datetime"
        )
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _audit_export_rows(db: Session, head_id: int, since, limit: int):
    """Yield the CSV lines for the export, newest first.

    The work is bounded by ``limit`` (the row cap) and ``head_id`` (the head
    read before the export row was written), so a very large trail is streamed
    rather than materialised as one list. ``seq``/``hash``/``prev_hash`` are
    taken from the chain link and left empty for pre-chain rows, where there is
    no link to read them from — never invented.
    """
    yield _csv_row(CSV_COLUMNS)
    q = (
        db.query(AuditLog, AuditChain)
        .outerjoin(AuditChain, AuditChain.audit_id == AuditLog.id)
        .filter(AuditLog.id <= head_id)
    )
    if since is not None:
        q = q.filter(AuditLog.at >= since)
    q = q.order_by(AuditLog.id.desc()).limit(limit)
    for audit_row, link in q:
        yield _csv_row((
            audit_row.at.isoformat() if audit_row.at is not None else "",
            _cell(audit_row.id),
            _cell(getattr(link, "seq", None)),
            _cell(audit_row.actor),
            _cell(audit_row.actor_role),
            _cell(audit_row.action),
            _cell(audit_row.target_type),
            _cell(audit_row.target_id),
            _cell(audit_row.ip),
            _cell(getattr(link, "hash", None)),
            _cell(getattr(link, "prev_hash", None)),
            _detail_json(audit_row.detail),
        ))


@router.get("/audit/export.csv")
def export_audit_csv(
    limit: int = Query(5000, ge=1, le=50000),
    since: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
):
    """Export the audit trail as RFC 4180 CSV, newest first. Admin only.

    Exporting the trail is itself a security event, so the trail must not be
    the one thing that does not know about it: an ``audit_exported`` row is
    written *before* streaming. To make sure that row never appears in the file
    it describes, the head (newest audit id) is read first, the export row is
    written, and the stream then stops at the head read — the export row, and
    any row written after the head read, carries a higher id and is excluded.
    """
    since_dt = _parse_since(since) if since is not None else None

    # Read the head before the export row exists; it is the boundary the stream
    # will stop at, so the export cannot contain the row that describes it.
    head_id = db.query(func.max(AuditLog.id)).scalar() or 0

    # Count what the stream will contain — same filters, same cap — so the
    # audit_exported row reports the true row count rather than an estimate.
    count_q = db.query(func.count(AuditLog.id)).filter(AuditLog.id <= head_id)
    if since_dt is not None:
        count_q = count_q.filter(AuditLog.at >= since_dt)
    exported = min(count_q.scalar() or 0, limit)

    audit(db, actor=actor.username, actor_role=actor.role, action="audit_exported",
          detail={"count": exported, "limit": limit, "since": since})
    db.commit()

    filename = f"audit-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
    return StreamingResponse(
        _audit_export_rows(db, head_id, since_dt, limit),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
