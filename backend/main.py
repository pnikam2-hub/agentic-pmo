"""Agentic PMO — main FastAPI app entry point."""
import os
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.database import init_db, SessionLocal
from backend.audit_chain import append_anchor
from backend.routers import projects, tasks, agents, dashboard, auth, alerts, templates, packs, plane, plane_webhook, admin
from backend.auth import any_role, bootstrap_admin, check_auth_config, enforce_auth_config
from backend.integrations import oidc
from backend.rate_limit import limiter

# Bumped whenever the API surface changes: the health endpoint is how a deploy is proved to have landed.
APP_VERSION = "0.2.0"
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def _check_env():
    """Warn at startup if critical config is missing."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("⚠️  No .env file found. Copy .env.example to .env and configure LLM_API_KEY.")
        print("   The app will work as a task manager without AI agents.")

    if not os.getenv("LLM_API_KEY", ""):
        print("⚠️  LLM_API_KEY is not set. AI agents will use fallback templates.")
        print("   Set LLM_API_KEY in .env for full AI-powered planning & monitoring.")

    for warn in check_auth_config():
        print(f"⚠️  {warn}")


def enforce_sso_config():
    """Fail closed: SSO-only is only possible when SSO is actually configured.

    LOCAL_LOGIN_ENABLED=0 closes the password front door, so the deployment
    must not start unless the OIDC flow that replaces it is fully configured —
    otherwise nobody, including the owner, can sign in and recovery is a
    restart. Mirrors enforce_auth_config()'s fail-closed stance for insecure
    defaults.
    """
    if not oidc.LOCAL_LOGIN_ENABLED and not oidc.configured():
        raise RuntimeError(
            "LOCAL_LOGIN_ENABLED=0 disables password sign-in, but single sign-on "
            "is not configured (OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_REDIRECT_URI "
            "and OIDC_CLIENT_SECRET must all be set). A deployment that cannot "
            "sign anyone in must not start."
        )

app = FastAPI(
    title="Agentic PMO",
    version=APP_VERSION,
    description="AI-agent-driven project management and orchestration platform.",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (slowapi) — handler + shared limiter instance
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# API routers — public
app.include_router(auth.router)

# API routers — protected. The router-level gate is the read boundary (any of
# the four roles, per plan §A5); write routes carry their own stricter guard,
# because every router here mixes reads with writes.
app.include_router(projects.router, dependencies=[Depends(any_role)])
app.include_router(tasks.router, dependencies=[Depends(any_role)])
app.include_router(agents.router, dependencies=[Depends(any_role)])
app.include_router(dashboard.router, dependencies=[Depends(any_role)])
app.include_router(alerts.router, dependencies=[Depends(any_role)])
app.include_router(templates.router, dependencies=[Depends(any_role)])
app.include_router(packs.router, dependencies=[Depends(any_role)])
app.include_router(plane.router, dependencies=[Depends(any_role)])
# Plane's webhook receiver authenticates with an HMAC signature, not a JWT — no auth dependency.
app.include_router(plane_webhook.router)

# Admin surface carries its own require_role("admin") gate on the router.
app.include_router(admin.router)

# Health check
@app.get("/api/health")
def health():
    """Liveness plus what the scheduler is actually holding — a job that never registered is invisible
    otherwise, and this is the cheapest place to make it visible."""
    from backend.scheduler import scheduler
    jobs = []
    if getattr(scheduler, "running", False):
        jobs = [
            {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in scheduler.get_jobs()
        ]
    return {"status": "ok", "version": APP_VERSION, "scheduler_running": bool(jobs), "jobs": jobs}


# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.on_event("startup")
async def on_startup():
    # async on purpose: AsyncIOScheduler.start() calls asyncio.get_running_loop(), which fails when
    # the hook runs in Starlette's threadpool. A sync hook would start the app but not the scheduler.
    _check_env()
    enforce_auth_config()  # fail closed on default admin password / JWT secret
    enforce_sso_config()   # fail closed if SSO-only is on without a working SSO config
    init_db()
    # After init_db: the users table must exist before anything can be put in it.
    # The .env admin is only ever created against an empty table, so a restart
    # neither duplicates nor overwrites it. The anchor is written in the same
    # session, before any new rows, so each process start records the chain head
    # it inherited — the one thing a later suffix deletion would otherwise erase.
    db = SessionLocal()
    try:
        append_anchor(db)
        bootstrap_admin(db)
    finally:
        db.close()
    from backend.scheduler import start_scheduler
    start_scheduler()
