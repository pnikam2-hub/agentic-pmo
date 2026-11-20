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

## Roles and permissions

Four cumulative roles. Every rule below is enforced by the server on every request; the interface only
hides what a role cannot use.

| Capability | viewer | contributor | pmo_lead | admin |
|---|---|---|---|---|
| Read projects, tasks, dashboard, packs, templates, Plane status | yes | yes | yes | yes |
| Move a task between statuses, log actual hours | no | yes | yes | yes |
| Create/edit projects and tasks, run agents, apply templates and packs, link and sync Plane | no | no | yes | yes |
| Delete a project | no | no | no | yes |
| Manage users and roles, read the audit trail | no | no | no | yes |

Sign in with a username or an email. A password change, a role change or a deactivation invalidates that
user's outstanding tokens immediately. Every refusal (401 or 403) is recorded in the audit log, and the
audit log never stores a password, a hash or a token.


### Single sign-on (OIDC)

Set `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` and `OIDC_REDIRECT_URI` and the app accepts
sign-ins from any standard OIDC provider — Entra ID, Google Workspace, Okta — with no code change. Users are
provisioned on first login and their role comes from `OIDC_ROLE_MAP`; an account that already exists with
that verified email is linked and **keeps its existing role**, so SSO never silently promotes or demotes a
local user. Password sign-in stays available by default: an identity-provider outage must not lock you out.
Set `LOCAL_LOGIN_ENABLED=0` for SSO-only — the app refuses to start unless SSO is fully configured, because a
deployment that cannot sign anyone in is worse than one with two front doors.

---

## Security

The full access-control matrix — who may do what, and where each rule is enforced in code — is in
[docs/rbac-matrix.md](docs/rbac-matrix.md). The SSO/RBAC design and build are in
[docs/sso-rbac-phaseA-report.md](docs/sso-rbac-phaseA-report.md) and
[docs/sso-rbac-phaseB-report.md](docs/sso-rbac-phaseB-report.md).

| Measure | Enforced where |
|---|---|
| Four roles on every route | A router-level guard plus a per-route guard, all resolving through one `current_user` dependency; the role is re-read from the database on every request, never trusted from the JWT claim |
| Hash-chained audit with an anchor | Every security event writes a row; each row is hash-chained to its predecessor and an optional external anchor records the head, so an edit, insertion or suffix deletion is detectable via `GET /api/admin/audit/verify` |
| Per-identifier login lockout | Counted on the audit trail; `LOGIN_FAILURE_LIMIT` failures for one identifier within a window return 429 with `Retry-After` |
| Password policy | 12-character floor, 72-byte ceiling, and a zxcvbn strength score ≥ 3, with zxcvbn's own words as the rejection message |
| Response headers | One middleware sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store` on `/api/`, and HSTS when HTTPS is in play |
| SSO with local fallback | OIDC sign-in verifies the id token against the provider JWKS; password login stays on by default so an identity-provider outage cannot lock the owner out (`LOCAL_LOGIN_ENABLED=0` for SSO-only) |
| Deliberate exclusions | Per-project ACLs, SCIM provisioning, our own MFA, and SAML are out of scope for v1 — each is listed with its consequence in `docs/rbac-matrix.md` §6 |

No password, hash or token is ever stored in the audit trail, so the CSV export
(`GET /api/admin/audit/export.csv`) is safe to hand to an auditor.

---

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Sign in with `identifier` (username or email) and `password` |
| GET | `/api/auth/me` | Current user, role and permissions |
| GET | `/api/auth/verify` | Token check |
| POST | `/api/auth/password` | Change your own password (bumps the token version) |
| GET | `/api/auth/sso/enabled` | Whether SSO is configured (503 when it is not) |
| GET | `/api/auth/sso/start` | Begin OIDC sign-in — redirects to the identity provider |
| GET | `/api/auth/sso/callback` | Provider callback; verifies the id token and issues a handoff |
| POST | `/api/auth/sso/exchange` | Exchange the single-use handoff for a session token |

### Administration (admin role only)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/admin/users` | List / create users |
| PATCH/DELETE | `/api/admin/users/:id` | Change role or status / deactivate |
| POST | `/api/admin/users/:id/password` | Reset a password |
| GET | `/api/admin/audit` | Audit trail, newest first (`?limit=&actor=&action=`) |
| GET | `/api/admin/audit/verify` | Recompute the hash chain and compare the head against the anchor |
| GET | `/api/admin/audit/export.csv` | Export the audit trail as CSV, newest first (`?limit=&since=`) |

### Projects, tasks and agents

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

## Integrations

### Plane (work surface)

Plane is the human-facing task board; the PMO keeps the plan, the domain knowledge and the judgement.
A domain pack WBS is pushed into Plane as modules and work items with typed dependency relations
(`blocked_by` / `blocking`), and Plane stays the only place a work item is edited after that.

- Instance: https://plane.agenticpmo.tech (self-hosted, v1.5.0, AGPL-3.0, unmodified)
- API: `/api/v1/workspaces/{slug}/…`, `X-API-Key` auth, cursor pagination, 60 requests/minute
- Boundary: Plane owns execution state; the PMO never writes to a linked task again
- All four phases **live**: pull (`/sync`), push (`/push`, create-only, dry run by default), inbound HMAC
  webhooks (`/webhook`) plus a nightly reconcile, and typed dependencies feeding the Monitor agent

Full contract, field mapping, backup/restore and runbook: [docs/plane-integration.md](docs/plane-integration.md).

---

## Deployment Options

### Option A: Docker Compose (recommended — persistence + restart)

```bash
# Build and run
docker compose up -d

# Check logs
docker compose logs -f

# Stop
docker compose down
```

The SQLite database persists in `./data/agentic_pmo.db` on the host.
No database server needed.

### Option B: Docker (standalone)

```bash
docker build -t agentic-pmo .
docker run -d \
  --name agentic-pmo \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e DATABASE_URL=sqlite:///./data/agentic_pmo.db \
  -e LLM_API_KEY=sk-y...n \
  agentic-pmo
```

### Option C: Bare metal (dev/test)

```bash
# Python 3.12+ required
cd agentic-pmo
pip install -r backend/requirements.txt
cp .env.example .env
# Edit .env — add LLM_API_KEY
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option D: Systemd service (Linux production)

```ini
[Unit]
Description=Agentic PMO
After=network.target

[Service]
WorkingDirectory=/opt/agentic-pmo
ExecStart=/usr/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
User=agentic-pmo

[Install]
WantedBy=multi-user.target
```

---

## Environment Variables

See `.env.example` for all options. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `openai` | `openai`, `anthropic`, `openrouter` |
| `LLM_API_KEY` | **Yes for AI agents** | — | Your LLM API key |
| `LLM_MODEL` | No | `gpt-4o` | Model name |
| `LLM_BASE_URL` | No | — | Custom API endpoint |
| `DATABASE_URL` | No | `sqlite:///./agentic_pmo.db` | Database connection |
| `ADMIN_USERNAME` | No | `admin` | Bootstrap admin, created on first start against an empty users table |
| `ADMIN_PASSWORD` | **Yes** | — | Bootstrap admin password; startup refuses the default |
| `JWT_SECRET` | **Yes** | — | 32+ byte secret for session tokens (`openssl rand -hex 32`) |
| `JWT_EXPIRY_HOURS` | No | `8` | Session lifetime |
| `PLANE_WEBHOOK_SECRET` | No | — | HMAC secret for inbound Plane deliveries |
| `OIDC_ISSUER` | No | — | SSO provider; SSO is off unless this and the next three are set |
| `OIDC_CLIENT_ID` | No | — | Client registered at the provider |
| `OIDC_CLIENT_SECRET` | No | — | Client secret for the token exchange |
| `OIDC_REDIRECT_URI` | No | — | Must match the provider registration |
| `OIDC_ROLE_MAP` | No | `{}` | JSON group→role map, e.g. `{"pmo-admins":"admin","*":"viewer"}` |
| `LOCAL_LOGIN_ENABLED` | No | `true` | `0` for SSO-only (the app then refuses to start without a full OIDC config) |

**Without an LLM key**, the Plan Agent falls back to a template plan so
you can still use the PMO as a task manager. Add a key when you want
AI-powered features.

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
