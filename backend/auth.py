"""Agentic PMO — Authentication: JWT, password hashing, dependency injection."""
import os
import datetime
import bcrypt
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── Config from environment ─────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-agentic-pmo-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
ALLOW_INSECURE_DEFAULTS = os.getenv("ALLOW_INSECURE_DEFAULTS", "") == "1"

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


_stored_hash = hash_password(ADMIN_PASSWORD)


# ── Auth scheme ─────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    """Create a JWT access token."""
    import jwt as pyjwt
    now = datetime.datetime.now(datetime.UTC)
    expiry = now + datetime.timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {"sub": username, "iat": now, "exp": expiry}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    """Verify a JWT and return the username. Returns None if invalid."""
    import jwt as pyjwt
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def login(username: str, password: str) -> Optional[str]:
    """Authenticate user and return a JWT token, or None on failure."""
    if username == ADMIN_USERNAME and verify_password(password, _stored_hash):
        return create_token(username)
    return None


# ── FastAPI dependency ──────────────────────────────────────────────────
def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """FastAPI dependency: require valid Bearer token. Returns username."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Include Authorization: Bearer <token>"
        )
    username = verify_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Login again.",
        )
    return username
