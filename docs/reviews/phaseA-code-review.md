# Phase A code review — authentication and role-based permissions

Reviewed range: `git diff 7d0c7aa..HEAD` (four commits — round 1 core, round 2 enforcement,
round 3 test gate + denial auditing, round 4 SPA). Governing docs: `docs/sso-rbac-plan.md`,
`docs/BUILD-phaseA-r1..r4.md`. Review method: full read of every changed file plus the untouched
webhook path, the full 114-test suite, and targeted runtime probes against a throwaway SQLite DB.

## 1. Verdict

**Not yet — not fit to put in front of an enterprise security review, for two specific reasons.**
The core of the change is genuinely sound — the four-role matrix is enforced at the router and
handler boundary through a single `current_user` resolution point, the effective role is re-read from
the database on every request rather than trusted from the JWT, and `token_version` + `is_active`
checks really do kill live tokens on password change, role change and deactivation (the 114-test gate
passes and `test_rbac.py` drives the real dependency chain). But two defects sit squarely on the
"review exists to catch this" line. First, login is a **confirmed enumeration oracle**: `authenticate`
runs bcrypt only when the identifier names a real, active account, so a nonexistent or disabled
identifier returns in ~10 ms while a wrong password for a real account returns in ~324 ms — a 32×
difference I measured directly. Second, the **last-active-admin guard is a non-atomic check-then-write**:
two concurrent demotions/deactivations can each see the other admin as "still active" and both commit,
leaving the tenant with zero admins and no bootstrap back (bootstrap only runs against an empty
`users` table). Everything else below is fixable polish, audit-completeness, or a broken contributor
workflow — important, but not what decides the verdict.

## 2. Findings table

| ID | Severity | file:line | Summary |
|---|---|---|---|
| F1 | major | `backend/auth.py:141-143` | Login is a 32× timing oracle that enumerates usernames/emails despite equal 401 text |
| F2 | major | `backend/routers/admin.py:143-145, 205-206` | Last-admin guard is a non-atomic read-then-write; concurrent requests can remove the final admin |
| F3 | major | `frontend/js/projects.js:381-395` (× `backend/routers/tasks.py:67-79`) | Contributor can never save a task from the SPA — the modal always submits `assignee`, which the field rule always refuses |
| F4 | minor | `backend/routers/tasks.py:72-79` | The contributor field-refusal 403 writes no `access_denied` row, breaking the "every 403 leaves a trace" rule |
| F5 | minor | `backend/routers/auth.py:79-80` | `login_failed` records the raw typed identifier, which a botched paste turns into a plaintext secret in the audit log |
| F6 | minor | `backend/auth.py:74-75` (callers `admin.py:99-100,184-186`, `routers/auth.py:125-127`) | Passwords over 72 bytes raise an unhandled `ValueError` → HTTP 500 instead of a 422 |
| F7 | minor | `backend/auth.py:261` | Audit `ip` is the reverse-proxy address; `X-Forwarded-For` is never honoured |
| F8 | minor | `backend/auth.py:151-170, 182` | The `iss="agentic-pmo"` claim is minted but never validated, so any token signed with the same `JWT_SECRET` is accepted |
| F9 | minor | `backend/routers/admin.py:39, 102-106` | `email` accepts the empty string, producing accounts that can only log in by username |
| F10 | minor | `backend/models.py:260-276` | The audit trail is an ordinary mutable table — no append-only or tamper-evidence protection |
| F11 | minor | `frontend/js/api.js:17-21` | SPA role is frozen at login and never refreshed, so a demoted user keeps seeing stale buttons until re-login |

## 3. Findings in full

### F1 — Login timing / enumeration oracle (major)

**What it is.** `authenticate()` (`backend/auth.py:123-147`) looks up the identifier, then at line 141
returns `None` immediately when the identifier matches nothing or the account is inactive, and only
reaches the bcrypt `verify_password` at line 143 when the account is real and active. The login route
(`backend/routers/auth.py:69-92`) returns the *same* 401 text for all three cases, so the message does
not distinguish them — but the time does: a wrong password for a real account costs a bcrypt hash
(~320 ms at the default cost factor), while a nonexistent or disabled identifier costs ~10 ms.

**How it fails.** An attacker who can reach the login endpoint (it is rate-limited per-IP at
`5/minute`, which slows but does not stop a distributed or patient enumerator) can, for any candidate
username or email, tell "account exists and is active" from "no such account / inactive" by timing a
single request. This is exactly the enumeration the round-3 spec claims to have removed ("same 401 so
the response does not reveal whether the account exists", `test_rbac.py:149-165`) — the test only
asserts message equality, not timing equality, so it passes while the oracle remains.

**Fix.** Always do a dummy `bcrypt.checkpw` against a fixed synthetic hash when the identifier is
unknown or inactive (and still return the generic 401). This normalises the cost across all three
cases; the dummy hash needs to be a precomputed bcrypt hash of a fixed string so the work factor
matches.

**Verified.** Yes — measured directly: 10 samples each, nonexistent identifier median 10.1 ms vs
existing-wrong-password median 323.9 ms (ratio 32×) via `TestClient` against an in-memory DB.

### F2 — Last-admin guard is a non-atomic check-then-write (major)

**What it is.** `update_user` (`backend/routers/admin.py:141-145`) and `delete_user`
(`:205-206`) guard the demote/deactivate of an admin by calling `_other_active_admins()` (`:76-79`),
a plain `SELECT count(*)`, and then unconditionally applying the mutation and committing. There is no
lock, no `SELECT … FOR UPDATE` analogue, and no single conditional `UPDATE` — the count and the write
are separate statements in separate transactions.

**How it fails.** Two admins, A and B, are both active. Two concurrent requests — one demoting A, one
demoting B — each run `_other_active_admins` and each see `count == 1` (the other one) before either
commits. Both pass the guard, both commit. The tenant now has zero admins: nobody can reach
`/api/admin/*`, and `bootstrap_admin` cannot restore the situation because it refuses to run against a
non-empty `users` table (`backend/auth.py:98-99`). Recovery requires direct database surgery. The same
interleaving deactivates or deletes the last admin. This is the classic TOCTOU the guard is
specifically meant to prevent.

**Fix.** Make the check and the write atomic — e.g. perform the demote/deactivate as a single
`UPDATE users SET … WHERE id = :id AND NOT EXISTS (SELECT 1 FROM users WHERE role='admin' AND
is_active=1 AND id != :id)`, and check `rowcount`; or serialise user-mutation writes through an
application-level lock. SQLite's serialised writer does not save you here because the *read* (count)
is the stale value.

**Verified.** Reasoned from the code path (count at `:76-79`, unconditional write at `:150-163`
/ `:207-211`); not reproduced under concurrent load — a deterministic reproduction needs two
interleaved sessions and is inherently racy, but the absence of any atomicity construct makes the
window structural rather than incidental.

### F3 — Contributor cannot save a task through the SPA (major)

**What it is.** The contributor field rule (`backend/routers/tasks.py:67-79`) refuses any PATCH whose
body contains a field other than `status` and `actual_hours`. The SPA's task editor
(`frontend/js/projects.js:381-395`) builds its payload as
`{ status, assignee, actual_hours }` unconditionally — `assignee` is always present, even when the
user did not touch it.

**How it fails.** Every save by a contributor through the edit modal carries `assignee`, so the server
always answers 403 "Fields refused: assignee" (`tasks.py:72-79`). The contributor's two §1
capabilities — "move a task between statuses" and "log actual hours" — are therefore unreachable via
the modal (the only UI surface for hours). Dragging a card still works, because `dropTask` sends only
`{ status }` (`projects.js:410-417`), so status moves have a workaround; logging hours has none. The
backend is correct; the client defeats it. This also silently contradicts the round-4 rule "the SPA
hides what the caller cannot use": the modal renders an Assignee field to contributors who can never
submit it.

**Fix.** In `_saveTask`, send only fields that differ from the loaded task, or omit `assignee` for
roles that cannot submit it; and render the Assignee input only when `can('manage_projects')`.

**Verified.** Yes — a `PATCH /api/projects/{pid}/tasks/{tid}` with
`{"status":"done","assignee":"bob","actual_hours":1.0}` as a contributor returned 403 "Fields
refused: assignee" (matches the exact body the modal produces).

### F4 — Field-refusal 403 leaves no audit trace (minor)

**What it is.** The denial-auditing guarantee ("kept here, in one place, so no route can forget",
`backend/auth.py:245-263`) lives inside `require_role`'s guard. The contributor field refusal in
`update_task` (`backend/routers/tasks.py:72-79`) is a *manual* `raise HTTPException(403, …)` executed
after the `contributor_up` guard has already passed, so it bypasses that audit write entirely.

**How it fails.** A contributor probing another task field (title, priority, dependencies) gets a 403
with no `access_denied` row — the precise "who tried, and from where" question a security review asks
first goes unanswered for a whole class of role denial. Contrast: a contributor POSTing a project hits
the `pmo_lead_up` guard and *does* produce an `access_denied` row. The two adjacent denials behave
differently with no stated reason.

**Fix.** Route the field refusal through the same audit call (`audit(..., action="access_denied",
detail={... "refused_fields": refused})`) before raising, or refactor the field check into a guard the
route depends on.

**Verified.** Yes — after a field-refusal 403 the count of `access_denied` rows did not change
(delta 0), while a guard-level 403 in the same run added exactly one.

### F5 — `login_failed` records the raw typed identifier (minor)

**What it is.** `backend/routers/auth.py:79-80` writes `detail={"identifier": identifier}` for every
failed login, where `identifier` is the caller's raw input string.

**How it fails.** The spec's justification ("the identifier is not a secret") assumes the caller typed
a username or email. The field is unconstrained: a user who pastes their password into the username
box (a common autofill/typo failure) has that password persisted in plaintext in `audit_logs.detail`,
visible to every admin who opens the audit screen (`backend/routers/admin.py:215-229`), forever. An
audit trail whose own invariant is "never contains a secret" (`backend/audit.py:3-4`) can be broken by
a single fat-fingered login.

**Fix.** Do not store the raw identifier on failure — record a salted hash of it (still lets a
defender correlate the actor) or nothing; the row's purpose is "a login failed from this IP", not
"this exact string was typed". The `ip` should be recorded at the same time (see F7).

**Verified.** Code-read; the behaviour is visible in the audit rows produced by `test_rbac.py`
(`login_failed` with `detail.identifier`).

### F6 — Passwords over 72 bytes → unhandled 500 (minor)

**What it is.** `hash_password` raises `ValueError` for inputs over bcrypt's 72-byte limit
(`backend/auth.py:74-75`), but every caller only enforces a 12-character minimum
(`backend/routers/admin.py:99-100`, `:184-186`, `backend/routers/auth.py:125-127`). There is no
72-byte ceiling and no `try/except` converting the `ValueError` into a 4xx.

**How it fails.** An admin creating a user, resetting a password, or a user changing their own
password with a long passphrase (≥73 ASCII bytes, or far fewer multibyte characters) hits an unhandled
`ValueError` and the request dies with HTTP 500. Nothing is bypassed and nothing is written, but the
API fails in an unpolished, alarming way on a legitimate input.

**Fix.** Reject with 422 "Password must be at most 72 bytes" before hashing (measure `len(pw.encode())`),
and share that validation across the three call sites.

**Verified.** Yes — creating a user with an 80-char password and resetting to an 80-char password both
returned HTTP 500 (with `raise_server_exceptions=False`).

### F7 — Audit `ip` is the proxy address (minor)

**What it is.** The denial audit stores `request.client.host` directly (`backend/auth.py:261`). The
login success/failure rows store no `ip` at all. The deployment note in `backend/rate_limit.py:7-11`
already concedes that `get_remote_address()` sees the reverse-proxy's address; the audit writer
inherits the same blind spot without the acknowledgement.

**How it fails.** Behind nginx/traefik (the documented deployment), every `access_denied` row records
the proxy's IP, and logins record none — so the audit trail cannot answer "from where" for the two
events a security reviewer cares about most. Not a privilege issue, but a direct erosion of the
audit's evidential value.

**Fix.** Honour `X-Forwarded-For` only when `request.client` is a trusted proxy (mirroring the
`--proxy-headers` caveat), and populate `ip` on the `login_success`/`login_failed` rows too.

**Verified.** Code-read; not runtime-verified.

### F8 — `iss` claim minted but never validated (minor)

**What it is.** `create_token` stamps `iss="agentic-pmo"` (`backend/auth.py:167`) but
`verify_token` decodes with `pyjwt.decode(token, JWT_SECRET, algorithms=[...])` (`:182`) and never
checks `iss` (or `aud`).

**How it fails.** Any JWT signed with the same `JWT_SECRET` whose `sub` is a valid user id and whose
`ver` happens to match is accepted as that user — even a token minted for an unrelated purpose or
issuer sharing the secret. In practice this is mitigated by the secret being per-deployment and
fail-closed on the default (`backend/auth.py:53-68`), so the severity is low — but the claim is
advertising a boundary that is not enforced.

**Fix.** `pyjwt.decode(..., issuer="agentic-pmo")` (and validate `sub` is a non-empty string of digits
before `int()`).

**Verified.** Code-read; not runtime-verified.

### F9 — Empty-string email accepted (minor)

**What it is.** `UserCreate.email` is `str = Field(..., max_length=255)` with no `min_length`
(`backend/routers/admin.py:39`), and `create_user` lowercases and stores it verbatim (`:103`).

**How it fails.** An admin can create a user with `email=""`; a second such user collides on the
unique index and gets a misleading 409. Such an account can never log in by email (the login route
rejects an empty identifier at `routers/auth.py:73`), so the field silently lies about being usable.
Data-quality rather than security, but it is the kind of edge a reviewer pokes at.

**Fix.** `min_length=1`, or coerce `""` to `None` before the uniqueness check.

**Verified.** Code-read; not runtime-verified.

### F10 — Audit trail has no append-only or tamper-evidence protection (minor)

**What it is.** `AuditLog` (`backend/models.py:260-276`) is an ordinary table written with the same
session that performs the audited action. Nothing — no in-app API, but also no DB-level guard —
prevents an audit row from being altered or deleted after the fact, and no hash-chaining makes
tampering detectable.

**How it fails.** The audit trail's entire purpose is "an authoritative record of who did what"
(`backend/audit.py:1-5`). Today that authority rests on good behaviour: any actor with direct
database access (a backup restore, a support query, or a future write path) can silently edit or
delete rows, and the readers cannot tell. The spec does not require tamper-evidence (§A6 stops at
"write rows and never store secrets"), so this is hardening rather than a spec breach — but it is
exactly the audit-integrity question an enterprise review asks next.

**Fix.** At minimum: document the trust model; ideally, hash-chain rows (each row carries the hash of
its predecessor) or restrict the DB role to append-only. Either is a later phase, but the limitation
should be stated.

**Verified.** Code-read; not runtime-verified.

### F11 — SPA role is frozen at login and never refreshed (minor)

**What it is.** `setSession` writes `role` to `localStorage` once at login
(`frontend/js/api.js:17-21`) and `can()` reads only that value. The `/me` endpoint that could refresh
it (`backend/routers/auth.py:101-112`) is called by `AdminView` but its result is never written back
to the session.

**How it fails.** If an admin demotes or deactivates a user mid-session, the SPA keeps rendering the
buttons for the old, higher role until the next login (or the next 401). This is presentation-only and
the server refuses every underlying call, so it is not a security hole — but it is the "UI that lies
about what it can do" state the round-4 rule set out to prevent (`frontend/js/api.js:50-79`), and it
reappears the moment a role changes behind a live session.

**Fix.** Refresh `getRole()`/`getDisplayName()` from `api.me()` after login and periodically (or on
any 403), or drop the local copy and derive visibility from `me()`.

**Verified.** Code-read; not runtime-verified.

## 4. What the change gets right

- **A single resolution point, honoured everywhere.** `current_user` (`backend/auth.py:198-219`) is
  the only function that turns a bearer token into a `User`; every guard (`require_auth`,
  `require_role`) and every `actor: User = Depends(...)` resolves through it. The round-1 structural
  bet paid off: one `current_user` override in `test_api.py` covers the whole app, and `test_rbac.py`
  is able to exercise the real chain without fakes.
- **The token's `role` claim is decorative; the database is authoritative.** `verify_token`
  (`auth.py:173-191`) re-loads the user and re-checks `is_active` and `token_version` on every
  request, and the guards take the role from that loaded `User`, not from the JWT. A stale or forged
  role claim cannot escalate anything.
- **Revocation actually works.** Bumping `token_version` (password change, role change, deactivation)
  kills every outstanding token immediately, and deactivation also blocks login and in-flight token
  use — all covered by `test_rbac.py:168-191`. This is the correct, simple revocation model for a
  no-refresh-token v1.
- **Fail-closed startup.** `enforce_auth_config` (`auth.py:53-68`) refuses to boot on the default
  `ADMIN_PASSWORD`/`JWT_SECRET` unless `ALLOW_INSECURE_DEFAULTS=1`, and `_check_env` warns.
- **The webhook stayed outside the role system.** `plane_webhook.router` is included with no auth
  dependency (`backend/main.py:62-63`), authenticates by HMAC with a constant-time
  `hmac.compare_digest` (`backend/integrations/plane/webhook.py:51`), fails closed when the secret is
  missing (`routers/plane_webhook.py:27-30`), and is proven token-less by
  `test_rbac.py:321-329`. The "must never gain a role dependency" constraint is respected.
- **401 vs 403 are correctly separated.** No/invalid/stale token → 401 (`auth.py:208-219`); valid
  token, wrong role → 403 naming the required roles and the caller's role (`auth.py:245-270`). The
  message contracts the old tests depend on are reproduced exactly.
- **No write route is under-gated.** Every POST/PATCH/DELETE across projects, tasks, agents,
  templates, packs, plane and alerts carries a `pmo_lead_up`/`contributor_up`/`admin_only` guard; the
  only any-role writes are self-service (`/auth/password`).
- **Audit never commits secrets by construction.** `audit()` rejects action names outside an
  allow-list (`audit.py:13-29, 44-46`), `UserOut` uses an explicit field list so `password_hash`
  cannot serialise (`admin.py:21-34`), and `test_rbac.py:309-318` asserts no password, bcrypt hash or
  JWT appears in any row's `detail`.
- **Bootstrap is genuinely idempotent.** Empty-table-only (`auth.py:98-99`), so a restart never
  overwrites an existing account with the env password, and the conftest `DATABASE_URL` pin prevents
  the test suite from locking out the real demo admin (`conftest.py:18-19`).
- **The 114-test gate passes** (`114 passed`), including the eight acceptance cases in `test_rbac.py`.

## 5. What the specification asks for that is missing

Nothing in §A1–§A8 is missing outright: both tables exist, the auth rewrite is complete, login/me/
password endpoints exist, the admin surface is gated and feature-complete, every router carries its
gate, the §A6 audit call sites are all present, the SPA hides per `data-requires`, and all eight §A8
acceptance tests exist and pass. The gaps below are either deliberate exclusions to restate, or
natural next-hardening the spec does not yet ask for:

- **Project `PATCH` is unaudited.** §A6 names "project create/delete" but not update, and
  `update_project` (`backend/routers/projects.py:71-89`) writes no row. A security reviewer will ask
  why a change to a project's goal/status is not a "security-relevant action" when task delete is.
  This is a spec gap, not an implementation omission.
- **Login rows carry no `ip`.** Only `access_denied` records `ip` (round-3 requirement); the
  `login_success`/`login_failed` rows (`routers/auth.py:83-85`) omit it even though the audit helper
  supports it. See F7.
- **No tamper-evidence / append-only on the audit log** (F10) — not required by §A6, but the next
  question an enterprise review asks.
- **No token `jti` or refresh/revocation list.** Replay of a stolen bearer token within the 8-hour
  window is possible; the mitigations are `token_version` (coarse, kills *all* of a user's tokens),
  role-from-DB, and the 8-hour expiry. The plan accepts this for v1 and does not list it as missing,
  but it is worth stating in the release note.
- **Phase C hardening is deferred by design**, not missing: per-identifier throttling (only per-IP
  `5/minute` today), zxcvbn password policy (only length ≥12 today), security headers, audit CSV
  export. These are explicitly out of Phase A scope (`docs/sso-rbac-plan.md` §4).

## Constraints checked (no "fix away")

- No new dependencies, no new tables beyond `users`/`audit_logs`; `create_all` only — held.
- Four global roles, no per-project ACLs/SCIM/local MFA — held.
- Plane webhook stays HMAC-only with no role dependency — held (`main.py:62-63`, `plane_webhook.py`).
- 114 existing tests pass; no assertion was deleted or weakened (the only test edits are the fixture
  stand-ins and the `actor=` argument added to three direct handler calls) — held.
