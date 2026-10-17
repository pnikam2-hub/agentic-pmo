"""Auth router — login endpoint."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from backend.auth import login, require_auth
from backend.rate_limit import limiter, LOGIN_RATE_LIMIT

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
def login_endpoint(request: Request, body: LoginRequest):
    token = login(body.username, body.password)
    if token is None:
        raise HTTPException(401, "Invalid username or password")
    return LoginResponse(token=token)


@router.get("/verify")
def verify_token(auth_user: str = Depends(require_auth)):
    """Check if the current token is valid. Returns the username."""
    return {"user": auth_user, "ok": True}
