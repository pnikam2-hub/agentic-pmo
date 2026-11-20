"""Auth router — login, token verification, own-account, SSO endpoints."""
import datetime
import hmac
from hashlib import sha256
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import audit
from backend.auth import (
    JWT_EXPIRY_HOURS, authenticate, client_ip, create_token, current_user,
    hash_password, other_active_admins, require_auth, validate_password,
    verify_password,
)
from backend.database import get_db
from backend.integrations import oidc
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
    # LOCAL_LOGIN_ENABLED=0 turns off password sign-in entirely, without
    # touching SSO. Default stays on so an IdP outage cannot lock the owner out.
    if not oidc.LOCAL_LOGIN_ENABLED:
        raise HTTPException(403, "Password sign-in is disabled for this deployment")
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


# ── SSO (Phase B) ───────────────────────────────────────────────────────
SSO_NOT_CONFIGURED = "Single sign-on is not configured"


def _sso_fail(db: Session, request: Request, reason: str, extra: dict = None):
    """One audit row per failed SSO attempt, with a short reason code only.

    The reason is a coarse category — never which check failed or any claim —
    so the trail records that a sign-in was refused without teaching an
    attacker how to refine their attempt. ``extra`` carries non-secret context
    (for example an OAuth error code) that is safe to record.
    """
    detail = {"issuer": oidc.OIDC_ISSUER, "reason": reason}
    if extra:
        detail.update(extra)
    audit(db, actor="anonymous", action="sso_login_failed", detail=detail,
          ip=client_ip(request))
    db.commit()


def _unique_username(db: Session, email: str, sub: str) -> str:
    """Derive a unique username for a provisioned oidc user.

    The email local-part is the human-friendly default; when it collides with
    an existing username a numeric suffix keeps the unique index satisfied
    without ever surfacing a raw IdP subject as a display name.
    """
    base = email.split("@")[0].lower() if "@" in email else ""
    if not base:
        base = sub
    candidate = base
    suffix = 1
    while db.query(User).filter(User.username == candidate).first():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


@router.get("/sso/enabled")
def sso_enabled():
    """Report whether SSO is configured, and to which issuer. Never the secret."""
    if not oidc.configured():
        raise HTTPException(503, SSO_NOT_CONFIGURED)
    return {"enabled": True, "issuer": oidc.OIDC_ISSUER or None}


@router.get("/sso/start")
def sso_start(request: Request):
    """Redirect to the IdP, stashing state+nonce+verifier in a signed cookie.

    The cookie is HttpOnly so the SPA cannot read the verifier, SameSite=Lax
    so it is sent only on the top-level callback navigation, Secure on https,
    and scoped to /api/auth/sso so it never rides along on unrelated requests.
    """
    if not oidc.configured():
        raise HTTPException(503, SSO_NOT_CONFIGURED)
    try:
        authorize_url, session_state = oidc.start(oidc.OIDC_REDIRECT_URI)
    except oidc.OIDCError:
        # Discovery failed or the document was malformed — an upstream problem,
        # not a client mistake, so it is a 502 rather than a 400 or a 500.
        raise HTTPException(502, "The identity provider is not reachable right now")
    response = RedirectResponse(authorize_url, status_code=302)
    response.set_cookie(
        key=oidc.SSO_COOKIE_NAME,
        value=oidc.encode_session_cookie(session_state),
        max_age=oidc.SSO_COOKIE_TTL,
        path="/api/auth/sso",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/sso/callback")
def sso_callback(
    request: Request,
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """Complete the SSO flow: verify, map the role, resolve or create the user.

    The redirect lands on /#sso=<token> because the fragment is never sent to a
    server — round B2 reads and clears it in the browser, so our own token is
    handed to the SPA without ever being echoed into a URL that could be
    logged.
    """
    if not oidc.configured():
        raise HTTPException(503, SSO_NOT_CONFIGURED)

    if error:
        # The provider refused the sign-in (cancelled, consent denied, etc.) and
        # sent us back with an OAuth error code instead of an authorisation
        # code. The code is a coarse, public category — not a secret — so it is
        # safe to record in the audit detail.
        _sso_fail(db, request, "provider_error", extra={"error": error})
        raise HTTPException(400, "Sign-in was cancelled at the identity provider")

    cookie = request.cookies.get(oidc.SSO_COOKIE_NAME)
    if not cookie:
        _sso_fail(db, request, "missing_cookie")
        raise HTTPException(400, "Sign-in session is missing — start sign-in again")
    session_state = oidc.decode_session_cookie(cookie)
    if session_state is None:
        _sso_fail(db, request, "invalid_cookie")
        raise HTTPException(400, "Sign-in session has expired or is invalid — start sign-in again")

    cookie_state = session_state.get("state")
    if not isinstance(cookie_state, str) or not isinstance(state, str) \
            or not hmac.compare_digest(cookie_state, state):
        _sso_fail(db, request, "state_mismatch")
        raise HTTPException(400, "Sign-in session does not match this request — start sign-in again")
    nonce = session_state.get("nonce")
    verifier = session_state.get("verifier")
    if not isinstance(nonce, str) or not isinstance(verifier, str):
        _sso_fail(db, request, "invalid_cookie")
        raise HTTPException(400, "Sign-in session is malformed — start sign-in again")
    if not code:
        _sso_fail(db, request, "missing_code")
        raise HTTPException(400, "Sign-in callback is missing the authorisation code")

    try:
        id_token, _access_token = oidc.exchange(code, verifier, oidc.OIDC_REDIRECT_URI)
    except oidc.OIDCError:
        _sso_fail(db, request, "token_exchange")
        raise HTTPException(401, "Single sign-on failed at the token exchange")
    try:
        claims = oidc.verify_id_token(id_token, nonce)
    except oidc.OIDCError:
        _sso_fail(db, request, "id_token")
        raise HTTPException(401, "Single sign-on failed: the identity token did not verify")
    try:
        sub, email, name, issuer = oidc.identity_from_claims(claims)
    except oidc.OIDCError as exc:
        _sso_fail(db, request, "identity")
        raise HTTPException(403, str(exc))
    role, matched, degraded = oidc.role_from_claims(claims)

    external_id = f"{issuer}#{sub}"
    user = db.query(User).filter(User.external_id == external_id).first()
    provisioned = False
    linked = False
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            # An account already holds this verified email. Linking proves
            # identity, not authority: keep the existing role and source, so a
            # local account (including the bootstrap admin, whose email may
            # match an IdP identity with no role groups) is never silently
            # promoted or demoted by its first SSO login. The divergence is
            # recorded below so it can be resolved deliberately in Users & Audit.
            user.external_id = external_id
            linked = True
        elif not oidc.OIDC_AUTO_PROVISION:
            _sso_fail(db, request, "not_provisioned")
            raise HTTPException(
                403,
                "Single sign-on succeeded but no account exists for your email "
                "and automatic provisioning is disabled",
            )
        else:
            user = User(
                username=_unique_username(db, email, sub),
                email=email,
                display_name=name or email.split("@")[0],
                password_hash=None,
                role=role,
                source="oidc",
                external_id=external_id,
            )
            db.add(user)
            provisioned = True
            try:
                db.flush()   # assign the id before the audit row references it
            except IntegrityError:
                # Two first logins for the same person, or a username a racing
                # request just claimed, can both pass the existence checks above
                # before either commits; the unique index then rejects the loser.
                # Roll back and adopt whichever row won rather than 500ing.
                db.rollback()
                user = (
                    db.query(User).filter(User.external_id == external_id).first()
                    or db.query(User).filter(User.email == email).first()
                )
                if user is None:
                    _sso_fail(db, request, "provision_conflict")
                    raise HTTPException(
                        409, "Could not create your account — please try again"
                    )
                provisioned = False
                if user.source != "oidc":
                    # The winning row is a local account that shares the email;
                    # link it (keeping its role) rather than applying the map.
                    user.external_id = external_id
                    linked = True

    # A deactivated account must not complete SSO: minting a token for it would
    # hand the SPA a JWT that every later request rejects with 401 anyway.
    # Refuse here — before any mutation is committed — so the failed row is the
    # only trace and the account keeps its pre-login state.
    if not user.is_active:
        _sso_fail(db, request, "inactive")
        raise HTTPException(
            403, "Your account has been deactivated. Contact an administrator."
        )

    # Role sync applies only to oidc accounts, which have no local authority to
    # preserve. A linked local account keeps its role (link proves identity, not
    # authority), so it is skipped entirely. A demotion that would remove the
    # last active admin is refused — the same invariant the admin router
    # enforces, via the same helper.
    role_changed = False
    if not linked:
        role_changed = user.role != role
        if role_changed and user.role == "admin" and user.is_active == 1 \
                and other_active_admins(db, user) == 0:
            _sso_fail(db, request, "last_admin")
            raise HTTPException(
                403,
                "Refusing this sign-in: it would demote the last active admin "
                "and leave this deployment with no administrator",
            )
        if role_changed:
            # A role change must kill every live token (Phase A rule): bump
            # token_version so tokens minted under the old role stop working.
            user.role = role
            user.token_version += 1
    user.last_login_at = datetime.datetime.utcnow()
    db.commit()

    detail = {"issuer": issuer, "matched": matched}
    if degraded:
        # The group map produced a value that is not a known role; record that
        # we substituted the default, never the token that carried the group.
        detail["role_fallback"] = degraded
    if provisioned:
        action = "sso_user_provisioned"
        detail["role"] = role
    elif linked:
        action = "sso_user_linked"
        # Linking proves identity, not authority: record the role we kept and
        # the role the group map would have granted, so a divergence is visible
        # in Users & Audit and can be reconciled deliberately rather than
        # silently applied.
        detail.update({
            "linked": True,
            "role_kept": user.role,
            "mapped_role": role,
        })
    else:
        action = "sso_login"
        detail["role"] = role
    audit(db, actor=user.username, actor_role=user.role, action=action,
          target_type="user", target_id=user.id, detail=detail, ip=client_ip(request))
    if role_changed:
        # A role change is its own queryable outcome, separate from the login.
        audit(db, actor=user.username, actor_role=user.role, action="sso_role_updated",
              target_type="user", target_id=user.id,
              detail={"issuer": issuer, "role": role, "matched": matched},
              ip=client_ip(request))
    db.commit()

    token = create_token(user)
    return RedirectResponse(f"/#sso={token}", status_code=302)
