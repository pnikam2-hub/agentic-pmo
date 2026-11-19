# Plane integration — what exists, what it does, and how to run it

Status: infrastructure live, **Phase 1 (read-only pull)** and **Phase 4 (schedule-aware Monitor)**
shipped, 19 November 2026. Write-back and inbound webhooks are phases 2–3 — see section 6.
Audience: whoever operates Agentic PMO, and whoever builds the rest of the adapter.

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
- Endpoints used: `projects/`, `work-items/`, `work-items/{id}/relations/`, `states/`, `modules/`,
  `modules/{id}/module-issues/`, `comments/`.
- There is no hours field on a work item; `estimated_hours`, discipline, deliverables and acceptance
  criteria go into `description_html` with the pack reference (`epc_project/T014`).

**Relations are the reason this integration is worth doing.** Plane stores `blocking`, `blocked_by`,
`duplicate`, `relates_to`, `start_before`, `start_after`, `finish_before`, `finish_after` — i.e. the
FS/SS/FF/SF taxonomy the PMO's `Task.dependencies` JSON list cannot express. Posting `blocked_by` from
the successor also creates the reciprocal `blocking` row, so the sync must never write both directions.

**Webhooks** — inbound to the PMO, when the adapter lands

- HMAC-SHA256 over the raw body in `X-Plane-Signature`; verify before parsing.
- Deliveries carry `delivery_id` and `event_id` — dedupe on them, because Plane retries with backoff.
- Return 2xx immediately and queue. A 4xx is treated as a permanent rejection; five non-2xx in a row
  silently disables the webhook and emails its creator.
- Rejected target URLs: `localhost`, `127.0.0.1`, private ranges (unless allowlisted via
  `WEBHOOK_ALLOWED_IPS` / `WEBHOOK_ALLOWED_HOSTS`). The PMO's public host satisfies this.
- Webhooks are workspace-level only, and their CRUD is **not** in the key-authenticated v1 API — they
  are created once in the Plane UI at Workspace settings → Webhooks.

## 4. Field mapping (validated on the pilot board)

| Agentic PMO | Plane | Notes |
|---|---|---|
| Project | Project (+ `identifier`) | identifier is uppercase, ≤12 chars |
| Domain pack | — | survives as text in each work item's description and in the PMO's `project_packs` |
| Pack phase (`phases[].name`) | Module | phases in `wbs_template.json` are dicts `{id, name, weeks}` |
| Task | Work item | `sequence_id` is Plane's per-project number |
| `status` | State | todo→Backlog, in_progress→In Progress, review→In Review, done→Done, blocked→Blocked |
| `priority` | Priority | low/medium/high/critical → low/medium/high/urgent |
| `dependencies` (task-id list) | typed relation | always `blocked_by` on the successor |
| `estimated_hours` | — | no equivalent; goes in the description |
| `due_date` | `target_date` | Plane also has `start_date`, which the PMO does not |
| Milestone | Module (or work item type, in newer lines) | the AGPL tree has no Milestone model |
| `agent_actions` | — | stays in the PMO; surfaced by linking back to the PMO project |

## 5. Secrets and where they live

| Secret | Location | Notes |
|---|---|---|
| Plane API token | `.153:/root/.config/plane/api_key` (600) | bot token, workspace-scoped |
| Plane `.env` (SECRET_KEY, DB/RabbitMQ/MinIO passwords) | `.104:/opt/plane/.env` (600) | backed up nightly, see §7 |
| Google app password | `.104:/root/.config/google/app_password`, `.153:/root/.config/google/app_password` (600) | used by Plane's mailer and by the health-check alerter |
| Plane admin password | in the admin's head, not on disk | reset path in §7.4 |

None of these belong in the repo, in a document, or in a chat message.

## 6. The adapter

Phasing, in the order that carries least risk. **Phase 1 is built and running.**

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

**Phase 2 — push plans (≈3 days).** Plan agent output → Plane project, modules, work items, relations.
Idempotent on `plane_links`, behind a flag, as a background job.

**Phase 3 — inbound webhooks + reconcile (≈3 days).** `/api/integrations/plane/webhook` with HMAC
verification, dedupe table, and a nightly reconciliation that compares `content_hash` per link and
reports divergence instead of silently overwriting.

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
5. **The write half does not exist.** Phase 1 mirrors Plane into the PMO; nothing pushes yet, so a plan
   generated in the PMO still reaches Plane by the one-off script in `/root/plane-pilot/push.py` rather
   than through the product. Phase 2 replaces that script.
6. **The Alert agent has not been given the same feed.** It still auto-detects only overdue, `blocked`
   status and missing estimates on a schedule; the Monitor is the agent that reasons over chains.
   Until they share `schedule.analyse`, the scheduled alerting is weaker than the on-demand monitor.
7. **The guard covers task writes only.** Deleting a linked PMO project removes its mirrored tasks
   locally without touching Plane — intended, but anyone reading the PMO alone would see a plan
   disappear while the board still shows it.
