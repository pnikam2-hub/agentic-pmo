# Phase A report — local accounts, roles, audit, and the enterprise gate

Status: **complete and verified** on 20 November 2026. Scope was `docs/sso-rbac-plan.md` §2 (Phase A).
Phases B (OIDC) and C (hardening) are not started; what they inherit is listed at the end.

Built by Claude Code, driven by Hermes. Rounds 1–2 ran on GLM-5.2 (Z.AI); rounds 3–4, the gstack review
and the fix round ran on DeepSeek V4 Pro, because the Z.AI five-hour quota was exhausted mid-build and
the work was not worth stalling ten hours for. The reviewer of record is the gstack `/review` pass
(`docs/reviews/phaseA-code-review.md`), not the builder.

## 1. What changed

| File | Change |
|---|---|
| `backend/models.py` | **Appended only**: `User` (username/email lower-cased and unique, nullable password for future OIDC, role as plain string, `token_version`, `is_active`, `source`, `external_id`) and `AuditLog` (actor, actor_role, action, target, JSON detail, ip). Nothing existing altered — `create_all()` cannot migrate. |
| `backend/auth.py` | Rewritten around one resolution point, `current_user`. `require_auth` keeps its `-> str` signature; `require_role` returns a guard that resolves through `current_user`; shared guards `any_role`, `contributor_up`, `pmo_lead_up`, `admin_only`. JWT claims `sub`/`usr`/`role`/`ver`/`iss`/`iat`/`exp`, HS256, `JWT_EXPIRY_HOURS` (default 8). `verify_token` reloads the user and rejects inactive or stale-version tokens. `bootstrap_admin` (empty table only). `authenticate` with a constant-cost dummy compare. `validate_password`, `client_ip`. |
| `backend/audit.py` | `audit()` helper plus an `ACTIONS` allow-list, so a typo is a loud failure rather than a silent new action name. |
| `backend/routers/auth.py` | Login by `identifier` (username or email) or legacy `username`; response adds role, display name, expiry; `/verify` unchanged; `/me` with a permissions list; own-password change that bumps `token_version`. |
| `backend/routers/admin.py` | User list/create/patch/reset/soft-delete and the audit query, all admin-only. Last-admin protection, now atomic at write time. |
| `backend/routers/{projects,tasks,agents,templates,packs,plane,alerts,dashboard}.py` | Role gates per the matrix below; the contributor field rule; audit rows for project create/update/delete, task delete, agent run, Plane link/unlink/push/sync; `access_denied` on both guard-level and field-level refusals. |
| `backend/main.py` | Admin router included; `any_role` replaces `require_auth` on the seven routers; `bootstrap_admin` after `init_db()`. The Plane webhook stays outside every role gate. |
| `backend/tests/conftest.py` | `DATABASE_URL` pinned to a scratch file: the webhook tests start the app, so without the pin the suite would write a `users` row with the test password into the demo database and lock the real `.env` admin out. |
| `backend/tests/test_rbac.py` | **New** — 19 acceptance tests driving real JWTs and real guards. |
| `backend/tests/test_api.py`, `test_plane_integration.py` | Test-infrastructure only: `current_user` stand-in in the fixture, and an `actor=` argument on three direct handler calls. No assertion changed. |
| `frontend/js/api.js` | Session (token + role + name), `can()`, `refreshSession()`, auth/admin API methods. |
| `frontend/js/app.js`, `index.html` | `data-requires` visibility with a MutationObserver, route guard, Admin nav item, signed-in-as footer. |
| `frontend/js/admin.js` | **New** — users table (role select, deactivate, reset password, create) and the audit log with action/actor filters. |
| `frontend/js/{projects,dashboard,packs,templates}.js`, `css/app.css` | Gated create/edit/run/attach controls, static kanban cards for read-only roles, contributor-safe task modal. |
| `docs/` | The plan, four round briefs, the review brief, the review itself, this report. |

## 2. The permission matrix as implemented

Cumulative; every cell is enforced at the router or handler boundary, and each denial writes an audit row.

| Capability | viewer | contributor | pmo_lead | admin |
|---|---|---|---|---|
| Read projects, tasks, dashboard, packs, templates, Plane status, agent log | yes | yes | yes | yes |
| Move a task between statuses, log actual hours | no | yes | yes | yes |
| Create/edit projects and tasks, run agents, apply templates and packs, link/push/sync Plane, alert test and webhooks | no | no | yes | yes |
| Delete a project | no | no | no | yes |
| Manage users, roles, passwords; read the audit log | no | no | no | yes |

Three cells go beyond the plan's §1 table, each for a stated reason: **project delete is admin-only**
(it cascades, and nothing else can undo it), **agent-action resolve is contributor** (acknowledging a
recommendation is not editing the plan), and **alert webhook registration is pmo_lead** (an outbound
webhook moves alert payloads off-site). All three are recorded here rather than left to be rediscovered.

## 3. Verification — commands, not opinions

| Check | Result |
|---|---|
| `pytest backend/tests -q` | **125 passed**, run twice back to back |
| `pytest backend/tests/test_rbac.py -q` | 19 passed |
| `python -c "import backend.main"` | clean |
| Independent probe 1 (identity, tokens, audit, bootstrap) | **52/52** |
| Independent probe 2 (the full role matrix over HTTP) | **44/44** |
| Independent probe 3 (the fix round: F2, F5, F6, F8, F9) | **12/12** |
| Login timing, unknown identifier vs wrong password | **323.7 ms vs 322.6 ms — 1.00×** (was 10 ms vs 324 ms, 32×) |
| Browser, six screens × three roles (Playwright, 1440×900) | zero console or page errors; viewer sees no create/edit/run/drag; pmo_lead redirected from `#admin` with a toast |
| Contributor saves hours through the task modal | assignee field absent, save → "Task updated", modal closes |
| Plane webhook with HMAC and no JWT | still accepted; still no role dependency |

The browser pass is the check that mattered most: it caught two residual write affordances a viewer
could see (the "From template" button and the "Attach one" pack link) that no unit test would have
found.

## 4. The review, and what was done with it

gstack `/review` produced eleven findings and a verdict of "not yet fit for an enterprise review". Ten
were accepted and fixed:

| Finding | Disposition |
|---|---|
| F1 login timing oracle (major) | Fixed — constant dummy compare; measured 1.00× after |
| F2 last-admin check-then-write race (major) | Fixed — invariant re-checked after the mutation, before commit, rollback on violation |
| F3 contributor cannot save a task from the SPA (major) | Fixed — the modal sends only changed fields; verified in the browser |
| F4 field-refusal 403 not audited | Fixed |
| F5 raw identifier stored on failed login | Fixed — digest + length, never the input |
| F6 >72-byte password → 500 | Fixed — 422 with a shared validator |
| F7 audit ip is the proxy address | Fixed — `client_ip()` with trusted-proxy handling; login rows now carry an ip |
| F8 `iss` minted but never validated | Fixed — decoded with `issuer="agentic-pmo"`, `sub` must be digits |
| F9 empty-string email accepted | Fixed — refused |
| F11 SPA role frozen at login | Fixed (boot refresh); additionally, a role change bumps `token_version`, so a demoted user's next request is a 401 and they re-authenticate — there is no window in which a stale role can be used |
| F10 audit has no tamper-evidence | **Deferred** — a hash chain or append-only DB role changes the table and the write path; §6 does not require it. First item of Phase C |

## 5. What this deliberately does not do

Per plan §5, and restated because an enterprise reviewer will ask: no per-project ACLs (roles are global),
no SCIM, no MFA of our own, no OIDC yet (Phase B), no refresh tokens or `jti` (a stolen token is live for
up to 8 hours; the mitigations are DB-authoritative roles and `token_version`), per-IP rate limiting only
(not per-identifier), no zxcvbn password policy, no audit CSV export, no security headers at the app.

## 6. Phase B and C, in the order they should be taken

1. **F10 tamper-evidence** for the audit trail — hash-chain rows, or move the writer to an append-only DB
   role. Decide before any client relies on the trail as evidence.
2. **OIDC** (plan §3) — `client_id`/`secret`, discovery, PKCE, JWKS validation, group→role mapping, JIT
   provisioning. Local login stays available so an IdP outage cannot lock the owner out.
3. **Per-identifier login throttling** and **zxcvbn** on local passwords.
4. **Security headers** at the proxy, **audit CSV export**, and the one-page RBAC matrix for the security
   questionnaire.
5. **Postgres** — the atomic last-admin guard should become `SELECT … FOR UPDATE`; the comment in
   `admin.py` records this.

## 7. Operating notes

- The `.env` admin is created on first start against an empty `users` table and is never recreated or
  overwritten. Changing `ADMIN_PASSWORD` after that does nothing — reset through
  `POST /api/admin/users/{id}/password` with an admin token, or delete the row deliberately.
- `JWT_EXPIRY_HOURS` defaults to 8. A password change, a role change or a deactivation invalidates every
  outstanding token for that user immediately; that is the point, and it is covered by tests.
- The audit log holds no password, hash or token — asserted by test, not only by intent.
- No deployment to `agenticpmo.tech` was made as part of this work.
