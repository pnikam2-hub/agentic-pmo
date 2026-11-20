# ROUND 1 of 3 — Phase A backend core

You are working in the repository at /root/projects/agentic-pmo (FastAPI + SQLAlchemy + SQLite, Python
3.12, no migration tool).

Read these first, in this order:

1. `docs/sso-rbac-plan.md` — sections 0, 1, 2 and 6 are the specification. Phase A only.
2. `docs/BUILD-PROMPT-round1.md` — the hard constraints and the quality bar. They all still apply.
3. `backend/auth.py`, `backend/models.py`, `backend/main.py`, `backend/routers/auth.py`,
   `backend/routers/projects.py` — the code you are changing and the conventions to match.

## What this round covers, and what it does not

This is round 1 of 3. It builds the **core**: the schema, the auth module, the audit helper, the auth
router, the admin router, and the startup wiring. Nothing else.

- **Round 1 (this one):** §A1, §A2, §A3, §A4, §A6 (the helper only), startup wiring.
- **Round 2:** role enforcement across the existing routers (§A5) and the one-line test-fixture change
  that follows from it.
- **Round 3:** `backend/tests/test_rbac.py` (§A8), the frontend (§A7), and the phase report.

Do not touch the seven existing routers in this round. Do not write `test_rbac.py`. Do not touch the
frontend. Do not touch `docs/plane-integration.md`. Do not commit.

## Deliverables

### 1. `backend/models.py` — append only

`User` and `AuditLog` exactly as specified in plan §A1. Append at the end of the file, after the
existing models, following the file's existing style (section comment banner, `Column(...)` inline).
Nothing above may change. No relationships on existing tables.

Practical notes:

- SQLite has no `citext`, so store `username` and `email` lower-cased on write and query them
  lower-cased. Uniqueness is enforced by a unique index on each column.
- `external_id` is nullable and unique-when-present. SQLite treats `NULL`s as distinct in a unique
  index, which is the behaviour we want for local users.
- `password_hash` is nullable (OIDC users have none). `token_version` defaults to 0. `is_active`
  defaults to true. `role` is a plain `String(20)` with the value validated in `auth.py` — do not use
  `SAEnum` here, because adding a role later must not need a table rewrite.
- `AuditLog.detail` is `JSON`, defaulting to `{}`. `at` defaults to `datetime.datetime.utcnow`, matching
  the rest of the file.

### 2. `backend/audit.py` — new, small

`audit(db, actor, action, target_type=None, target_id=None, detail=None, actor_role=None, ip=None)`:
build the row, `db.add`, and let the caller commit (the request's session owns the transaction). One
module docstring stating the rule — audit records who did what to which object, and never contains a
password, hash or token — and one function. Also expose a module-level tuple `ACTIONS` naming the
actions the codebase may write, so a typo becomes a test failure rather than a silent new action name.

### 3. `backend/auth.py` — rewrite per §A2

Keep, unchanged in behaviour: `hash_password`, `verify_password`, `check_auth_config`,
`enforce_auth_config`, the `security` HTTPBearer instance, the module's env constants, and the
`Optional`/`Depends` import style.

**The one structural decision this round must get right — a single resolution point.**
There must be exactly one function that turns an `Authorization` header into a `User`:

```
current_user(credentials = Depends(security), db: Session = Depends(get_db)) -> User   # raises 401
```

- `require_auth` = `Depends(current_user)`, returns `user.username` (a `str`), same signature as today.
- `require_role(*roles)` returns a dependency defined as `def guard(user: User = Depends(current_user))`,
  which raises 403 when `user.role` is not in `roles` and otherwise returns the `User`.

Why it matters: FastAPI resolves dependency overrides at any depth, so a test that overrides
`current_user` once covers every handler and every role guard. That is what keeps round 2 to a one-line
change in the test fixture instead of a rewrite of 106 tests. Do not inline user resolution into
`require_role`'s closure or into each handler.

Message contracts that existing tests depend on — reproduce them exactly:

- No credentials at all → 401 with detail starting `"Authentication required"` (the test asserts that
  substring).
- Bad, expired, or stale-version token → 401 `"Invalid or expired token. Login again."`
- Wrong role → 403 with a message naming the required role(s) and the caller's role.

Other rules:

- `create_token(user)`: claims `sub` (user id as a string), `usr`, `role`, `ver`, `iss="agentic-pmo"`,
  `iat`, `exp`. HS256, `JWT_SECRET`, expiry from `JWT_EXPIRY_HOURS` (env, default 8).
- `verify_token(token, db) -> Optional[User]`: decode, then load the user by id and return `None` when
  the user is missing, `is_active` is false, or `ver != user.token_version`. A token is only valid
  while its user is.
- `authenticate(identifier, password, db) -> Optional[User]`: look up by lower-cased username first,
  then lower-cased email; refuse inactive users; `verify_password`; set `last_login_at`; return the user.
- `bootstrap_admin(db)`: if the `users` table is empty, insert the `.env` admin as
  `role="admin"`, `source="local"`, with `hash_password(ADMIN_PASSWORD)`. Idempotent; never overwrite an
  existing user. Return the created user or `None`.
- **`authenticate` must also work in a process that never ran the startup hook.** The test suite builds
  the app's tables with `Base.metadata.create_all()` and never runs startup events, so the bootstrap
  admin would not exist and every login test would fail. Resolve it inside `authenticate`: if the lookup
  by identifier finds nothing *and* the users table is empty, call `bootstrap_admin(db)` and retry once.
  Say why in the docstring — the env admin must stay usable in any process that does not run startup
  (tests, embedded ASGI, a CLI), and bootstrapping is idempotent by construction.
- `ROLES = ("viewer", "contributor", "pmo_lead", "admin")` and a `validate_role(value)` that raises
  `ValueError` on anything else. Cumulative order is the tuple order — use it, do not hard-code
  comparisons like `role >= "contributor"`.
- Keep a module-level `_stored_hash` only if you still need it; if it becomes unused, remove it rather
  than leave dead code.

### 4. `backend/routers/auth.py` — §A3

- `POST /api/auth/login` accepts `identifier` **or** `username` (both optional in the schema, at least
  one required, `identifier` wins) plus `password`. Response keeps `token` and `token_type="bearer"`
  and adds `role`, `display_name`, `expires_at`. Keep the `@limiter.limit(LOGIN_RATE_LIMIT)` decorator
  and the `request: Request` parameter it needs. 401 on failure with `"Invalid username or password"`,
  and write an audit row (`action="login_failed"`, actor `"anonymous"`, the identifier in `detail` —
  the identifier is not a secret).
- `GET /api/auth/verify` — keep exactly as it is; a test asserts the body `{"user": "admin", "ok": true}`.
- `GET /api/auth/me` — the current user: id, username, email, display_name, role, source, and a
  `permissions` list derived from the role (a simple mapping, not a permissions engine).
- `POST /api/auth/password` — change own password; body has `old_password` and `new_password`; verify
  the old one (401 if wrong), reject a new password under 12 characters, bump `token_version` so every
  other live token dies, audit the change. Never put either password in the audit detail.

### 5. `backend/routers/admin.py` — new, §A4

Router prefix `/api/admin`, every route `Depends(require_role("admin"))`.

- `GET /users` — list, with role, source, is_active, last_login_at.
- `POST /users` — create a local user: username, email, display_name, role, password. Validate the
  role with `validate_role`. Reject a duplicate username or email with 409. Audit.
- `PATCH /users/{id}` — role, is_active, display_name. Refuse to demote or deactivate the last active
  admin (400, message says why). Bump `token_version` when the role changes or the user is deactivated,
  so live tokens cannot outlive the change. Audit.
- `POST /users/{id}/password` — admin reset, no old password needed, minimum 12 characters, bumps
  `token_version`. Audit. Never log or audit the value.
- `DELETE /users/{id}` — soft delete (`is_active = false`), refuse the last active admin.
- `GET /audit?limit=&actor=&action=` — newest first, default limit 100, max 500.

Return the `User` without `password_hash` — a Pydantic model with an explicit field list, not
`model_config = {"from_attributes": True}` over the whole row.

### 6. `backend/main.py`

- Import and include the admin router.
- Call `bootstrap_admin(...)` during startup **after** `init_db()`, with a session from `SessionLocal`.
- Leave the existing `dependencies=[Depends(require_auth)]` on the seven routers exactly as they are —
  they get their role boundaries in round 2. This is what keeps the present suite green today.
- Do not add emoji or change the existing startup prints.

### 7. `backend/tests/conftest.py` — one addition

Pin `DATABASE_URL` to a scratch file (`sqlite:///./.pytest-scratch.db`) with `os.environ.setdefault`,
alongside the other pins, for a concrete reason: `test_plane_webhook.py` enters `TestClient(app)` as a
context manager, which runs startup — so `init_db()` and `bootstrap_admin()` execute against whatever
`DATABASE_URL` points at. Without the pin, running the suite would write a `users` row with the *test*
password into the demo database `agentic_pmo.db`, and since bootstrap never overwrites, the real
`.env` admin would then be locked out of the demo instance. Add a one-line comment saying exactly that.

## Hard constraints (repeat of the ones most likely to bite)

- No new dependencies. No new tables beyond `User` and `AuditLog`.
- Do not alter an existing table or an existing column. `create_all()` cannot migrate.
- Do not modify any test other than the conftest `DATABASE_URL` line above.
- The Plane webhook endpoint gains no role dependency, now or later.
- British spelling in prose, module docstrings, comments that explain *why*, no emoji, no `print()`
  debugging, no defensive `try/except` around code that cannot fail.

## When you are done

1. Run `.venv/bin/python -m pytest backend/tests -q` and paste the final summary line. **106 tests must
   still pass.** If any fail, fix your code — not the tests.
2. Run `.venv/bin/python -c "import backend.main"` and paste the output.
3. Report back in your final message: files changed, the exact `current_user` / `require_auth` /
   `require_role` definitions, the JWT claim list, and anything in the plan you could not do — stated
   plainly rather than quietly skipped. Do not write a report file; round 3 produces the report.
