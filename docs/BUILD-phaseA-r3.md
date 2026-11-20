# ROUND 3 of 4 — the RBAC test suite, and one small gap it exposes

Repository: /root/projects/agentic-pmo. Phase A rounds 1 and 2 are committed and green: `users` and
`audit_logs` tables, `current_user` / `require_auth` / `require_role` plus the shared guards `any_role`,
`contributor_up`, `pmo_lead_up`, `admin_only` in `backend/auth.py`, the admin surface, and role gates on
every router with audit rows for the writes plan §A6 names. 106 tests pass.

Read before starting: `docs/sso-rbac-plan.md` §A6 and §A8, `docs/BUILD-prompt-round1.md` for the house
constraints, `backend/auth.py`, `backend/audit.py`, `backend/routers/admin.py`, and
`backend/tests/test_api.py` (for the in-memory-engine and override conventions).

## 1. One backend change: denials must be visible in the audit trail (§A8, last bullet)

A 403 that leaves no trace is the thing a security review asks about first — "who tried, and from
where". Today the guard raises a 403 and writes nothing.

In `backend/auth.py`, `require_role`'s returned `guard` must, **when it refuses**, append and commit an
audit row before raising, and then raise as it does now:

- add `request: Request` and `db: Session = Depends(get_db)` to the guard's signature;
- action `access_denied` — add it to `ACTIONS` in `backend/audit.py`;
- `detail={"method": request.method, "path": request.url.path, "required_roles": list(allowed)}`,
  `actor=user.username`, `actor_role=user.role`;
- `ip` from `request.client.host` when a client is present, else `None`;
- the 403 message stays exactly as it is (it already names the required roles and the caller's role).

Keep this in the guard, not in each router: one place, so no route can forget. Do not audit the 401 path
(there is no user to name) — a failed login is already audited by the auth router.

## 2. `backend/tests/test_rbac.py` — new file, the acceptance suite for Phase A

This file is the release gate. It must exercise the **real** dependency chain (real JWTs, real
`current_user`, real guards) — do not override `current_user` here, that is what `test_api.py` does for
its own convenience.

Shape:

- its own in-memory engine + `SessionLocal` equivalent, `app.dependency_overrides[get_db]` for the
  module, and `Base.metadata.create_all()` / `drop_all()` around each test;
- a module-level `TestClient(app)` (no context manager: startup must not run, so the database the tests
  use is the only one touched);
- a fixture that, per test, creates the tables, calls `bootstrap_admin(...)` and then creates one
  `viewer`, one `contributor` and one `pmo_lead` through the admin API or directly, and returns a dict of
  ready-to-use `Authorization` headers obtained by **logging in over HTTP**;
- helper assertions that read a response body into the failure message, so a wrong status shows the
  server's own `detail`.

Cases, one test each, named for the rule:

1. `bootstrap_admin` creates exactly one user on an empty table; calling it again creates nothing.
2. login by username works; login by email works; wrong password is 401; an inactive user is 401 with the
   same message as a wrong password (no account enumeration).
3. a token whose `ver` is stale is refused (bump `token_version` directly, then use the old token → 401);
   deactivating a user kills their live token (401) and they cannot log in again.
4. viewer cannot move a task (403) but contributor can (200); contributor cannot create a project (403)
   but pmo_lead can (200); contributor may set `status` and `actual_hours` and is refused on any other
   field (403, and the task is unchanged afterwards).
5. only admin reaches `/api/admin/users` and `/api/admin/audit` (viewer/contributor/pmo_lead → 403);
   a pmo_lead cannot delete a project (403) while an admin can (200).
6. the last active admin cannot be demoted, deactivated or deleted (400 on all three); with a second
   admin present, the first can be demoted.
7. audit: a failed login writes `login_failed`; a role-denied write writes `access_denied` with the path
   and the caller's role; the audit detail of every row produced by these tests contains no password, no
   bcrypt hash and no token.
8. the Plane webhook accepts a correctly signed delivery with no JWT at all (reuse the signing helper
   from `test_plane_webhook.py`, monkeypatch `PLANE_WEBHOOK_SECRET`), and a bad signature is 401.

Do not duplicate `test_api.py` coverage of CRUD; assert roles, tokens, denials and audit, and leave
business-logic correctness to the existing suite.

## 3. Constraints

- The 106 existing tests must still pass, unchanged. Do not edit any other test file.
- No new dependencies. No new tables. No frontend work. No commit.
- British spelling, docstrings that state the rule, no emoji, no `print()` left behind.
- If a case above cannot pass against the current implementation, do not weaken the test: fix the
  implementation, and say in your report what you changed and why.

## 4. When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — paste the summary line. Expect more than 106.
2. `.venv/bin/python -m pytest backend/tests/test_rbac.py -q` — paste that line too.
3. `.venv/bin/python -c "import backend.main"`.
4. Report: the number of tests added, the cases you could not implement and why, every file changed, and
   any place the plan and the code disagreed. Do not write a report file.
