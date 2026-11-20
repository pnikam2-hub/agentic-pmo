"""Agentic PMO — Authentication: JWT, password hashing, dependency injection."""
import os
import datetime
import bcrypt
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User

# ── Config from environment ─────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-agentic-pmo-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
ALLOW_INSECURE_DEFAULTS = os.getenv("ALLOW_INSECURE_DEFAULTS", "") == "1"

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
        return None
    if not user.password_hash or not verify_password(password, user.password_hash):
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
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except Exception:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    if payload.get("ver") != user.token_version:
        return None
    return user


# ── Auth scheme and dependencies ────────────────────────────────────────
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

    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires role {', '.join(allowed)}, "
                    f"but your role is '{user.role}'."
                ),
            )
        return user

    return guard
