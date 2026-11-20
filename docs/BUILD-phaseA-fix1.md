# FIX ROUND — the gstack review's findings, Phase A

Repository: /root/projects/agentic-pmo. The `docs/reviews/phaseA-code-review.md` review (gstack `/review`,
run against `git diff 7d0c7aa..HEAD`) raised eleven findings. Three are `major` and block sign-off; eight
are `minor`. Fix them all except F10, which is deferred on purpose (see the end).

Read the review first, then `backend/auth.py`, `backend/audit.py`, `backend/routers/auth.py`,
`backend/routers/admin.py`, `backend/routers/tasks.py`, `frontend/js/projects.js`, `frontend/js/api.js`.
The 114 tests must still pass, and every fix needs a test that would fail without it.

## Must fix

**F1 — login timing oracle (`backend/auth.py`, `authenticate`).** When the identifier matches nothing, or
matches an inactive user, the function must still run one bcrypt comparison against a fixed dummy hash
before returning `None`, so the response cost does not distinguish "no such account" from "wrong
password". Compute the dummy hash once at import (`_DUMMY_HASH = hash_password(...)` over a fixed
constant string) and do the same when `password_hash` is None. Keep the single generic 401.
Test (deterministic, not timing-based): monkeypatch `backend.auth.verify_password` with a spy, call
`authenticate("no-such-user", "x", db)` and assert the spy was called once; and assert it is called for an
inactive user too.

**F2 — last-admin guard must survive a stale read (`backend/routers/admin.py`).** Today it is a count,
then an unconditional write. Keep the pre-check for the good message, then make the invariant hold at
write time: after applying the role change / deactivation / soft delete but **before commit**, count the
remaining active admins in the same session; if the count is zero, `db.rollback()` and raise the same 400.
Document in a comment that correctness relies on SQLite's serialised writer (the second writer blocks
until the first commits, so its post-write check sees the committed state) and that a Postgres move needs
`SELECT … FOR UPDATE` on the admin rows instead.
Test (deterministic race simulation): monkeypatch `_other_active_admins` to return 1 regardless — a stale
read — then attempt to demote the only admin and assert the response is 400 and the admin is still
`role == "admin"` and active in the database. Do the same for deactivation.

**F3 — the contributor can never save a task from the SPA (`frontend/js/projects.js`).** `_saveTask`
always sends `assignee`, which the server's field rule refuses for a contributor. Send only the fields
that actually changed against the task as loaded; and render the Assignee input only when
`can('manage_projects')`. `actual_hours` and `status` must remain sendable for a contributor.
Test: in `backend/tests/test_rbac.py` add one test that sends exactly the payload the modal would now
send for a contributor (`{"status": ..., "actual_hours": ...}`) and asserts 200 with both applied — and
that the old over-sending payload (`assignee` included) is still 403, so the contract stays explicit.

**F4 — the field-refusal 403 must be audited (`backend/routers/tasks.py`).** The manual 403 for a
refused field bypasses the guard's audit write. Add the `access_denied` row there too, with
`detail={"method": "PATCH", "path": ..., "required_roles": [...], "refused_fields": [...]}` and the same
actor/role/ip shape as the guard. Add a test that the `access_denied` count rises by one after a
field-refusal.

**F5 — never store the raw typed identifier on a failed login (`backend/routers/auth.py`).** Replace
`detail={"identifier": identifier}` with a digest: `detail={"identifier_sha256": sha256(identifier
.lower())[:16], "identifier_len": len(identifier)}` — enough to correlate attempts, useless if a password
was pasted into the username box. Update `test_rbac.py` if it asserts the old key.

**F6 — a password over 72 bytes must be a 422, not a 500 (`backend/auth.py` + the three call sites).**
Add `validate_password(value)` that enforces the 12-character minimum *and* a 72-**byte** ceiling
(`len(value.encode("utf-8"))`), raising `ValueError` with a clear message, and call it from
`routers/auth.py` (own-password change) and `routers/admin.py` (create, reset) converting `ValueError`
to 422. Add a test: an 80-character password returns 422 on create and on reset, and no user is created.

**F7 — the audit cannot say where from (`backend/auth.py`, `backend/routers/auth.py`).** Add a small
`client_ip(request)` helper: return `request.client.host`, but when that address is loopback or private
and `X-Forwarded-For` is present, return the first hop of that header. Use it for the guard's
`access_denied` rows and for `login_success` / `login_failed`. Comment why the trusted-proxy assumption
matters. Add a test that a `login_failed` row carries a non-null `ip`.

**F8 — validate `iss` (`backend/auth.py`, `verify_token`).** Decode with `issuer="agentic-pmo"` and
reject a `sub` that is not a string of digits. Add a test: a token minted with a different `iss` (sign it
with the same secret) is refused with 401.

**F9 — an empty email must not be stored (`backend/routers/admin.py`).** `UserCreate.email` gets
`min_length=3`, and `create_user` strips it before the uniqueness check; a whitespace-only value is a 422.
Add a test.

**F11 — the SPA's role must not go stale (`frontend/js/api.js`, `frontend/js/app.js`).** In
`App.init()`, when a session exists, call `api.me()` and rewrite role and display name in the session
before routing; and on any 403 from `apiRequest`, refresh the session once and re-apply role visibility.
Keep it small: one `refreshSession()` function, called on boot and after a 403.

## Also fix, because the reviewer is right that the spec stopped short

**Project update is unaudited.** Add `"project_updated"` to `ACTIONS` and write a row from
`update_project` with the changed field names (never their values, which can be long prose).

## Defer, with the reason recorded

**F10 — audit tamper-evidence.** Not fixed in this round: a hash chain or an append-only DB role is an
architecture decision that changes the table and the write path, and Phase A's acceptance gate (§6) does
not require it. It goes in the phase report as the first item of Phase C hardening. State this in your
final message rather than silently skipping it.

## Constraints

- No new dependencies. No new tables. No change to the Plane webhook. No commit.
- Do not weaken or delete an existing assertion. New behaviour gets new tests; existing tests only get
  updated where a contract deliberately changed (F5's audit key, F3's payload).
- British spelling, comments that explain why, no emoji.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — paste the summary line (expect more than 114).
2. `.venv/bin/python -c "import backend.main"`.
3. A per-finding table: finding id, what changed, the test that now covers it, and — for F1, F2, F3, F6 —
   the failing-before/passing-after evidence (you may state which assertion would have failed).
4. Anything you could not fix, stated plainly.
