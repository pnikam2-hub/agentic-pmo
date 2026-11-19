# Plane integration — what exists, what it does, and how to run it

Status: infrastructure live; **all four phases shipped** 19 November 2026 — read-only pull,
PMO→Plane push, inbound webhooks with nightly reconcile, and the schedule-aware Monitor.
Audience: whoever operates Agentic PMO, and whoever extends the integration.

## 1. Why Plane, and where the boundary sits

Plane is an open-source project-management application (Django API + React front end) that gives a
team a work surface people actually use: work items, states, cycles, modules, comments, members,
activity history. It has no AI layer, no domain knowledge and no risk register.

Agentic PMO has the opposite profile: Plan / Monitor / Alert agents, seven domain packs
(92–165-task WBS, risk register, KPI targets, monitoring rules), a health score, and an agent audit
trail — but a thin UI and a data model that cannot express schedule logic.

So the division is:

| | Plane | Agentic PMO |
|---|---|---|
| Owns | the work item, its state, its owner, its history | judgement: plans, risk, health, alerts, domain context |
| Edits a task | yes, by humans, all day | **never**, once the task is pushed |
| Source of truth for | execution status and assignment | the plan that created the task, and the reasoning about it |

That boundary is the whole design. Two systems that both accept edits to the same field need a merge
policy, and a merge policy is where this kind of integration usually dies.

## 2. The instance as it stands

| | |
|---|---|
| URL | https://plane.agenticpmo.tech (TLS: Let's Encrypt, auto-renewed by Caddy) |
| Host | `187.127.191.104` / srv1804405 — Ubuntu 24.04, 2 vCPU, 7.9 GB RAM, 93 GB disk |
| Version | Plane **v1.5.0**, pinned via `APP_RELEASE` in `/opt/plane/.env` |
| Footprint | 12 containers + the pre-existing Uptime Kuma; ~1.2 GB RSS total |
| Licence | AGPL-3.0-only, per file |
| Edition | Community (`PLANE_COMMUNITY`); no licence key, no paid features |
| Admin | `ashwin@ainativeorganisations.com` (instance admin, member of workspace `ai-native`) |
| Public entry | host Caddy on :80/:443 → Plane's bundled proxy on `127.0.0.1:8080`. Postgres, Redis, RabbitMQ and MinIO are container-internal only |
| Signup | **closed** (`enable_signup: false`) — users are invited from inside the instance |
| Login | email + password, and magic link (both enabled); no SSO |
| Mail | Google Workspace SMTP (`smtp.gmail.com:587`) sending as `AI Native PMO <ashwin@ainativeorganisations.com>` |
| Integration in | `POST https://agenticpmo.tech/api/integrations/plane/webhook` — HMAC-verified, delivery-deduped |
| Reconcile | nightly at 02:30 UTC (in-process scheduler); `next_run` visible at `/api/health` |
| Backups | `.104` 02:15 UTC dump → `.153` 02:45 UTC pull, 30-day retention |

Workspace `ai-native` holds one pilot project, **EPC Project — AI Native PMO pilot**, which is the
`epc_project` domain pack rendered in Plane: 165 work items in 8 phase modules, with 162 typed
dependency sets imported from the pack's WBS.

## 3. How the two systems talk

Everything is HTTP. No code is shared, no database is shared, and Plane is never modified.

**REST API** — `/api/v1/workspaces/{slug}/…`

- Auth: `X-API-Key: plane_api_…` (a personal access token, `user_type=Bot`). One token per integrating
  system, held on `.153` at `/root/.config/plane/api_key` (mode 600).
- Cursor pagination: `per_page` max 100, `next_cursor` / `next_page_results` in the envelope.
- **Rate limit: 60 requests/minute per token.** A 165-item WBS push takes ~4 minutes at 1.05 s pacing.
  Any push must therefore be a background job with progress, never an inline request.
- Endpoints used: `projects/`, `work-items/` (read and create), `work-items/{id}/relations/`, `states/`,
  `modules/`, `modules/{id}/module-issues/`, `comments/`.
- There is no hours field on a work item; `estimated_hours`, discipline, deliverables and acceptance
  criteria go into `description_html` with the pack reference (`epc_project/T014`).

**Relations are the reason this integration is worth doing.** Plane stores `blocking`, `blocked_by`,
`duplicate`, `relates_to`, `start_before`, `start_after`, `finish_before`, `finish_after` — i.e. the
FS/SS/FF/SF taxonomy the PMO's `Task.dependencies` JSON list cannot express. Posting `blocked_by` from
the successor also creates the reciprocal `blocking` row, so the sync must never write both directions.

**Webhooks** — from Plane into the PMO, live since 19 Nov 2026

- `POST /api/integrations/plane/webhook` on `agenticpmo.tech`; mounted without the JWT dependency,
  because Plane has no user session — the signature is the authentication.
- **Plane signs a different byte string than it sends**: HMAC-SHA256 over `json.dumps(payload)` with
  default separators, while the body is serialised by httpx. A strict raw-body check fails, so the
  receiver tries five canonicalisations and records which matched (`plane_webhook_events.signature_scheme`).
- Deliveries carry `X-Plane-Delivery` → dedupe on it; Plane retries with backoff and fires one event
  per changed field, so a two-field edit arrives as two deliveries.
- **Return 2xx even when processing fails.** A 4xx is a permanent rejection and five non-2xx in a row
  silently disables the hook and emails its creator. Failures land in `plane_webhook_events` with
  `status=error` and are repaired by the nightly reconcile.
- No secret configured → `503`. Invalid signature → `401`, no row written. It fails closed.
- Rejected target URLs: `localhost`, `127.0.0.1`, private ranges (unless allowlisted via
  `WEBHOOK_ALLOWED_IPS` / `WEBHOOK_ALLOWED_HOSTS`).
- Webhooks are workspace-level only, and their CRUD is **not** in the key-authenticated v1 API. The
  hook here was created as a `Webhook` row on the Plane host (`issue`, `issue_comment`, `module`).

## 4. Field mapping (validated on the pilot board)

| Agentic PMO | Plane | Direction | Notes |
|---|---|---|---|
| Project | Project (+ `identifier`) | both | identifier is uppercase, ≤12 chars; the link is explicit, never inferred by name |
| Domain pack | — | — | survives as text in each work item's description and in the PMO's `project_packs` |
| Pack phase (`phases[].name`) | Module | pull only | phases are dicts `{id, name, weeks}`; a PMO task has no phase field, so **push does not create modules** |
| Task | Work item | both | `sequence_id` is Plane's per-project number; push creates only, never updates |
| `status` | State | both | pull: group → PMO status with `blocked`/`review` winning on state name. push: todo→Todo, in_progress→In Progress, done→Done; review/blocked fall back to In Progress because this board has no such states |
| `priority` | Priority | both | low/medium/high/critical ↔ low/medium/high/urgent |
| `dependencies` (task-id list) | typed relation | both | always `blocked_by` on the successor; posting one direction creates the reciprocal |
| `estimated_hours` | — | both | no field; written as `Estimate: 80 h` in the description and parsed back out on pull |
| `due_date` | `target_date` | pull | Plane also has `start_date`, which the PMO does not |
| Milestone | Module (or work item type, in newer lines) | — | the AGPL tree has no Milestone model |
| `agent_actions` | — | — | stays in the PMO; surfaced by linking back to the PMO project |

## 5. Secrets and where they live

| Secret | Location | Notes |
|---|---|---|
| Plane API token | `.153:/root/.config/plane/api_key` (600) and `/etc/agentic-pmo/plane_api_key` (640 root:www-data) | bot token, workspace-scoped |
| Plane webhook secret | `.153:/etc/agentic-pmo/plane_webhook_secret` (640 root:www-data), `.104:/root/plane-webhook-secret.txt` (600) | HMAC key; Plane shows it only at creation |
| Plane `.env` (SECRET_KEY, DB/RabbitMQ/MinIO passwords) | `.104:/opt/plane/.env` (600) | backed up nightly, see §7 |
| Google app password | `.104:/root/.config/google/app_password`, `.153:/root/.config/google/app_password` (600) | used by Plane's mailer and by the health-check alerter |
| Plane admin password | in the admin's head, not on disk | reset path in §7.4 |

None of these belong in the repo, in a document, or in a chat message.

## 6. The adapter

Four phases, built in the order that carried least risk. **All four are live.**

**Phase 1 — read-only pull (DONE, 19 Nov 2026).** `backend/integrations/plane/` plus
`backend/routers/plane.py`: a throttled, paginated client; `plane_project_links` and `plane_links`;
a pull that creates or updates the PMO tasks a linked Plane project owns. Nothing is written to
Plane, so nothing can be corrupted, and deletions on the Plane side surface as `stale_links` instead
of deleting a client's plan.

    GET    /api/integrations/plane/status           configured? linked projects, mirrored items
    GET    /api/integrations/plane/plane-projects   Plane projects available to link
    POST   /api/integrations/plane/link             {project_id, plane_project_id}
    GET    /api/integrations/plane/link/{id}        link detail + last sync stats
    DELETE /api/integrations/plane/link/{id}        unlink (optionally delete mirrored tasks)
    POST   /api/integrations/plane/sync/{id}        pull; ?include_relations=true adds dependencies

Measured against the pilot board: first pull created 165 tasks in 4 API calls / 4.1 s; the relations
pass took 169 calls / 189 s (≈53 req/min, inside the 60/min limit) and produced 211 dependency edges
across 162 tasks; a second pull reported 165 unchanged and created nothing.

One finding worth keeping: the v1 read returns `description_html` and leaves `description_stripped`
empty, and Plane has no hours field — so the first mirror arrived with blank descriptions and zero
hours, and the Monitor agent scored a fully estimated EPC plan as unestimated work (health 12). The
pull now strips the HTML and recovers `Estimate: 80 h` into `estimated_hours`; after the backfill the
same project totals 34,910 hours and scores 38. **Any field the PMO needs from Plane has to survive
that round trip deliberately.**

The boundary is enforced, not merely stated: `PATCH` and `DELETE` on any task with a `plane_links` row
return **409** with the work item reference and where to make the change instead —

    This task is owned by Plane — work item #165 in "EPC Project — AI Native PMO pilot".
    Change it in Plane; the PMO picks the change up on the next sync.

Tasks the PMO owns are unaffected. The frontend now shows that sentence rather than a raw HTTP dump.

**Phase 2 — push plans (DONE, 19 Nov 2026).** `backend/integrations/plane/push.py`, gated by
`PLANE_PUSH_ENABLED` and defaulting to a dry run:

    POST /api/integrations/plane/push/{id}?dry_run=true    what would be created — no writes, no calls
    POST /api/integrations/plane/push/{id}?dry_run=false   background job, returns 202 + run id
    GET  /api/integrations/plane/push/runs/{id}            audit rows: running | ok | partial | error

Four rules, and they are what make it safe to point at a client's board:

- **Create only.** A task that already has a `plane_links` row is skipped, never updated. Plane owns the
  work item once it exists; overwriting it from here is precisely the divergence the boundary forbids.
  The consequence is deliberate: renaming a task in the PMO after it has been pushed does *not* change
  Plane.
- **Idempotent on `plane_links`**, so a push that fails halfway finishes on the next run instead of
  duplicating the board.
- **Dry run is the default.** It reads the database, calls nothing, and reports counts, a sample of
  titles and the estimated duration at the 60 req/min pacing.
- **One push per project at a time** (`409` while another is in flight), and every run leaves a
  `plane_push_runs` row, because a job that writes to a live board must be answerable afterwards.

Modules are not created: a PMO task has no phase field (the pack's phases live only in its WBS file), so
there is nothing to group by. Work items and typed relations are what the push sends, with the estimate
written into the description so the pull can read the hours back.

Measured end to end on a throwaway project (6 tasks, a 5-link chain), then deleted:

    dry run           6 to create, 5 relations, ~0.2 min
    push              created 6, relations_created 5, 12 API calls, 0 errors — run status ok
    Plane             6 work items, first item reports blocked_by: 1
    re-push           dry run now says 0 to create (idempotent)
    reconcile         6 unchanged, 0 updated — the pushed content round-trips through the pull
    pilot board       dry run reports 0 to create / 165 already linked: a push there is a no-op

**Phase 3 — inbound webhooks + reconcile (DONE, 19 Nov 2026).** `POST
/api/integrations/plane/webhook`, mounted *without* the JWT dependency because Plane has no user
session — the HMAC signature is the authentication. `plane_webhook_events` records every delivery
(`delivery_id`, event, action, entity, matched signature scheme, status), `GET /events` lists them and
`POST /reconcile/{id}` runs the full pull on demand. The scheduler adds a nightly reconcile at
`PLANE_RECONCILE_TIME` (default 02:30 UTC).

Rules this layer follows, each from observed behaviour:

- **Verify before parsing anything.** A delivery without a valid signature gets `401` and no row.
  With no secret configured the endpoint answers `503` — fail closed, never fall open.
- **Plane signs a different byte string than it sends.** The signature is HMAC over
  `json.dumps(payload)` with default separators; the body is serialised by httpx. The receiver tries
  five canonicalisations (raw, default, compact, and both sorted) and records which matched — in
  practice `raw` matches, but a strict raw-only check is a truck-sized failure waiting to happen.
- **Dedupe on `delivery_id`.** Plane retries with backoff; the same event arrives more than once.
- **Return 2xx even when processing fails.** Plane treats 4xx as permanent rejection and disables a
  webhook after five non-2xx in a row; a disabled hook is silently dead, whereas a recorded `error`
  is repaired by the nightly reconcile.
- **A deletion in Plane never deletes a task here** — it leaves a stale link to be reported.
- Known work items cost 2–3 API calls to refresh; an unknown one triggers a project pull only when the
  payload names a linked project.

Measured against the pilot board: a priority + state change in Plane produced two deliveries
(one `issue.updated` per changed field) **within 5 seconds**, the first applying both changes and the
second correctly reporting `unchanged`. An immediate reconcile then showed `165 unchanged, 0 diverged`,
with all 211 relation edges re-verified in 169 calls.

One defect this phase exposed, worth knowing because it would have been invisible: `AsyncIOScheduler`
must be started from an **async** startup hook. A sync `@app.on_event("startup")` runs in Starlette's
threadpool, where `asyncio.get_running_loop()` raises — the app starts cleanly and the scheduler simply
never attaches, so a nightly job looks scheduled and never runs. `/api/health` now reports
`scheduler_running` and each job's next run, which is how this was caught.

**Phase 4 — agent feed (DONE, 19 Nov 2026).** `backend/agents/schedule.py` computes, deterministically,
what the Monitor agent could not see: days late per task, and every task waiting on an unfinished
predecessor, sorted worst-chain-first. `monitor_agent` sends a `SCHEDULE SIGNALS` block ahead of the
task list and records the counts on the agent action; the system prompt tells the model to reason over
chains — name the predecessor and the consequence — rather than restate the numbers.

On the pilot board the monitor went from "no recorded progress, **dependencies** or resource loading"
about a project with 211 edges, to:

    … all 165 tasks in todo and 162 blocked on unfinished predecessors — a fully serialized,
    front-loaded dependency graph with no float visible. The dominant risk is the convergence of
    three chains: (1) engineering (P&IDs → FEED Design Review → FEED Final Report → 30% Model
    Review → IFC Register), (2) procurement (POs → VDR → Packing → Logistics → Site Receipt) …

Two things to keep in mind about this layer. The task list is capped at 180 lines and dependency
chains at 12 — the *counts* are computed before truncation, because reporting the size of the sample
as the total understated a fully-blocked plan as "12 tasks". And `health_score` moves between runs
(38–45 on identical data) because it is the model's judgement, not the arithmetic; the counts are the
stable part, which is why they are also written to the agent action.

Schema as built (two tables; `Base.metadata.create_all()` creates them, there is no migration tooling):

    plane_project_links   id, project_id (unique), workspace_slug, plane_project_id,
                          plane_project_name, plane_identifier, last_synced_at, last_sync_stats
                          UNIQUE (workspace_slug, plane_project_id)

    plane_links           id, project_id, task_id (unique, FK tasks), plane_work_item_id,
                          plane_sequence_id, plane_state_name, plane_module, content_hash,
                          last_pulled_at
                          UNIQUE (project_id, plane_work_item_id)

Both cascade from `Project` — deleting a project removes its links and mirrored tasks, which is
verified by a test rather than assumed (the first version of `project_packs` left orphans behind).

## 7. Operations

### 7.1 Restart, upgrade, rollback

    cd /opt/plane
    docker compose --env-file .env up -d                  # start / apply .env changes
    docker compose --env-file .env up -d --force-recreate api worker beat-worker
    docker compose ps                                     # all 12 healthy, migrator exited 0

Upgrades are deliberate: change `APP_RELEASE` in `/opt/plane/.env`, `pull`, `up -d`, then confirm
`/api/instances/` still answers and the pilot board still loads. Never track `preview` — releases land
weekly and the API has already renamed issues to work items with a deprecated path kept alongside.

### 7.2 Backups

- `.104` at 02:15 UTC (`plane-dump.timer`): `pg_dump -Fc` of the database, a tar of the `plane_uploads`
  volume, and a copy of `.env` (without it the encrypted instance settings cannot be read back).
  Local retention 3 days. Files in `/var/backups/plane`, mode 600. Log: `/var/log/plane-dump.log`.
- `.153` at 02:45 UTC (`plane-backup-pull.timer`): rsync **pull** from `.104` to
  `/root/plane-backups`, retention 30 days. Pull rather than push, so a lost or compromised Plane box
  cannot delete its own history. Log: `/var/log/plane-backup-pull.log`.

Restore, in outline:

    # on .104, into a scratch database first — never straight over the live one
    docker cp plane_<ts>.dump plane-plane-db-1:/tmp/
    docker exec -e PGPASSWORD=… plane-plane-db-1 createdb -U plane plane_restore
    docker exec -e PGPASSWORD=… plane-plane-db-1 pg_restore -U plane -d plane_restore /tmp/plane_<ts>.dump
    # verify row counts, then point Plane at it (DATABASE_URL) and restart
    # uploads: docker run --rm -v plane_uploads:/data -v $PWD:/b alpine tar xzf /b/uploads_<ts>.tgz -C /data

A dump alone is not a restore: without `plane_env_<ts>.txt` the `SECRET_KEY` is gone and every
encrypted instance setting (mail password included) becomes unreadable.

### 7.3 Monitoring

`.153` runs `plane-health.py` every 15 minutes: public endpoint returns 200 with a config payload, TLS
certificate has more than 14 days left, and the newest backup is under 26 hours old. On failure it
emails the owner through the same Google SMTP path, at most once an hour. Log:
`/var/log/plane-health.log`. It runs from `.153` deliberately — a monitor on the box it watches only
reports the box is up when it can no longer tell you anything.

`GET /api/health` also reports `scheduler_running` and each scheduled job's next run. Check it after any
restart: a job that never registered is otherwise indistinguishable from a job that is waiting.

### 7.4 Lost admin password

There is no SMTP-free self-service reset. Generate a one-time reset link server-side:

    docker exec -i plane-api-1 python - <<'PY'
    import os, django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE","plane.settings.production"); django.setup()
    from plane.authentication.views.app.password_management import generate_password_token
    from plane.db.models import User
    u = User.objects.get(email="ashwin@ainativeorganisations.com")
    uid, tok = generate_password_token(u)
    print(f"https://plane.agenticpmo.tech/accounts/reset-password/?uidb64={uid}&token={tok}")
    PY

The link is single-use and expires in one hour. Password strength is judged by zxcvbn (score ≥ 3), not
by the character-class ticks shown in the form — four unrelated words pass, `Name1!` does not.

### 7.5 Configuration traps in this deployment

- Plane reads mail settings from `instance_configurations`, and `configure_instance` only inserts
  missing rows — editing `.env` after first boot has no effect on existing keys. Update the row, then
  `manage.py clear_cache`, or the instance endpoint keeps reporting stale values.
- The release `docker-compose.yml` ships literal `plane:***@` fallbacks for `DATABASE_URL` and
  `AMQP_URL`; leaving them unset produces "password authentication failed" in the migrator while the
  database itself is fine.
- `ENABLE_SIGNUP` and friends are not in the compose's env anchors; inject them per service in
  `docker-compose.override.yml` or they never reach the container.
- Modules and cycles are per-project feature flags. Creating a module 400s until the project is
  PATCHed with `module_view: true`.

### 7.6 Endpoint map, and running a push

Every path below is under `/api/integrations/plane` except the health check.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/webhook` | HMAC signature | Plane → PMO, per-event refresh |
| GET | `/status` | JWT | configuration + link counts |
| GET | `/plane-projects` | JWT | boards available to link |
| POST | `/link` | JWT | link a PMO project to a Plane project |
| GET / DELETE | `/link/{id}` | JWT | link detail / unlink |
| POST | `/sync/{id}` | JWT | pull (`?include_relations=true`) |
| POST | `/reconcile/{id}` | JWT | full pull with relations |
| POST | `/push/{id}` | JWT | **dry run by default**; writes only with `?dry_run=false` |
| GET | `/push/runs/{id}` | JWT | push audit rows |
| GET | `/events` | JWT | webhook deliveries and their outcomes |
| GET | `/api/health` | none | liveness + scheduler jobs and their next run |

Running a push (server-side; never paste the admin password into a shell history):

    TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
      -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" | python3 -c \
      'import sys,json;print(json.load(sys.stdin)["token"])')

    # 1. always dry run first — reports counts and duration, calls nothing
    curl -s -H "Authorization: Bearer $TOKEN" \
      -X POST "localhost:8000/api/integrations/plane/push/3?dry_run=true"

    # 2. the real thing: 202 + run id, executes in the background
    curl -s -H "Authorization: Bearer $TOKEN" \
      -X POST "localhost:8000/api/integrations/plane/push/3?dry_run=false"

    # 3. read the run, not the HTTP response, for the outcome
    curl -s -H "Authorization: Bearer $TOKEN" \
      "localhost:8000/api/integrations/plane/push/runs/3"

Turning the write path off is one env change and a restart: `PLANE_PUSH_ENABLED=0` in
`/var/www/agentic-pmo/app/.env`, then `systemctl restart agentic-pmo`. The pull, webhook and reconcile
paths are unaffected.

## 8. Licence position

Plane is AGPL-3.0-only. It runs here unmodified, as a separate service, reached over HTTP. The PMO is
Apache-2.0 and contains only an HTTP client. That is a service boundary, not a derivative work, so no
PMO source has to be published. Do not fork Plane, do not vendor its code, and do not modify it in
place to add features — if a change is needed, it belongs in the adapter or upstream as a patch.

## 9. Open items

1. **Sender address.** Mail currently leaves as `ashwin@ainativeorganisations.com` because the app
   password belongs to that mailbox. An alias cannot authenticate; to send as `prashant@` the domain
   would need verifying in Resend.
2. **Receiving mail on agenticpmo.tech.** The zone has no MX, so `pmo@agenticpmo.tech` can send but not
   receive. Not currently used.
3. **DMARC.** `p=none` on `agenticpmo.tech`. Tighten to `p=quarantine` once Resend has sent cleanly for
   a couple of weeks.
4. **Host horizon.** `.104` has a finite renewal date. The backup routine exists so that a move is a
   restore, not a rebuild — but the move has to be planned, not discovered.
5. **The push is create-only.** A task renamed, re-estimated or re-prioritised in the PMO after it has
   been pushed keeps its old values in Plane, because updating a linked work item is exactly the
   divergence the boundary forbids. If PMO-side edits should propagate, that is a deliberate new
   decision — a staged "propose change in Plane" flow — not a bug to patch.
6. **The Alert agent has not been given the same feed.** It still auto-detects only overdue, `blocked`
   status and missing estimates on a schedule; the Monitor is the agent that reasons over chains.
   Until they share `schedule.analyse`, the scheduled alerting is weaker than the on-demand monitor.
7. **The guard covers task writes only.** Deleting a linked PMO project removes its mirrored tasks
   locally without touching Plane — intended, but anyone reading the PMO alone would see a plan
   disappear while the board still shows it.

## 10. Build record — 19 November 2026

What exists, against what it was measured on. No estimate in this table: every number came from a run.

| Piece | Evidence |
|---|---|
| Plane v1.5.0 self-hosted on `.104` | 12 containers, ~1.2 GB RSS, HTTPS hostname with a Let's Encrypt certificate |
| Mail | Google Workspace SMTP; one real message delivered from Plane's own mailer (`sent = 1`) |
| Pull | 165 tasks, 162 dependency sets, 211 edges; 34,910 hours recovered; re-pull 165 unchanged |
| Push | throwaway 6-task chain: 6 created, 5 relations, 12 calls, 0 errors; re-push created 0; reconcile after push 6 unchanged |
| Webhooks | two deliveries within ~5 s of an edit; first applied, second correctly reported unchanged |
| Reconcile | nightly job registered, next run visible at `/api/health`; 0 diverged |
| Boundary | `409` on PATCH/DELETE of a mirrored task; local tasks still editable (`200`) |
| Monitor agent | reports 162 tasks waiting on an unfinished predecessor and names the chains |
| Backups | nightly dump 845 KB + uploads + `.env`, pulled to the other box, 30-day retention |
| Monitoring | external check every 15 min: endpoint, certificate, backup age; alert path tested |
| Tests | 106 passing (11 webhook, 10 pull/mapping/guard, 8 push, 9 schedule, plus the existing suite) |
| Licence | Plane AGPL-3.0 unmodified behind HTTP; PMO Apache-2.0 with no shared code |

Deliberate non-goals, so they are not mistaken for gaps: no forked Plane, no shared database, no
automatic update of a linked work item, no modules on push. Each of those would break either the licence
position or the single-owner boundary described in section 1.

This document is generated from `docs/plane-integration.md` by `docs/build_note.py`, which applies the
page setup and table styling pandoc leaves to Word defaults; the PDF is that docx converted by
LibreOffice. Edit the markdown, not the docx, or the next build will overwrite it.
