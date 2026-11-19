# BUILD BRIEF — Phase A: local accounts and role-based permissions

You are working in the repository at /root/projects/agentic-pmo (FastAPI + SQLAlchemy + SQLite, Python
3.12, no migration tool). Read `docs/sso-rbac-plan.md` first — sections 0, 1, 2 and 6 are the
specification. Build **Phase A only**. Do not start Phase B (OIDC) or Phase C.

## Hard constraints

1. **Do not alter existing tables.** `Base.metadata.create_all()` runs at startup and creates new
   tables; it will not add columns to existing ones. `User` and `AuditLog` are new tables. Nothing else
   in `models.py` may change except adding relationships if strictly required — prefer none.
2. **Do not add dependencies.** `bcrypt`, `pyjwt`, `fastapi`, `sqlalchemy`, `pydantic` are already in
   `backend/requirements.txt`. If you believe something else is needed, stop and say so instead.
3. **The Plane webhook endpoint keeps its HMAC auth and gains no role dependency.** It has no user.
4. **The existing 106 tests must still pass.** The bootstrap admin must keep working with the
   `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `JWT_SECRET` environment variables exactly as today, so
   `backend/tests/test_api.py::TestAuth` continues to pass unchanged.
5. Match the surrounding code: module docstrings, plain prose comments explaining *why*, no emoji, no
   defensive try/except around things that cannot fail. British spelling in prose.
6. `require_auth` must remain importable with its current signature — many routers depend on it.

## Files to create or change

- `backend/models.py` — append `User` and `AuditLog` exactly as described in plan §A1.
- `backend/auth.py` — rewrite per §A2. Keep `hash_password`/`verify_password` as they are. Keep
  `check_auth_config`/`enforce_auth_config` behaviour for insecure defaults.
- `backend/routers/auth.py` — §A3 (login by identifier, `/me`, change own password).
- `backend/routers/admin.py` — new, §A4 (user CRUD, reset password, audit query).
- `backend/main.py` — include the admin router behind an admin dependency; call `bootstrap_admin()`
  during startup after `init_db()`.
- Router-level role enforcement per §A5 in: `projects.py`, `tasks.py`, `agents.py`, `packs.py`,
  `plane.py`, `dashboard.py`, `templates.py`. Use the router `dependencies=[...]` form where the whole
  router shares a minimum role, and per-handler dependencies where a single write endpoint differs.
- `backend/audit.py` — new: the `audit(...)` helper, one small function.
- `frontend/js/api.js`, `frontend/js/app.js`, `frontend/js/projects.js` — §A7, presentation only.
- `backend/tests/test_rbac.py` — new, covering every case in §A8.

## Auth design details that matter

- JWT claims: `sub` = user id (int as string), `usr` = username, `role`, `ver` = token_version,
  `iss` = "agentic-pmo", `iat`, `exp`. `JWT_SECRET` and HS256 as today.
- `verify_token` must load the user and reject when `is_active` is false or `ver != token_version`.
  Deactivation and password change therefore invalidate live tokens — that is the point.
- `require_role(*roles)` returns a dependency that yields the `User` object, so handlers can audit the
  actor. `require_auth` wraps `require_role(...)` for all four roles and returns the username string, to
  stay compatible with existing handler signatures.
- Login by identifier: try username match first (case-insensitive), then email (case-insensitive).
- Bootstrap: if `users` is empty, insert the `.env` admin as `role="admin"`, `source="local"`. Never
  overwrite an existing user with the env password.
- Roles: `viewer`, `contributor`, `pmo_lead`, `admin`. Validate on write; reject unknown values.
- Refuse to deactivate or demote the last active admin (400 with a clear message).

## Quality bar

- Every denial has a test that asserts the 403, and every allowance has a test that asserts it works.
- The audit table gets a row for: login failure, login success, user create/update/reset/deactivate,
  project create/delete, task delete, agent run. Never store a password, hash or token in `detail`.
- No secrets in logs. No `print()` debugging left behind.
- Docstrings state the rule, e.g. "A token is only valid while its user is active and its version matches."

## When you are done

1. Run `.venv/bin/python -m pytest backend/tests -q` and paste the final summary line.
2. Run `.venv/bin/python -c "import backend.main"` to prove the app still imports.
3. Write `docs/sso-rbac-phaseA-report.md` containing: what you changed file by file, the permission
   matrix as implemented, the list of tests you added, and anything in the plan you could not do — stated
   plainly rather than quietly skipped.

Do not commit. Do not touch `docs/plane-integration.md`. If a requirement above conflicts with the
plan, the constraint list wins; note the conflict in the report.
