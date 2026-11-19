# SSO and role-based permissions — scope and build plan

Status: scoped 19 Nov 2026. Phase A handed to Claude Code; B and C follow in separate rounds.
Owner of the design: Hermes. Builder: Claude Code (GLM-5.2). Reviewer: Hermes, with the test suite as
the gate.

## 0. Where we are

`backend/auth.py` is 118 lines and does exactly one thing well: it authenticates **one** user whose
credentials come from `.env`, hashes it with bcrypt at import time, and issues a 24-hour HS256 JWT whose
only claim is `sub`. There is no `users` table, no role, no per-user revocation, no audit of who did
what, and every protected route uses the same `require_auth` dependency. That is a reasonable shape for
a demo and it is the first thing an enterprise security review will fail.

Facts that shape the work:

- 11 tables today; none is `users`. Adding one is safe — `Base.metadata.create_all()` creates new
  tables at startup. **Altering an existing table is not**: there is no migration tool, so nothing may
  change on `tasks`, `projects`, `plane_links` or the rest.
- Tokens carry no role and no version. Revocation means "change the env password and restart", which
  logs everyone out — unacceptable once there is more than one user.
- The frontend stores the JWT in `localStorage['agentic_pmo_token']` and calls `isLoggedIn()`; role
  handling there is presentation only and must never be the access control.
- 106 tests pass. The suite must still pass, and new tests must cover each denial, not just each success.

## 1. Target model

Four roles, cumulative. Deliberately four, not twelve: every additional role has to be explained in a
security review and supported forever.

| Capability | viewer | contributor | pmo_lead | admin |
|---|---|---|---|---|
| Read projects, tasks, dashboard, packs | ✅ | ✅ | ✅ | ✅ |
| Move a task between statuses, log actual hours | ❌ | ✅ | ✅ | ✅ |
| Create/edit projects, tasks, milestones; run agents | ❌ | ❌ | ✅ | ✅ |
| Link/push/sync with Plane, change pack | ❌ | ❌ | ✅ | ✅ |
| Manage users, roles, reset passwords, view audit log | ❌ | ❌ | ❌ | ✅ |

Identity comes from one of two sources, and the user record says which:

- `source = "local"` — username/email + password we store (bcrypt). Kept as the fallback and for the
  bootstrap admin, because an SSO-only system locks you out when the IdP is down.
- `source = "oidc"` — provisioned on first successful SSO login (JIT), linked by verified email, role
  taken from a group→role mapping. No password stored.

## 2. Phase A — local accounts and enforcement (build now)

Tasks in order. Each is small on purpose: the agent's round budget is the constraint, and a half-built
auth layer is worse than none.

**A1. Schema** (`backend/models.py`, append only)
`User`: id, username (unique, citext-equivalent lower-case), email (unique), display_name,
password_hash (nullable for oidc), role, is_active, source, external_id (unique when present),
token_version (int, default 0), created_at, last_login_at.
`AuditLog`: id, at, actor, actor_role, action, target_type, target_id, detail (JSON), ip.
No relationship to Project — audit must survive project deletion.

**A2. Auth core rewrite** (`backend/auth.py`)
- Keep `hash_password` / `verify_password` as they are; they are correct.
- `bootstrap_admin()`: on startup, if no user exists, create the `.env` admin as role `admin`,
  `source=local`. Idempotent. This preserves today's behaviour and the existing tests.
- `authenticate(identifier, password)`: identifier may be username or email; refuses inactive users;
  updates `last_login_at`.
- `create_token(user)`: claims `sub` (user id), `usr`, `role`, `ver`, `iat`, `exp`, `iss="agentic-pmo"`.
- `verify_token(token) -> User | None`: decode, then load the user and reject if
  `is_active` is false or `ver != user.token_version`. A token is only valid while its user is.
- `require_role(*roles)` dependency factory; `require_auth` stays as an alias for
  `require_role("viewer","contributor","pmo_lead","admin")` so existing imports do not break.
- `JWT_EXPIRY_HOURS` becomes env-configurable, default 8 (down from 24).

**A3. Login and identity endpoints** (`backend/routers/auth.py`)
- `POST /api/auth/login` accepts `identifier` (username or email) and `password`; response adds
  `role`, `display_name`, `expires_at`. Existing `username` field stays accepted for compatibility.
- `GET /api/auth/me` returns the current user, role and permissions list.
- `POST /api/auth/password` — change own password; requires the old one; bumps `token_version`.

**A4. Admin surface** (`backend/routers/admin.py`, new, all `require_role("admin")`)
- `GET /api/admin/users`, `POST /api/admin/users` (local user with a set password),
  `PATCH /api/admin/users/{id}` (role, is_active, display_name), `POST /api/admin/users/{id}/password`
  (reset, bumps token_version), `DELETE /api/admin/users/{id}` (soft: is_active=false; refuse to
  deactivate the last active admin).
- `GET /api/admin/audit?limit=&actor=&action=` — newest first.

**A5. Enforcement** (existing routers)
Apply roles at the router boundary, not per handler: reads allow all four roles; task status/hours
updates allow contributor+; project/task/milestone creation and agent runs allow pmo_lead+; the Plane
integration and pack application allow pmo_lead+; admin router is admin only. The Plane **webhook**
endpoint keeps its HMAC auth and must NOT gain a role dependency — it has no user.

**A6. Audit writes**
One helper `audit(db, actor, action, target_type, target_id, detail)` called from: login success and
failure (actor "anonymous", action "login_failed"), user create/update/reset/deactivate, project
create/delete, task delete, agent run, push/sync/link. Never store passwords or tokens in `detail`.

**A7. Frontend** (`frontend/js/api.js`, `app.js`, `login` view)
Store role alongside the token; show the Admin nav item only for `admin`; hide "Run agent" and create
buttons for roles that cannot use them. Presentation only — the server decides. On 401/403 show the
server's `detail` (the api.js change already surfaces it).

**A8. Tests** (`backend/tests/test_rbac.py`, new; keep `test_api.py` green)
- bootstrap admin exists exactly once; second startup creates nothing
- login by username and by email; wrong password refused; inactive user refused
- token with a stale `ver` refused; deactivation invalidates a live token
- each role can and cannot do its boundary actions (viewer cannot move a task: 403; contributor can;
  contributor cannot create a project: 403; pmo_lead can; only admin reaches `/api/admin/*`)
- last admin cannot be deactivated
- audit rows written for login failure and for a role-denied write
- webhook endpoint still works with a valid signature and no JWT

## 3. Phase B — OIDC single sign-on (separate round)

Config (all optional; SSO off unless `OIDC_ISSUER` is set):
`OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`,
`OIDC_SCOPES` (default `openid email profile`), `OIDC_GROUP_CLAIM` (default `groups`),
`OIDC_ROLE_MAP` (JSON, e.g. `{"pmo-admins":"admin","pmo-leads":"pmo_lead","*":"viewer"}`),
`OIDC_DEFAULT_ROLE` (default `viewer`), `OIDC_AUTO_PROVISION` (default true).

- `GET /api/auth/sso/start` — state + nonce + PKCE verifier in a short-lived signed cookie, redirect to
  the issuer's authorize endpoint (discovered from `/.well-known/openid-configuration`).
- `GET /api/auth/sso/callback` — verify state, exchange code at the token endpoint, validate the
  id_token against the issuer's JWKS (signature, iss, aud, exp, nonce), map groups → role, find-or-create
  the user by verified email, issue our own JWT, redirect to the SPA.
- Local login stays enabled unless `LOCAL_LOGIN_ENABLED=0`, so an IdP outage is survivable.
- Tests use a locally generated RSA key and a stub discovery/JWKS document — no network, no real IdP.

Works with Entra ID, Google Workspace and Okta without change, because all three are plain OIDC.
SAML is explicitly out of scope in v1; if a client demands it, that is a new decision with its own cost.

## 4. Phase C — hardening (fold in as we go)

Session TTL from env; login throttling already exists (slowapi) — extend per-identifier as well as
per-IP; security headers (`X-Frame-Options`, `Referrer-Policy`, HSTS at the proxy); audit CSV export;
a one-page RBAC matrix for the security questionnaire; and password policy on local accounts (zxcvbn ≥3,
reusing the rule we know works, since `Name1!` is not a password).

## 5. What this deliberately does not do

- No per-project ACLs in v1 (roles are global). Enterprise clients will ask; it is a second axis and
  doubling the matrix before anyone has used it is how permission systems become unusable.
- No SCIM provisioning, no just-in-time group sync beyond login time.
- No MFA of our own — that is the IdP's job once SSO is on, and building it locally would be worse.

## 6. Verification gate

Phase A is done when: `pytest backend/tests -q` is green including `test_rbac.py`; the bootstrap admin
still logs in with the `.env` credentials; a viewer receives 403 on a task move; an admin can create a
user who can then log in by email; a deactivated user's live token stops working; and the Plane webhook
still accepts a correctly signed delivery with no token at all.

Each of those is a command, not an opinion — they go in the release note with their output.
