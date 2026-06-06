# Agentic PMO

**AI-agent-driven project management and orchestration platform.**

Agentic PMO is a standalone tool that automates planning, scheduling, resource allocation, and cross-functional coordination using autonomous AI agents. Built for manufacturing, industrial operations, green fuel processing, and any project-based workflow.

---

## What It Does

| Agent | Function |
|-------|----------|
| 🧠 **Plan Agent** | Takes a project brief → generates tasks, milestones, timeline, dependencies |
| 👁️ **Monitor Agent** | Scans task status → flags delays, risks, bottlenecks |
| 🔔 **Alert Agent** | Detects anomalies → recommends responses with severity assessment |

---

## Quick Start

### Option 1: Docker (recommended)

```bash
# 1. Clone or copy the project
cd agentic-pmo

# 2. Copy and configure environment
cp .env.example .env
# Edit .env — add your LLM_API_KEY

# 3. Run
docker compose up -d

# 4. Open in browser
open http://localhost:8000
```

### Option 2: Bare metal

```bash
# 1. Install Python 3.12+
cd agentic-pmo

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — add your LLM_API_KEY

# 4. Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 5. Open in browser
open http://localhost:8000
```

---

## Using Agentic PMO

1. **Create a project** — give it a name and a brief goal
2. **Run the Plan Agent** — generates a full task breakdown with milestones
3. **Move tasks** across the kanban board with drag and drop
4. **Run Monitor Agent** — checks project health and flags risks
5. **Review alerts** — the Alert Agent detects anomalies automatically
6. **Check the Agent Log** — see every AI action across all projects

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard` | Dashboard stats |
| GET/POST | `/api/projects` | List / Create projects |
| GET/PATCH/DELETE | `/api/projects/:id` | Project CRUD |
| GET/POST | `/api/projects/:id/tasks` | Task CRUD |
| PATCH/DELETE | `/api/projects/:id/tasks/:tid` | Single task |
| POST | `/api/projects/:id/agents/plan` | Run Plan Agent |
| POST | `/api/projects/:id/agents/monitor` | Run Monitor Agent |
| POST | `/api/projects/:id/agents/alert` | Run Alert Agent |
| GET | `/api/projects/:id/agents/actions` | Agent activity log |

---

## Configuration

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, `openrouter` |
| `LLM_API_KEY` | — | Your LLM API key |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `LLM_BASE_URL` | — | Custom API endpoint |
| `DATABASE_URL` | `sqlite:///./agentic_pmo.db` | Database connection |

**Without an LLM key**, the Plan Agent falls back to a template plan so you can still use the PMO as a task manager. Add a key when you want AI-powered features.

---

## Architecture

```
agentic-pmo/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── models.py            # SQLAlchemy ORM models
│   ├── database.py          # Database setup
│   ├── schemas.py           # Pydantic API schemas
│   ├── routers/             # API route handlers
│   │   ├── projects.py
│   │   ├── tasks.py
│   │   ├── agents.py
│   │   └── dashboard.py
│   ├── agents/              # AI agent implementations
│   │   ├── base.py          # Shared agent logic
│   │   ├── plan_agent.py    # Project planning
│   │   ├── monitor_agent.py # Progress monitoring
│   │   └── alert_agent.py   # Anomaly alerting
│   └── services/
│       └── llm_service.py   # LLM API abstraction
├── frontend/
│   ├── index.html           # SPA shell
│   ├── css/app.css           # Styles
│   └── js/                   # JavaScript views
│       ├── app.js, api.js, dashboard.js
│       ├── projects.js, kanban.js, agents.js
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Trademark

"Agentic PMO" is a trademark of AI Native Organisations. This software is proprietary — use under licence.

---

## Version

v0.1.0 — MVP
