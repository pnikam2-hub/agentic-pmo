# ROUND 2 of 3 — Phase A role enforcement

Repository: /root/projects/agentic-pmo. Round 1 is committed to the working tree and green: the `users`
and `audit_logs` tables exist, `backend/auth.py` has `current_user` / `require_auth` / `require_role` /
bootstrap, `backend/routers/admin.py` is gated, and `pytest backend/tests -q` is 106 passed. Read
`docs/sso-rbac-plan.md` §A5 and §A6 and `docs/BUILD-PROMPT-round1.md` before starting.

This round does exactly two things: **put role gates on the seven existing routers**, and write the audit
rows §A6 asks for. No frontend, no `test_rbac.py`, no report file, no commit.

## 1. Shared guards, defined once (`backend/auth.py`)

Add module-level guard instances next to `require_role` so every router imports the same callables
(FastAPI caches a dependency per callable per request, so a shared instance resolves the token once):

```python
any_role      = require_role("viewer", "contributor", "pmo_lead", "admin")
contributor_up = require_role("contributor", "pmo_lead", "admin")
pmo_lead_up   = require_role("pmo_lead", "admin")
admin_only    = require_role("admin")
```

`backend/routers/admin.py` must then import `admin_only` from `backend.auth` instead of defining its own,
and `backend/main.py` must use `any_role` (not `require_auth`) on the seven routers. `require_auth` stays
in `auth.py` unchanged for anything that imports it — it is not the gate any more.

## 2. The permission matrix to implement

Every rule below comes from plan §1. Where a route is not named in §1 I have decided it and marked the
decision **(beyond the matrix)** — those go in the report.

| Router | Read routes | Write routes | Role |
|---|---|---|---|
| `projects.py` | GET list, GET one | POST, PATCH | `pmo_lead_up` |
| | | DELETE | `admin_only` **(beyond the matrix** — a project delete cascades to tasks, milestones, agent actions and the pack snapshot, and cannot be undone) |
| `tasks.py` | GET list, GET one | POST create | `pmo_lead_up` |
| | | PATCH | `contributor_up`, with the field rule below |
| | | DELETE | `pmo_lead_up` |
| `agents.py` | GET actions | POST plan / monitor / alert | `pmo_lead_up` |
| | | PATCH actions/{id}/resolve | `contributor_up` **(beyond the matrix** — acknowledging a recommendation is not editing the plan) |
| `templates.py` | GET list, GET one | POST apply | `pmo_lead_up` |
| `packs.py` | GET packs, GET pack, GET project pack | POST apply | `pmo_lead_up` |
| | | DELETE project pack | `pmo_lead_up` |
| `plane.py` | GET status, plane-projects, link/{id}, events, push/runs | POST link, POST push, POST sync, POST reconcile, DELETE link | `pmo_lead_up` |
| `dashboard.py` | GET | — | `any_role` |
| `alerts.py` | GET status, GET webhooks | POST test | `pmo_lead_up` |
| | | POST webhooks, DELETE webhooks/{id} | `pmo_lead_up` **(beyond the matrix** — an outbound webhook can receive alert payloads off-site, so it is a lead-level change, not a viewer one) |
| `plane_webhook.py` | — | — | **no role dependency; HMAC only. Do not touch this file.** |

## 3. The task-PATCH field rule

§1 gives contributors "move a task between statuses, log actual hours" and reserves "edit tasks" for
`pmo_lead`. So `PATCH /api/projects/{pid}/tasks/{tid}`:

- gate: `Depends(contributor_up)`, so the caller always has at least contributor;
- if the caller is `contributor`, the only fields they may send are `status` and `actual_hours`. Any other
  field in the body → 403 naming the fields that were refused and the two they may use.
- `pmo_lead` and `admin` may send any field.
- Route the refusal through the existing 403 shape (message names the required role), and test both sides.

## 4. Audit writes (§A6)

Call `audit(...)` from these handlers only, using the acting `User` the guard returns and the existing
`ACTIONS` names:

| Handler | action | target_type / id | detail |
|---|---|---|---|
| project create | `project_created` | project / id | name |
| project delete | `project_deleted` | project / id | name, and the number of tasks removed |
| task delete | `task_deleted` | task / id | title, project_id |
| agent plan / monitor / alert | `agent_run` | project / id | agent name |
| plane link | `plane_linked` | project / id | plane project id |
| plane unlink | `plane_linked` | project / id | `{"unlinked": true}` |
| plane push | `plane_push` | project / id | dry_run flag |
| plane sync / reconcile | `plane_sync` | project / id | which |

`db.commit()` after the write already covers the audit row in the same transaction — add the `audit()`
call before the existing commit, never a second commit. Nothing in `detail` may contain a password, a
hash or a token; no free-text task descriptions either, only the fields listed.

Handlers that write audit rows therefore need the user: add exactly one parameter,
`actor: User = Depends(<the guard>)`, to those handlers. Leave every other handler signature alone.

## 5. The test changes this round is allowed to make — and only these

Adding a `Depends(...)` parameter to a handler breaks the three tests that call the handler **directly**
rather than over HTTP (`backend/tests/test_plane_integration.py` lines ~225-266: `update_task` and
`delete_task`, including the `test_unmirrored_task_is_still_editable` success path). You may:

1. pass a stand-in `actor` in those three direct calls (a `User` with `role="admin"`), and
2. in `backend/tests/test_api.py`, extend the `auto_auth` fixture to also override `current_user`
   (`app.dependency_overrides[current_user] = lambda: <User role="admin">`) and pop it in teardown, and
   make `TestAuth._real_auth` pop **both** overrides — otherwise the "unauthenticated" tests would still
   be authenticated through `current_user` and assert 200 against a 401 expectation.

Nothing else. **Do not change a single assertion, test name or expected status code.** If a test fails
because it needs a role higher than admin, that is a fixture mistake, not a test to weaken. Every test
edit you make goes in your final report, one line each, with the reason.

## 6. What must not change

- `.venv/bin/python -m pytest backend/tests -q` → **106 passed**, no exceptions, no skips.
- `POST /api/auth/login`, `GET /api/auth/verify` behaviour and bodies (round 1 verified them).
- The `plane_webhook.py` router: no role dependency, HMAC auth only.
- Status codes on refusals: 401 when there is no valid token, 403 when the token is valid but the role is
  insufficient. A viewer must get 403 — not 401, not 404 — on a task move.
- No new dependencies, no new tables, no frontend files, British spelling, comments that explain why.

## 7. When you are done

1. Run `.venv/bin/python -m pytest backend/tests -q` and paste the summary line.
2. Run `.venv/bin/python -c "import backend.main"`.
3. In your final message, give: the permission table as implemented (route → role), every audit call site,
   every test line you changed, and any place where the plan and the code disagreed. State plainly
   anything you did not do. Do not write a report file — round 3 produces it.
