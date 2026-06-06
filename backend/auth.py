"""Agentic PMO — Authentication: JWT, password hashing, dependency injection."""
import os
import hashlib
import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── Config ──────────────────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-agentic-pmo-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# ── Password hashing (simple SHA-256 — bcrypt adds unnecessary weight for MVP) ─
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


_stored_hash = hash_password(ADMIN_PASSWORD)


# ── Auth scheme ─────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    """Create a JWT access token."""
    import jwt as pyjwt
    expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": username,
        "iat": datetime.datetime.now(datetime.UTC),
        "exp": expiry,
    }
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
