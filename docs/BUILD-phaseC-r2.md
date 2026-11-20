# PHASE C round C2 — throttling, password policy, response headers

Repository: /root/projects/agentic-pmo at 0.2.0+, 175 tests green, audit chain in place. Read
`docs/sso-rbac-phaseA-report.md` §6 and `docs/reviews/phaseA-code-review.md` findings F1/F7 for the reasoning
already accepted.

This round closes the three hardening items that a security questionnaire asks about next, and nothing else:
login throttling per identifier, a real password policy, and response security headers.

## 1. Login throttling that is per-identifier, not only per-IP

Today `/api/auth/login` is throttled by slowapi per client IP (`LOGIN_RATE_LIMIT`, 5/minute in production).
That does nothing against a distributed attempt on one account, which is the case that matters.

Implement it **on the audit trail**, so it survives a restart and needs no shared store:

- Count `login_failed` rows for the *identifier digest* (the `identifier_sha256` already stored in `detail`)
  within a window, and refuse with **429** and a `Retry-After` header once a threshold is reached.
- Defaults, both configurable: `LOGIN_FAILURE_LIMIT` (default 5) and `LOGIN_FAILURE_WINDOW_MINUTES`
  (default 15). Count only failures for the *same digest* — and document the trade-off in a comment: an
  attacker who knows a username can deliberately lock it out for the window, which is why the existing
  per-IP limit stays in place and why the window is short.
- The check runs before the password is verified (so a locked identifier costs no bcrypt) and after the
  identifier is normalised. The refuse path writes `login_throttled` (new audit action, actor
  `"anonymous"`, detail carrying the digest — never the identifier).
- A successful login clears the count for that identifier by construction: only failures are counted, and
  the window is time-bounded.
- Get the query on a usable footing: `AuditLog.at` is indexed? If not, add an index on
  `(action, at)` — that is a new index on an existing table, which `create_all()` will **not** create on a
  live database. Do not rely on it: filter by `action` (already indexed) and compare `at` in Python, or
  accept a scan bounded by the `action` index. State in the report which you chose and why.
- Tests: five failures then a sixth attempt with the *right* password returns 429 and an audit row;
  a failure beyond the window does not lock; a different identifier is unaffected; the 429 carries
  `Retry-After`.

## 2. A password policy that is not just a length

`validate_password` today enforces 12 characters and a 72-byte ceiling. Add a strength check using
`zxcvbn` (add it to `backend/requirements.txt` — pure Python, no native build) and require a score of at
least **3**. Apply it everywhere a password is set: user creation, admin reset, own-password change.

- Reject with 422 carrying zxcvbn's own short feedback (e.g. "This is a top-10 common password"), not just
  "too weak" — the message is the point of having a policy.
- Never log or audit the password, its score inputs, or the guess list.
- Keep the 12-character floor and the 72-byte ceiling; zxcvbn is additional, not a replacement.
- Tests: `Password1!` refused (score < 3 — this exact string is the example the plan calls out),
  a long passphrase accepted, a password over 72 bytes still 422, and the refusal message names the reason.

## 3. Response headers, in one middleware

Add a single middleware in `backend/main.py` that sets, on every response:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` | `no-store` on `/api/` responses (never on static assets) |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` **only** when HTTPS is in play — reuse `backend.auth.is_https` rather than trusting `request.url.scheme` |

Do not set a `Content-Security-Policy`: the SPA uses inline handlers throughout, and a policy worth having
needs the frontend rewritten first. Say that in a comment so it is a decision, not an omission.

Tests: a response from `/api/health` carries the five static headers and `no-store`; a request carrying
`X-Forwarded-Proto: https` from a loopback peer gets HSTS and one without it does not; a static asset under
`/js/` is **not** marked `no-store`.

## Constraints

- No change to any existing table's columns; no change to Phase A/B behaviour beyond the two policies above.
- New dependency: `zxcvbn` only. Nothing else.
- Every new denial writes an audit row (through `audit()`, so it is chained).
- British spelling, comments that explain why, no emoji. No commit.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — paste the summary line.
2. A curl-level demonstration on a spare port: six failed logins then a correct one, showing 429 and
   `Retry-After`; the same response's headers; and `/api/health` headers.
3. Report: what you chose for the audit query and why, the exact policy thresholds, the header list, and
   anything you could not do.
