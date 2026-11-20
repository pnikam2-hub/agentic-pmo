"""Auth router — login, token verification, own-account endpoints."""
import datetime
from hashlib import sha256
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.audit import audit
from backend.auth import (
    JWT_EXPIRY_HOURS, authenticate, client_ip, create_token, current_user,
    hash_password, require_auth, validate_password, verify_password,
)
from backend.database import get_db
from backend.models import User
from backend.rate_limit import limiter, LOGIN_RATE_LIMIT

router = APIRouter(prefix="/api/auth", tags=["auth"])

# What each role may do, mirroring the capability matrix in the SSO/RBAC plan.
# A flat list for the frontend to render with — the server enforces roles at
# the router boundary, this map never decides anything.
PERMISSIONS = {
    "viewer": [
        "read",
    ],
    "contributor": [
        "read",
        "update_tasks",
    ],
    "pmo_lead": [
        "read",
        "update_tasks",
        "manage_projects",
        "run_agents",
        "manage_plane",
        "apply_packs",
    ],
    "admin": [
        "read",
        "update_tasks",
        "manage_projects",
        "run_agents",
        "manage_plane",
        "apply_packs",
        "manage_users",
    ],
}


class LoginRequest(BaseModel):
    identifier: Optional[str] = None   # username or email; wins over username
    username: Optional[str] = None     # accepted for compatibility
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    role: str
    display_name: str
    expires_at: datetime.datetime


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
def login_endpoint(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    identifier = body.identifier or body.username
    if not identifier:
        raise HTTPException(422, "Provide 'identifier' (username or email) or 'username'")
    user = authenticate(identifier, body.password, db)
    if user is None:
        # Never record the raw typed identifier: a password pasted into the
        # username box must not end up plaintext in the audit trail. A salted
        # digest still lets a defender correlate repeated attempts, and the
        # length survives, without storing a possible secret.
        audit(db, actor="anonymous", action="login_failed",
              detail={
                  "identifier_sha256": sha256(identifier.lower().encode("utf-8")).hexdigest()[:16],
                  "identifier_len": len(identifier),
              },
              ip=client_ip(request))
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    audit(db, actor=user.username, actor_role=user.role, action="login_success",
          detail={"identifier": identifier}, ip=client_ip(request))
    db.commit()
    return LoginResponse(
        token=create_token(user),
        role=user.role,
        display_name=user.display_name,
        expires_at=datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    )


@router.get("/verify")
def verify_token(auth_user: str = Depends(require_auth)):
    """Check if the current token is valid. Returns the username."""
    return {"user": auth_user, "ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    """The current user and a permissions list derived from their role."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "source": user.source,
        "permissions": PERMISSIONS[user.role],
    }


@router.post("/password")
def change_password(
    body: PasswordChangeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Change own password. Requires the current one; bumps token_version so
    every live token — including this one — dies with the old password."""
    if not user.password_hash or not verify_password(body.old_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    try:
        validate_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    # Neither password may appear in the audit detail.
    audit(db, actor=user.username, actor_role=user.role, action="password_changed",
          target_type="user", target_id=user.id)
    db.commit()
    return {"ok": True}
