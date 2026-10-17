"""Agentic PMO — main FastAPI app entry point."""
import os
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.database import init_db
from backend.routers import projects, tasks, agents, dashboard, auth, alerts, templates
from backend.auth import require_auth, check_auth_config, enforce_auth_config
from backend.rate_limit import limiter
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

app = FastAPI(
    title="Agentic PMO",
    version="0.1.0",
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

# API routers — protected (require JWT)
app.include_router(projects.router, dependencies=[Depends(require_auth)])
app.include_router(tasks.router, dependencies=[Depends(require_auth)])
app.include_router(agents.router, dependencies=[Depends(require_auth)])
app.include_router(dashboard.router, dependencies=[Depends(require_auth)])
app.include_router(alerts.router, dependencies=[Depends(require_auth)])
app.include_router(templates.router, dependencies=[Depends(require_auth)])

# Health check
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.on_event("startup")
def on_startup():
    _check_env()
    enforce_auth_config()  # fail closed on default admin password / JWT secret
    init_db()
    from backend.scheduler import start_scheduler
    start_scheduler()
