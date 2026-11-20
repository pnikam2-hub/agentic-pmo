# Phase C round C2 report — login throttling, password policy, response headers

Status: **complete and verified** on 20 November 2026. Scope was the three hardening items that a
security questionnaire asks about after Phase A/B: per-identifier login throttling, a real password
policy, and response security headers. Nothing else was changed — no existing table column was
altered and no Phase A/B behaviour changed beyond the two policies below.

## 1. What changed

| File | Change |
|---|---|
| `backend/auth.py` | `identifier_digest()` (one place that turns a normalised identifier into the 16-hex digest); `login_failures_in_window()` and `login_throttled()` (the per-identifier counter, on the audit trail); `validate_password()` now also requires a zxcvbn score ≥ 3 on top of the 12-character floor and 72-byte ceiling, and raises zxcvbn's own feedback as the message; new config `LOGIN_FAILURE_LIMIT` / `LOGIN_FAILURE_WINDOW_MINUTES` / `ZXCVBN_MIN_SCORE`. |
| `backend/audit.py` | Added `login_throttled` to the `ACTIONS` allow-list. |
| `backend/routers/auth.py` | Login now checks the per-identifier throttle after the identifier is normalised and before `authenticate` (so a locked identifier costs no bcrypt), refuses with **429** + `Retry-After`, and writes a `login_throttled` audit row carrying the digest only. The `login_failed` row reuses `identifier_digest()` so the counter and the trail can never disagree. |
| `backend/main.py` | One `security_headers` middleware setting the headers below on every response. |
| `backend/requirements.txt` | `zxcvbn>=4.4.28` (pure Python, no native build). |
| `.env.example` | Documented the two new throttle knobs. |
| `backend/tests/conftest.py` | Pinned `LOGIN_FAILURE_LIMIT` / `LOGIN_FAILURE_WINDOW_MINUTES` so the suite is deterministic. |
| `backend/tests/test_hardening.py` | **New** — 12 tests: 3 throttling, 6 password policy, 3 headers. |

## 2. Per-identifier login throttling

- **Config**: `LOGIN_FAILURE_LIMIT` (default **5**) and `LOGIN_FAILURE_WINDOW_MINUTES` (default
  **15**), both read at import time like the rest of `backend/auth.py`.
- **What is counted**: `login_failed` rows whose `detail.identifier_sha256` equals the digest of the
  identifier being tried. The digest is the same 16-hex truncation the audit trail already stores, so
  the counter survives a restart (it is on the audit trail) and needs no shared store.
- **Query strategy — and why**. `AuditLog.at` is **not** indexed. I did **not** add an index on
  `(action, at)`: it would be a new index on a live table, which `create_all()` will not create for an
  existing database, so the code could never rely on it being there. Instead the query filters by
  `action == "login_failed"` — which **is** indexed — and applies the window in SQL (`at >= cutoff`),
  then matches the digest in Python, because the digest lives inside the JSON `detail` column, which
  SQLite cannot index on meaningfully anyway. The scan is therefore bounded by the `action` index, not
  a full table scan.
- **Order**: the check runs before the password is verified (no bcrypt for a locked identifier) and
  after the identifier is normalised (so `victim`, `VICTIM` and `victim@example.com` fall into the
  same digest for the username/email they resolve to).
- **Refusal**: `429` with `Retry-After: <seconds-until-release>`, plus a `login_throttled` audit row
  (`actor="anonymous"`, `detail` carrying the digest only — never the identifier). `Retry-After` is
  computed as the moment the `LIMIT`-th most recent failure ages out of the window.
- **Trade-off, documented in the code**: because the counter is keyed on the identifier digest, an
  attacker who knows a username can deliberately lock that account out for the window. That is why the
  existing per-IP slowapi limit stays in place and why the window is short — the two limits together
  make a distributed lockout expensive while still stopping a targeted brute force.
- **Release**: a successful login clears the count by construction — only failures are counted and the
  window is time-bounded, so nothing needs an explicit reset.

## 3. Password policy

- `validate_password` now enforces, in order: ≥ **12 characters**, ≤ **72 bytes** (bcrypt ceiling),
  and **zxcvbn score ≥ 3**. zxcvbn is additional, not a replacement.
- The rejection message is zxcvbn's own short feedback (the `warning`, falling back to the first
  `suggestion`, then a bare score) — for example "This is similar to a commonly used password" — never
  a bare "too weak".
- Applied everywhere a password is set: user creation, admin reset, and own-password change all call
  `validate_password`.
- The password, its score inputs, and the guess list are never logged or audited — the message carries
  only zxcvbn's fixed vocabulary, not the input.
- `Password1!` (the example the plan calls out) is ten characters, so the length floor catches it
  before zxcvbn runs; it is still refused, and a length-valid but weak password (`password12345`) is
  refused with zxcvbn's own words — both covered by tests.

## 4. Response headers

One middleware in `backend/main.py` sets, on every response:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` | `no-store` on `/api/` responses only — never on static assets |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, only when HTTPS is in play |

- HSTS reuses `backend.auth.is_https` rather than `request.url.scheme`, so a TLS-terminating reverse
  proxy is honoured exactly the same way the SSO cookie already is (trusted peer + `X-Forwarded-Proto`).
- **No `Content-Security-Policy`**, deliberately: the SPA uses inline event handlers throughout, and a
  policy worth having needs the frontend rewritten first. The decision is recorded in a comment in the
  middleware so it reads as a choice, not an omission.

## 5. Verification

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest backend/tests -q` | **187 passed** (175 prior + 12 new) |
| `backend/tests/test_hardening.py` | 12 passed |
| Curl demo, spare port 8765 | five 401s then a 429 with `Retry-After: 899` and the security headers; `/api/health` carries the five static headers + `no-store` and no HSTS; adding `X-Forwarded-Proto: https` from the loopback peer adds HSTS |

## 6. Notes

- One early full-suite run reported a transient failure in
  `test_rbac.py::test_admin_surface_and_project_deletion` (a test that does not touch the new paths);
  it did not reproduce in three subsequent full runs and does not reproduce in isolation. Treated as
  pre-existing flake in the shared `app.dependency_overrides` fixture dance across test modules, not as
  a regression from this round.
- The audit-query index trade-off (no `(action, at)` index) is the only thing this round decided
  *against*; it is stated above rather than left to be rediscovered.
