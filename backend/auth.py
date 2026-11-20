"""Agentic PMO — Authentication: JWT, password hashing, dependency injection."""
import os
import datetime
import ipaddress
from hashlib import sha256
import bcrypt
import zxcvbn
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.audit import audit
from backend.database import get_db
from backend.models import AuditLog, User

# ── Config from environment ─────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-agentic-pmo-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
ALLOW_INSECURE_DEFAULTS = os.getenv("ALLOW_INSECURE_DEFAULTS", "") == "1"

# Per-identifier login throttling. Counted on the audit trail (login_failed
# rows), so the lock survives a restart and needs no shared store. The window
# is deliberately short: a failure count keyed on the identifier digest means
# an attacker who knows a username can lock that account out by feeding it
# bad passwords, which is why the per-IP slowapi limit stays in place too —
# the two limits together make a distributed lockout expensive while still
# stopping a targeted brute force.
LOGIN_FAILURE_LIMIT = int(os.getenv("LOGIN_FAILURE_LIMIT", "5"))
LOGIN_FAILURE_WINDOW_MINUTES = int(os.getenv("LOGIN_FAILURE_WINDOW_MINUTES", "15"))

# Minimum zxcvbn score a password must reach. 3 means "safely unguessable:
# moderate protection from online throttled attacks" — a passphrase, not a
# tweaked dictionary word. Enforced in addition to the 12-character floor and
# bcrypt's 72-byte ceiling, never instead of them.
ZXCVBN_MIN_SCORE = 3

# Roles are cumulative in tuple order: viewer < contributor < pmo_lead < admin.
# Compare via membership in ROLES slices, never via string comparison.
ROLES = ("viewer", "contributor", "pmo_lead", "admin")


def validate_role(value: str) -> str:
    """Accept a known role, reject anything else. An unknown role must fail on
    write, not surface later as a user no guard recognises."""
    if value not in ROLES:
        raise ValueError(f"Unknown role '{value}'. Valid roles: {', '.join(ROLES)}")
    return value


# ── Security validation ─────────────────────────────────────────────────
def check_auth_config():
    """Warn about insecure defaults. Returns list of warnings."""
    warnings = []
    if not ADMIN_PASSWORD or ADMIN_PASSWORD == "admin":
        warnings.append(
            "DEFAULT PASSWORD: ADMIN_PASSWORD is unset, empty, or still 'admin'. "
            "Set a strong password in .env before deploying to production."
        )
    if not JWT_SECRET or JWT_SECRET == "change-me-in-production-agentic-pmo-2026":
        warnings.append(
            "DEFAULT JWT SECRET: JWT_SECRET is unset, empty, or the known public "
            "default. Anyone can forge admin tokens. Generate one with: "
            "openssl rand -hex 32"
        )
    return warnings


def enforce_auth_config():
    """Fail closed: refuse to run with known-insecure defaults.

    Called at app startup. Tests and local demos may opt out with
    ALLOW_INSECURE_DEFAULTS=1; production must set real credentials.
    """
    if ALLOW_INSECURE_DEFAULTS:
        return
    problems = check_auth_config()
    if problems:
        raise RuntimeError(
            "Refusing to start with insecure auth defaults: "
            + " | ".join(problems)
            + ". Set ADMIN_PASSWORD and JWT_SECRET in .env, or set "
            "ALLOW_INSECURE_DEFAULTS=1 only for local demos/tests."
        )


# ── Password hashing (bcrypt — salted, adaptive, constant-time verify) ──
def validate_password(value: str) -> None:
    """Shared password policy: a 12-character floor, bcrypt's 72-byte ceiling,
    and a zxcvbn strength floor (score >= ZXCVBN_MIN_SCORE).

    The strength check is *additional*, not a replacement: the length and byte
    checks stay so every entry point fails with the same clear 422, and zxcvbn
    catches the long-but-predictable passwords ("Password1!") that a length
    rule alone lets through. The rejection message is zxcvbn's own feedback so
    the user is told *why*, not just "too weak".
    """
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters")
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    result = zxcvbn.zxcvbn(value)
    if result.get("score", 0) < ZXCVBN_MIN_SCORE:
        raise ValueError(_zxcvbn_feedback(result))


def _zxcvbn_feedback(result: dict) -> str:
    """zxcvbn's own words for why a password is weak.

    The warning is the short, human sentence ("This is a top-10 common
    password"); the suggestions are the more specific fixes. Prefer the warning,
    fall back to the first suggestion, and only then to a bare score — the
    message is the point of having the policy. Never includes the password
    itself: zxcvbn's feedback text is fixed vocabulary, not the input.
    """
    feedback = result.get("feedback") or {}
    warning = (feedback.get("warning") or "").strip()
    suggestions = [s for s in (feedback.get("suggestions") or []) if s]
    if warning:
        return warning
    if suggestions:
        return suggestions[0]
    return f"Password is too weak (zxcvbn score {result.get('score', 0)} of 4)"


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")
    if len(pw) > 72:
        raise ValueError("Password too long for bcrypt (max 72 bytes)")
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # Malformed hash or password over bcrypt's 72-byte limit
        return False


# A bcrypt hash of a fixed constant, computed once at import. authenticate()
# verifies every failed login against it so "no such account", "inactive
# account" and "wrong password" all pay the same bcrypt cost — the 401 text is
# already identical, and this closes the timing channel that would otherwise
# let a caller enumerate identifiers by latency.
_DUMMY_PASSWORD = "dummy-timing-normalisation-password-not-a-secret"
_DUMMY_HASH = hash_password(_DUMMY_PASSWORD)


def identifier_digest(identifier: str) -> str:
    """A short digest of the normalised identifier, for the audit trail and the
    login-failure counter.

    The full sha256 is truncated to 16 hex characters — enough to correlate
    repeated attempts against one account without storing the identifier (or a
    password pasted into the username box) in plaintext. Matching the login
    endpoint's login_failed row exactly, so the throttle counter and the audit
    trail can never disagree on what an identifier is.
    """
    return sha256(identifier.lower().encode("utf-8")).hexdigest()[:16]


def login_failures_in_window(db: Session, digest: str) -> list:
    """The ``at`` timestamps of recent login_failed rows for one digest, oldest
    first, bounded by the configured window.

    Querying strategy, chosen deliberately: ``AuditLog.at`` is *not* indexed,
    and adding an index on ``(action, at)`` would be a new index on a live
    table that ``create_all()`` never creates for an existing database. So
    instead of relying on an index that may not exist, this filters by
    ``action == "login_failed"`` — which *is* indexed — and applies the window
    in SQL to pull only recent rows, then matches the digest in Python (the
    digest lives inside the JSON ``detail``, which SQLite cannot index on
    meaningfully anyway). The scan is therefore bounded by the action index
    rather than a full table scan.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(
        minutes=LOGIN_FAILURE_WINDOW_MINUTES
    )
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "login_failed", AuditLog.at >= cutoff)
        .order_by(AuditLog.at.asc())
        .all()
    )
    return [
        row.at
        for row in rows
        if row.at is not None and (row.detail or {}).get("identifier_sha256") == digest
    ]


def login_throttled(db: Session, digest: str):
    """Whether the identifier is currently locked out, and for how long.

    Returns ``(locked, retry_after_seconds)``. Locked means there have been at
    least ``LOGIN_FAILURE_LIMIT`` failures for this digest within the window.
    ``retry_after`` is the seconds until the lock releases — the moment the
    ``LIMIT``-th most recent failure ages out of the window — so the caller can
    hand it straight to a ``Retry-After`` header. A successful login clears the
    count by construction: only failures are counted and the window is
    time-bounded, so nothing here needs an explicit reset.
    """
    failures = login_failures_in_window(db, digest)
    if len(failures) < LOGIN_FAILURE_LIMIT:
        return False, 0
    # The failure that, once it ages out, drops the count below the limit.
    release_failure_at = failures[len(failures) - LOGIN_FAILURE_LIMIT]
    window = datetime.timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)
    remaining = (release_failure_at + window) - datetime.datetime.utcnow()
    return True, max(1, int(remaining.total_seconds()) + 1)


# ── User lookup and bootstrap ───────────────────────────────────────────
def bootstrap_admin(db: Session) -> Optional[User]:
    """Create the .env admin as the first user, role admin, source local.

    Only ever runs against an empty users table, which is what makes it
    idempotent: it can never overwrite an existing user with the env password,
    so a stale .env cannot reclaim an account someone has since renamed or
    repurposed. Commits its own work — it is a standalone unit, not part of a
    request's transaction. Returns the created user, or None if any user
    already exists.
    """
    if db.query(User).count() > 0:
        return None
    admin = User(
        username=ADMIN_USERNAME.lower(),
        email=None,
        display_name=ADMIN_USERNAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        role="admin",
        source="local",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def other_active_admins(db: Session, user: User) -> int:
    """Count active admins other than ``user``.

    The single definition of "is this the last active admin", shared by the
    admin router and the SSO callback so the two paths can never drift apart on
    the invariant that a deployment always keeps at least one administrator.
    """
    return db.query(User).filter(
        User.role == "admin", User.is_active == 1, User.id != user.id
    ).count()


def _find_user(identifier: str, db: Session) -> Optional[User]:
    """Look up by lower-cased username first, then lower-cased email."""
    identifier = identifier.lower()
    return (
        db.query(User).filter(User.username == identifier).first()
        or db.query(User).filter(User.email == identifier).first()
    )


def authenticate(identifier: str, password: str, db: Session) -> Optional[User]:
    """Verify credentials against the users table; returns the user or None.

    Identifier may be a username or an email, matched lower-cased. Inactive
    users are refused without revealing whether the identifier exists.

    If the identifier matches nothing and the users table is empty, the env
    admin is bootstrapped and the lookup retried once. The test suite, embedded
    ASGI processes, and any CLI build the tables without running the startup
    hook, so without this the env admin would not exist there and every login
    would fail; bootstrapping is idempotent by construction (empty table only),
    so the env admin stays usable in any process without weakening the rule
    that the database, not .env, is authoritative once populated.
    """
    user = _find_user(identifier, db)
    if user is None and db.query(User).count() == 0:
        bootstrap_admin(db)
        user = _find_user(identifier, db)
    if user is None or not user.is_active:
        # Burn one bcrypt comparison even when there is nothing to compare
        # against, so the response time does not reveal whether the identifier
        # exists or is active (see _DUMMY_HASH).
        verify_password(password, _DUMMY_HASH)
        return None
    if not user.password_hash:
        # oidc users carry no local password; still pay the same comparison so
        # this path is not distinguishable from a wrong password.
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.datetime.utcnow()
    db.commit()
    return user


# ── Tokens ──────────────────────────────────────────────────────────────
def create_token(user: User) -> str:
    """Create a JWT for a user.

    The role and username travel in the token for display, but they are claims
    of convenience: verify_token re-checks everything against the database, so
    a stale token can never act with a role its user no longer holds.
    """
    import jwt as pyjwt
    now = datetime.datetime.now(datetime.UTC)
    expiry = now + datetime.timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(user.id),
        "usr": user.username,
        "role": user.role,
        "ver": user.token_version,
        "iss": "agentic-pmo",
        "iat": now,
        "exp": expiry,
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, db: Session) -> Optional[User]:
    """Decode a JWT and load its user, or return None.

    A token is only valid while its user is: missing, deactivated, or carrying
    a token_version other than the token's `ver` all invalidate it. That is
    what makes a password change or an admin deactivation kill live tokens.
    """
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                               issuer="agentic-pmo")
        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub.isdigit():
            return None
        user_id = int(sub)
    except Exception:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    if payload.get("ver") != user.token_version:
        return None
    return user


# ── Auth scheme and dependencies ────────────────────────────────────────
def client_ip(request: Request) -> Optional[str]:
    """Best-effort caller IP for audit rows.

    request.client.host is the direct peer. Behind the documented single
    reverse proxy that peer is the proxy itself, so honour X-Forwarded-For —
    but only when the direct peer is loopback or a private address, because any
    caller can set the header otherwise and would be able to forge the "from
    where" in the audit trail. The trusted-proxy assumption is: we are either
    reached directly, or through a proxy on the same trusted network, and the
    first hop of the header is the original client.
    """
    host = request.client.host if request.client else None
    forwarded = request.headers.get("X-Forwarded-For")
    if host and forwarded:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            addr = None
        if addr is not None and (addr.is_loopback or addr.is_private):
            return forwarded.split(",")[0].strip()
    return host


def is_https(request: Request) -> bool:
    """Is this request HTTPS, honouring a TLS-terminating reverse proxy?

    ``request.url.scheme`` is "http" behind the documented single reverse proxy
    (the proxy terminates TLS and forwards plaintext), so it cannot decide the
    cookie's Secure flag on its own. Trust ``X-Forwarded-Proto: https`` only
    when the direct peer is loopback or private — the same trusted-proxy rule
    ``client_ip`` applies — so a remote caller cannot set the header and trick
    us into marking a plaintext cookie Secure (which would both lie about the
    protection and drop the cookie for the legitimate proxy).
    """
    if request.url.scheme == "https":
        return True
    host = request.client.host if request.client else None
    proto = request.headers.get("X-Forwarded-Proto", "")
    if host and proto:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            addr = None
        if addr is not None and (addr.is_loopback or addr.is_private):
            return proto.split(",")[0].strip().lower() == "https"
    return False


security = HTTPBearer(auto_error=False)


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """The single point that turns an Authorization header into a User.

    Every guard and every handler resolves through this one dependency, so a
    test that overrides it (or a future swap of the token scheme) covers the
    whole app in one place. Do not inline user resolution anywhere else.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Include Authorization: Bearer <token>",
        )
    user = verify_token(credentials.credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Login again.",
        )
    return user


def require_auth(user: User = Depends(current_user)) -> str:
    """Require any authenticated user; returns the username.

    Kept as a str-returning dependency because the routers written before
    users had identities take it as their auth boundary; they gain role
    limits in a later round.
    """
    return user.username


def require_role(*roles: str):
    """Dependency factory: admit only the named roles, return the User.

    The guard resolves through current_user rather than decoding the token
    itself, so an override of current_user covers every guard too.
    """
    allowed = tuple(roles)

    def guard(
        request: Request,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.role not in allowed:
            # A 403 that leaves no trace is the first thing a security review
            # asks about — "who tried, and from where". Record the refusal
            # before raising, so the audit trail names the actor, the path and
            # the roles they lacked. Kept here, in one place, so no route can
            # forget to write it.
            audit(
                db,
                actor=user.username,
                actor_role=user.role,
                action="access_denied",
                detail={
                    "method": request.method,
                    "path": request.url.path,
                    "required_roles": list(allowed),
                },
                ip=client_ip(request),
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires role {', '.join(allowed)}, "
                    f"but your role is '{user.role}'."
                ),
            )
        return user

    return guard


# ── Shared guard instances ──────────────────────────────────────────────
# One instance per role boundary, defined here so every router imports the
# same callable. FastAPI caches a dependency per callable per request, so a
# shared guard means a router-level gate and a handler-level `actor`
# parameter resolve the same User instead of decoding the token twice — and
# a test that overrides current_user covers every router identically.
any_role = require_role("viewer", "contributor", "pmo_lead", "admin")
contributor_up = require_role("contributor", "pmo_lead", "admin")
pmo_lead_up = require_role("pmo_lead", "admin")
admin_only = require_role("admin")
