"""Agentic PMO — main FastAPI app entry point."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.database import init_db
from backend.routers import projects, tasks, agents, dashboard

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

# API routers
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(dashboard.router)

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
    init_db()
