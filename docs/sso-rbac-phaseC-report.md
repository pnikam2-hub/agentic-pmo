# Phase C report — hardening, and the end of the planned build

Status: **complete and verified** on 20 November 2026, at commit `c5f8e58` plus the round that follows it.
Scope was `docs/sso-rbac-plan.md` §4, plus the one item both review passes ranked first: audit
tamper-evidence.

Built by Claude Code (DeepSeek V4 Pro), verified independently after each round — every claim below is a
probe I ran myself, not a builder's summary.

## 1. What shipped

### C1 — the audit trail is now tamper-evident

- `AuditChain` (new table): `seq`, `audit_id`, `prev_hash`, `hash`. Every `audit()` call writes its row and
  its link in the same transaction, so a row and its link land together or not at all.
- `hash = sha256(prev_hash || canonical_json(audit_id, at, actor, actor_role, action, target_type,
  target_id, detail, ip))`; genesis is `prev_hash = "0"×64`.
- `GET /api/admin/audit/verify` recomputes the chain, reports `ok / checked / unchained / broken_at / head`,
  and compares the head with an optional anchor file (`AUDIT_ANCHOR_PATH`) written at startup and after each
  clean verify. Pre-chain history is reported as `unchained`, never as tampering — otherwise the first run on
  an upgraded deployment would cry wolf.
- `GET /api/admin/audit/head` for the current head.

What each part actually catches, from probing a live database rather than reading the code:

| Tampering | Chain | Anchor |
|---|---|---|
| Edit a committed field of an audit row | **caught** (`broken_at` = that seq) | — |
| Delete a link in the middle | **caught** (gap) | — |
| Delete the last N rows | blind (a shorter chain is still self-consistent) | **caught** (`match: false`, `anchor_seq` ahead of `db_seq`) |
| Pre-existing rows from before C1 | reported as `unchained`, not a failure | — |

My probe: 4/4 clean, 6/6 edit, 5/5 gap, 8/8 truncate — including "head moved down by exactly the deleted
rows".

### C2 — throttling, password policy, response headers

- **Per-identifier lockout.** Failed logins are counted per identifier digest over a 15-minute window
  (`LOGIN_FAILURE_LIMIT=5`, `LOGIN_FAILURE_WINDOW_MINUTES=15`). The sixth attempt is a 429 with
  `Retry-After` and an `login_throttled` audit row. The per-IP slowapi limit stays: an identifier lockout can
  be triggered deliberately by someone who knows a username, which is why the window is short.
- **Password policy.** zxcvbn score ≥ 3, on top of the 12-character floor and the 72-byte ceiling, applied at
  user creation, admin reset and own-password change. The refusal quotes the reason.
- **Response headers.** One middleware: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store` on `/api/` only, and HSTS when
  the request is HTTPS behind a trusted proxy. No CSP — the SPA uses inline handlers, so a policy worth
  having needs the frontend rewritten first; that is a decision, recorded in the code.

Probe: five 401s then the correct password → **429, `retry-after: 899`**; a different identifier unaffected;
all five headers plus `no-store` on `/api/health`; a static asset **not** `no-store`; HSTS only with
`X-Forwarded-Proto: https` from a loopback peer. zxcvbn refused `Password1234!` ("similar to a commonly used
password"), `passwordpassword`, `qwertyuiop123!`, and accepted `Vermilion-Otter-82-Tram`.

### C3 — the audit export

`GET /api/admin/audit/export.csv` (admin only): one row per entry, newest first, columns
`at, id, seq, actor, actor_role, action, target_type, target_id, ip, hash, prev_hash, detail`, RFC 4180
quoting, `text/csv` with an `attachment` filename, `no-store`, `limit` (default 5000, max 50000) and `since`
with 422 on a bad value. The export writes an `audit_exported` row **before** streaming and the file it
describes does not contain that row.

Probe: 17/17 — header exact, one row per entry, every `detail` parses as JSON, newest first, a project named
`A, "B"\nC` round-trips through the quoting exactly, hashes are 64 hex characters, exactly one
`audit_exported` row exists and is absent from its own file, viewer 403, filters and their 422s behave.

### The paperwork

`docs/rbac-matrix.md` — one page for a security questionnaire: the four roles and their capabilities, where
each is enforced, the session model, the audit model, the deliberate exclusions, and the six questions it
answers in order. The README gains a `## Security` section that links it rather than repeating it.

## 2. Verification

| Check | Result |
|---|---|
| `pytest backend/tests -q` | **193 passed** |
| Audit-chain tamper probe (4 scenarios) | 4/4, 6/6, 5/5, 8/8 |
| Hardening probe (lockout, headers, policy) | as listed above |
| CSV export probe | 17/17 |

## 3. The one unresolved thing, stated plainly

The suite has produced the same fixture-level `401 Invalid or expired token` — creating a user seconds after
a successful admin login — about **three times in roughly thirty full-suite runs**. It has never reproduced
on demand, including 14 consecutive full runs during a deliberate hunt. Rather than slow every run with a
file-backed database on an unproven theory, the fixture now prints the admin row's id and `token_version` and
the token's own claims on failure, and the engine's shared-connection caveat is documented where the engine is
created. The next occurrence will name its cause in one line.

That is not "fixed"; it is instrumented, and a 1-in-10 flake that never recurs under investigation is the
honest description.

## 4. What is left, and in what order

The planned build — Phase A (roles), Phase B (SSO), Phase C (hardening) — is **complete**. What remains is
product decision, not unfinished work:

1. **Deploy.** `scripts/deploy_vps.sh` is written and unrun. The live instance is still pre-RBAC.
2. **Postgres**, when a client needs it: the last-admin rule becomes `SELECT … FOR UPDATE`, and the login
   lockout query gets a real index instead of relying on the `action` index.
3. **A shared store for SSO handoff single-use** if the deployment runs more than one worker.
4. **Per-project ACLs, SCIM, our own MFA, SAML** — all deliberately excluded, each a decision with its own
   cost. See `docs/rbac-matrix.md` §6.
5. **A Content-Security-Policy**, which needs the SPA's inline handlers removed first.
6. **Refresh tokens / per-token revocation** if an 8-hour window becomes unacceptable.
