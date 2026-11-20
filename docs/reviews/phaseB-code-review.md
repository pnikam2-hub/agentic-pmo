# Phase B code review — OIDC single sign-on

Reviewed range: `git diff 02a6c4d..HEAD` (one commit, `feat(sso): OIDC sign-in`). Governing docs:
`docs/sso-rbac-plan.md` §3, `docs/BUILD-phaseB-r1.md`, `docs/BUILD-phaseB-fix1.md`. Method: full read of
`backend/integrations/oidc.py` (the whole protocol surface), the SSO section of `backend/routers/auth.py`,
`backend/audit.py`, the `users`/`audit_logs` models, the `admin.py` last-admin refactor, `backend/tests/
test_oidc.py`, and the untouched webhook path; the full suite; plus two targeted runtime probes (multi-
audience `aud` acceptance, and the deactivated-account mutation-on-refusal) against an in-memory SQLite DB.

## 1. Verdict

**Yes — fit for an enterprise security review, with one reservation to close before any SSO-only
deployment.** The two decisive reasons. First, the id-token verification chain is correct and complete:
the algorithm is pinned to RS256 (an HS256 or `none` token is rejected before key material matters), the
signature is checked against a JWKS key selected by `kid` with a bounded refetch and a TTL'd,
wholesale-replaced key set (so a retired key stops being trusted), and `iss`/`aud`/`exp`/`iat`/`nonce` are
all enforced — `nonce` constant-time against the signed state cookie, which itself carries a random
CSRF-bindable `state` and the PKCE verifier. Every denial in the brief's threat model (wrong key, wrong
`aud`, expired, wrong `nonce`, unknown `kid`, tampered/missing state, retired key, unverified email) is
proven by a test that mints the adversarial token locally — 22 OIDC tests and the full 147-test suite pass.
Second, provisioning and role mapping are least-privilege and audit-complete: linking proves identity, not
authority (a local account keeps its role, and the divergence is recorded); an unknown mapped role degrades
to `viewer` with an audit row rather than elevating; deactivated users and the last active admin are refused;
and no token, code, verifier or secret ever reaches an error message or an audit `detail`. The single
reservation is **B1**: the escape hatch can be switched off with no startup guard tying it to a working
SSO configuration, so `LOCAL_LOGIN_ENABLED=0` with `OIDC_ISSUER` unset or the IdP unreachable leaves the
deployment with no way in. That is a config-validation gap, not a protocol hole, but it is exactly the
"lock the owner out" failure this phase exists to rule out, and it should be closed before running
SSO-only. No finding here lets an attacker in.

## 2. Findings table

| ID | Severity | file:line | Summary |
|---|---|---|---|
| B1 | major | `backend/integrations/oidc.py:69-80, 122-124` · `backend/routers/auth.py:80-81` · `backend/main.py:92-108` | `LOCAL_LOGIN_ENABLED=0` with SSO unconfigured/misconfigured locks the owner out and nothing at startup catches it |
| B2 | minor | `backend/routers/auth.py:371-378` | SSO last-admin guard is a single pre-write check with no post-write recheck (admin.py has one); concurrent demotions can still leave zero admins |
| B3 | minor | `backend/routers/auth.py:300-309, 347-351, 357-361` | A deactivated email-linked account has its `external_id` committed on the refusal path, contradicting "before any mutation is committed" |
| B4 | minor | `backend/routers/auth.py:217-225` | Cookie `Secure` derives from `request.url.scheme`; behind the documented TLS-terminating proxy the signed cookie goes plaintext |
| B5 | minor | `backend/integrations/oidc.py:310-318` | Multi-audience id_token accepted without an `azp` check — a token minted for another client of the same issuer passes |
| B6 | minor | `backend/routers/auth.py:200-226, 229-420` | SSO endpoints are unauthenticated and un-rate-limited (unlike `/login`); attacker can drive outbound token-endpoint calls and flood the audit log |
| B7 | minor | `backend/routers/auth.py:247-252` | The `error` query value is written verbatim into audit `detail` by an unauthenticated caller — attacker-controlled text in the trail |
| B8 | minor | `backend/routers/auth.py:300-309` | Linking by verified email silently overwrites `external_id`; a second IdP identity with the same email re-binds the account |
| B9 | minor | `backend/integrations/oidc.py:136-158` | Discovery document is cached with no TTL; token/jwks endpoints are pinned until process restart |
| B10 | minor | `backend/routers/auth.py:419-420` | The `/#sso=<token>` handoff puts a live 8-hour bearer token in the fragment and the 302 is not `no-store` |
| B11 | minor | `backend/integrations/oidc.py:404-409` | `decode_session_cookie` requires no `exp`/`iss`/purpose discriminator; the cookie's only protection is the shared `JWT_SECRET` |

## 3. Findings in full

### B1 — `LOCAL_LOGIN_ENABLED=0` with SSO unconfigured locks the owner out (major)

**What it is.** Two independent gates govern how anyone signs in: `POST /api/auth/login` refuses when
`oidc.LOCAL_LOGIN_ENABLED` is false (`backend/routers/auth.py:80-81`), and the three SSO endpoints return
503 when `oidc.configured()` is false (`backend/integrations/oidc.py:122-124`, which requires only
`OIDC_ISSUER` **and** `OIDC_CLIENT_ID`). Nothing ties the two together. `configured()` also ignores
`OIDC_REDIRECT_URI` and `OIDC_CLIENT_SECRET`, both of which the flow needs to complete.

**How it fails.** An operator sets `LOCAL_LOGIN_ENABLED=0` intending SSO-only, but forgets to set
`OIDC_CLIENT_ID`, sets a wrong issuer, or the discovery document is unreachable: password login returns
403, `/sso/start` returns 503, and no one — including the owner — can reach any protected route. Recovery
is possible only by editing `.env` and restarting, but nothing at startup (`backend/main.py:92-108`, which
checks only `ADMIN_PASSWORD`/`JWT_SECRET` via `enforce_auth_config`) warns that the deployment has
disabled its own front door. The build brief calls this exact failure out ("an IdP outage must never lock
the owner out"), and the guard for it is absent. The same gap means `configured()` can report "enabled"
while a missing `OIDC_REDIRECT_URI` makes every flow 502.

**Fix.** At startup (or in `configured()`), fail closed — or at minimum emit a loud warning — when
`LOCAL_LOGIN_ENABLED` is false and `configured()` is false, and require `OIDC_REDIRECT_URI` (and
`OIDC_CLIENT_SECRET` for the confidential-client exchange) before `configured()` returns true. The intent is
"SSO-only is only possible when SSO is actually configured."

**Verified.** Code-read, composed from two passing tests: `test_disabled_without_configuration` (no config
→ all SSO endpoints 503) and `test_local_login_disabled` (`LOCAL_LOGIN_ENABLED=False` → login 403). The
combination — both off at once — is not tested; that is the gap.

### B2 — SSO last-admin guard is a single check with no post-write recheck (minor)

**What it is.** `sso_callback` (`backend/routers/auth.py:371-378`) guards the role-change demotion of an
admin with a single `other_active_admins(db, user) == 0` read and then applies the demotion and commits.
The admin router, which fix1 consolidated onto the same `backend.auth.other_active_admins` helper, performs
a **second** count after the mutation and before commit (`backend/routers/admin.py:176-188, 236-243`) to
close the stale-read window. The SSO path has no such post-write recheck.

**How it fails.** Two active oidc admins, A and B, whose group mappings both resolve downward. Two
concurrent SSO logins each run the pre-check and each see the *other* admin as still active, so both pass,
both demote, both commit — zero admins remain, and `bootstrap_admin` cannot restore the situation (it
refuses a non-empty table). This is the same TOCTOU the Phase A review flagged in the admin router (F2),
re-introduced in the new path that fix1 added specifically to prevent this outcome. The trigger is narrower
(two concurrent SSO logins of two distinct admins), which is why this is minor rather than major — but the
admin router shows the fix, so it is a consistency gap rather than a hard limit.

**Fix.** Mirror `admin.py`: re-run `other_active_admins` after `user.role = role` and before `db.commit()`,
rollback and refuse if zero.

**Verified.** Code-read (reasoned from the check-then-write structure); not reproduced under concurrency —
a deterministic reproduction needs two interleaved sessions, but the missing post-write recheck is
structural, and the contrast with `admin.py:176-188` is exact.

### B3 — Deactivated email-linked account gets `external_id` committed on refusal (minor)

**What it is.** The `is_active` refusal (`backend/routers/auth.py:357-361`) sits *after* the
find-or-create block. On the email-match path (`:300-309`) — and the race-adopt path (`:347-351`) — the
code does `user.external_id = external_id` before the guard, and then `_sso_fail` (`:158-171`) calls
`db.commit()` before raising 403. The comment at `:353-356` claims the refusal happens "before any mutation
is committed, so … the account keeps its pre-login state" — that is false for the link mutation.

**How it fails.** A deactivated **local** account whose email matches the IdP identity is linked on the
failed sign-in: its `external_id` is persisted to the attacker's/claimant's `sub` despite the 403. If an
admin later reactivates the account (unaware the binding changed), the identity that owns that `sub` can
SSO-login, be found by `external_id` (`:296`), and receive the account's preserved role. The deactivation
check — the whole point of fix1 finding 3 — is silently weakened on exactly the linking path.

**Fix.** Move the `is_active` check before any mutation (before `user.external_id = external_id`), or make
the refusal path not commit pending state (`_sso_fail` should flush/rollback rather than commit, or the
link should be applied only after the guard passes).

**Verified.** Yes — ran a probe against an in-memory DB with a deactivated local user (`is_active=0`) and a
matching verified email: the callback returned 403 "…deactivated…", and the account's `external_id` changed
from `None` to `https://issuer.test#alice-123`. The existing `test_deactivated_user_cannot_complete_sso`
does not catch this because it constructs an `external_id`-matched (oidc) user, not the email-link path.

### B4 — Cookie `Secure` derives from the request scheme, not the forwarded proto (minor)

**What it is.** `sso_start` sets `secure=request.url.scheme == "https"` (`backend/routers/auth.py:217-225`).
Behind the reverse proxy the code itself documents and accounts for in `client_ip`
(`backend/auth.py:241-261`), `request.url.scheme` is `"http"` — the proxy terminates TLS and forwards
plaintext. So the signed session cookie, which holds the **PKCE verifier and the nonce**, is sent unencrypted
to the proxy and is not marked `Secure`.

**How it fails.** On the documented deployment (single TLS-terminating reverse proxy), the cookie that
authorises the code redemption travels in cleartext over the loopback/private hop, and the browser will
replay it over plaintext HTTP anywhere the hostname is reachable. An on-path observer between proxy and app
— or a browser that later visits the same host over HTTP — can read the verifier+state+nonce and complete
(or race) the sign-in. The `state`/`nonce` are CSRF tokens, not the token itself, so the practical impact is
bounded by the 600 s cookie TTL and the single-use code, but the `Secure` flag is silently lying about
whether the cookie is protected.

**Fix.** Derive `secure` from a trusted `X-Forwarded-Proto` (mirroring the `client_ip` trusted-proxy rule)
or a dedicated `COOKIE_SECURE`/proxy-header config flag, defaulting to `request.url.scheme == "https"` only
when no proxy is documented.

**Verified.** Code-read; `TestClient` is plain HTTP so the existing `test_start_sets_cookie_and_redirects`
observes (and asserts) a cookie without `Secure`, which is precisely the wrong default behind a proxy.

### B5 — Multi-audience id_token accepted without an `azp` check (minor)

**What it is.** `verify_id_token` passes `audience=OIDC_CLIENT_ID` (a string) to `pyjwt.decode`
(`backend/integrations/oidc.py:310-318`). pyjwt treats a string audience as membership: a token whose `aud`
is a **list** passes as long as the client id appears anywhere in it. OIDC Core requires that when `aud`
contains multiple parties, the `azp` (authorized party) claim be checked to confirm the token was actually
issued *for this client*.

**How it fails.** An id_token minted by the same issuer for a *different* client but carrying
`aud: ["other-client", "pmo-client"]` verifies here. In the normal flow the token endpoint returns our own
client's token, so this is defence-in-depth against a confused or multi-tenant provider (Entra ID in
particular issues multi-`aud`/`azp` tokens) rather than a direct attack — but the check the spec names for
exactly this confusion is absent.

**Fix.** After decode, if `aud` is a list with length > 1, require `claims.get("azp") == OIDC_CLIENT_ID`.

**Verified.** Yes — ran `pyjwt.decode` with a token carrying `aud=["other","me"]` and `audience="me"`; it
was accepted (returns the list), confirming the membership behaviour the code relies on.

### B6 — SSO endpoints are unauthenticated and un-rate-limited (minor)

**What it is.** `POST /api/auth/login` is throttled with `@limiter.limit(LOGIN_RATE_LIMIT)`
(`backend/routers/auth.py:76`), but `/sso/start` (`:200`) and `/sso/callback` (`:229`) carry no limiter and
no auth. Both are reachable by any anonymous caller.

**How it fails.** An attacker can repeatedly hit `/sso/start` (each call builds a redirect and, on a cold
discovery cache, an outbound HTTPS request to the IdP) and `/sso/callback` with a self-minted cookie
(`/sso/start` hands them a valid signed cookie for free, so the state check is not a barrier). Each callback
with a bogus `code` drives an outbound token-endpoint POST and writes an `sso_login_failed` row. This is an
amplification path against the IdP and an unbounded audit-log fill, neither of which the login throttle
protects against.

**Fix.** Apply `limiter.limit(LOGIN_RATE_LIMIT)` (or a dedicated SSO limit) to `/sso/start` and
`/sso/callback`.

**Verified.** Code-read; the absence of the decorator is unambiguous, and `/login`'s decorator is the
in-repo contrast.

### B7 — The `error` query value is written verbatim into the audit trail (minor)

**What it is.** On a provider error, `sso_callback` records `detail={"error": error}`
(`backend/routers/auth.py:247-252`) where `error` is the raw, unauthenticated query parameter. The comment
assumes it is "a coarse, public category", but nothing validates it against the OAuth error registry.

**How it fails.** Any anonymous caller can GET `/sso/callback?error=<arbitrary>` and have that string
persisted in `audit_logs.detail` — a log-injection / audit-spoofing channel (an attacker can plant "false"
records, e.g. `error=account_compromised`, that a later reviewer will mistake for a real provider refusal)
and, combined with B6, an unaudited row-flooding vector. `detail` is JSON so classic newline injection is
contained today, but any future CSV/HTML export re-opens it.

**Fix.** Allow-list the OAuth error codes (`access_denied`, `server_error`, `temporarily_unavailable`, …)
and store only a recognised value (or a boolean), never the raw string.

**Verified.** Code-read; the value flows from `Query` to `detail` with no validation in between.

### B8 — Linking by verified email silently overwrites `external_id` (minor)

**What it is.** On an email match, `user.external_id = external_id` is assigned unconditionally
(`backend/routers/auth.py:300-309`). There is no check for whether the account already has a *different*
`external_id` bound.

**How it fails.** Two distinct IdP subjects that share a verified email both resolve to the same account:
the first SSO login binds `sub1`, the second binds `sub2` and silently severs the first binding. Because
linking preserves the account's role, a second identity that comes to control the shared email inherits
whatever authority the account holds — and the account owner's own `sub` is de-linked with no audit note.
Email reuse/rename at the IdP is exactly the scenario that makes `sub`-binding valuable, and it is the one
place the code treats the binding as disposable.

**Fix.** If `user.external_id` is already set to a different `sub`, refuse (or record the replacement as its
own audited event) rather than silently overwriting.

**Verified.** Code-read; the assignment at `:308` has no preceding `external_id` comparison.

### B9 — Discovery document cached with no TTL (minor)

**What it is.** `discover()` caches the full document keyed by issuer with no timestamp or expiry
(`backend/integrations/oidc.py:136-158`), unlike the JWKS cache which ages out after `JWKS_TTL` and replaces
wholesale.

**How it fails.** The token endpoint, authorization endpoint and `jwks_uri` are pinned for the life of the
process. A provider that rotates its `jwks_uri` (or migrates tenants, a routine Entra ID event) leaves this
deployment POSTing codes to a dead token endpoint and fetching keys from a dead URI until restart. Rotation
of the *keys* is handled (the JWKS TTL); rotation of the *locations* is not.

**Fix.** Store a monotonic timestamp with the cached document and refetch after a TTL (reusing the
`JWKS_TTL`-style pattern), preserving the fail-closed "malformed doc → refuse" behaviour.

**Verified.** Code-read; the cache write at `:157` stores the document with no timestamp, and every
subsequent call returns it unconditionally at `:137-138`.

### B10 — The `/#sso=<token>` handoff is a live bearer token with no `no-store` (minor)

**What it is.** The callback returns `RedirectResponse(f"/#sso={token}")` (`backend/routers/auth.py:419-420`)
where `token` is a full 8-hour session JWT. The fragment is never sent to the origin on the *next* request,
which is the stated reason for the design, but the token still sits in the browser address bar, browser
history, and the response `Location` header — and neither SSO redirect sets `Cache-Control: no-store`.

**How it fails.** The token is retained in the browser's history/address bar (and in any extension or shared
machine that reads them) and can be emitted by the browser as a `Referer` on a subsequent navigation, and a
caching intermediary that logs or stores response `Location` headers retains it. This is an accepted
trade-off of the fragment handoff the build brief chose (and round B2 is meant to read-and-clear it), but
the missing `no-store` and the 8-hour lifetime make the residual exposure larger than it needs to be.

**Fix.** Set `Cache-Control: no-store` on both SSO redirects; prefer a short-lived, single-use handoff code
exchanged for the JWT by the SPA over putting the 8-hour token in the fragment.

**Verified.** Code-read; the two redirects (`:216`, `:420`) set no cache-control header.

### B11 — `decode_session_cookie` has no `exp`/issuer/purpose discriminator (minor)

**What it is.** `decode_session_cookie` (`backend/integrations/oidc.py:404-409`) does
`pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])` with no `options={"require": ["exp"]}`, no `issuer`,
and no `purpose`/`typ` claim. Its only defence is the secrecy of `JWT_SECRET` — the same key that signs the
bearer session tokens (`create_token`).

**How it fails.** The brief's substitution concern — "our own session JWT replayed as the `pmo_sso` cookie,
or the cookie replayed as a bearer token" — is *currently* rejected only by accident of shape: the bearer
token has `sub`/`iss` and no `state`/`nonce`, and the cookie has the reverse, so each decoder rejects the
other's payload. But the cookie decoder asks for no `exp`, so a cookie minted (or forged, in any
`ALLOW_INSECURE_DEFAULTS`/default-secret environment) without `exp` is accepted indefinitely, and nothing
cryptographically distinguishes a "session state" JWT from a "session token" JWT. A future edit that adds a
`sub` to the cookie, or drops the `iss` check from `verify_token`, silently re-opens the confusion, because
the two token types are not discriminated by claim.

**Fix.** Require `exp` and a fixed `purpose`/`iss` value in the cookie (`pyjwt.decode(..., options={"require":
["exp"]}, issuer="agentic-pmo-sso-state")`), and assert the payload is a dict with string `state`/`nonce`/
`verifier` before use.

**Verified.** Code-read; the decode at `:407` carries no `options` or `issuer`, and `encode_session_cookie`
at `:397-401` stamps only `iat`/`exp`.

## 4. What the change gets right

- **The token-substitution surface is genuinely closed.** `verify_id_token` pins `algorithms=["RS256"]`,
  so an HS256 token offered where RS256 is expected is rejected outright (an HS256 token whose `alg` is not
  in the allowed list fails before the key is consulted), and `_jwk_to_key` constructs only RSA public keys —
  a symmetric `oct` key in the JWKS is skipped, not used as an HMAC secret. `iss`, `aud`, `exp`, `iat` and
  `nonce` are all verified, `nonce` constant-time. Verified by the full 22-test OIDC suite, each minting the
  adversarial token with a locally generated key through `httpx.MockTransport`.
- **Key rotation is actually rotation.** `_jwks_cache` is keyed per `jwks_uri` with a monotonic timestamp;
  a refresh *replaces* the key set wholesale, and the "refetch exactly once on an unknown `kid`" behaviour is
  bounded (the test asserts exactly two JWKS calls). The retired-key test proves a rotated-out key stops
  verifying once the cache is stale — the opposite of the merge-forever bug fix1 set out to kill.
- **Session fixation and CSRF on the callback are defended correctly.** `state` is 32 random bytes, signed
  into an HttpOnly/SameSite=Lax cookie scoped to `/api/auth/sso`, and compared constant-time against the
  query before any code is exchanged. The PKCE verifier is in the same signed cookie, so a callback the
  browser did not start (no cookie, tampered cookie, wrong state) is refused before it can redeem anything.
- **Provisioning is least-privilege and the escalation paths fix1 named are shut.** Linking preserves the
  existing role and records `role_kept` vs `mapped_role`; an unknown mapped role degrades to `viewer` and
  is audited (`role_fallback`); the wildcard/default fall back to `viewer` when unconfigured; deactivated
  users are refused before a token is minted; and the last-admin invariant is shared with the admin router
  via one `backend.auth.other_active_admins` helper.
- **Every refusal leaves an audit row with a coarse reason, never a claim or secret.** `_sso_fail` records
  issuer + a reason code; the failure messages are category-level ("…did not verify", "…cancelled"), and
  `sso_enabled` returns the issuer only. No token, code, verifier, secret, or raw claim reaches a `detail`.
- **The race on first login is handled rather than 500-ing.** The `IntegrityError` rollback-and-adopt path
  is tested both for the "loser adopts the winner" and "still no row → 409" cases.
- **Discovery is validated, not just fetched.** The document's `issuer` must equal the configured issuer
  (confused/hostile endpoint refusal), missing fields are rejected, and a failed discovery maps to 502 rather
  than 500. The failure path is not negatively cached, so a transient outage recovers on the next attempt.
- **The dependency constraint is held.** `cryptography` is the only addition (`requirements.txt`), used
  solely for RS256 public-key construction; no schema change (`external_id`/`source`/`password_hash` were
  already present); the Plane webhook is untouched and remains HMAC-only with no role dependency.
- **The suite is green and the gate is real.** `147 passed` across the full suite; `test_oidc.py` drives the
  real `current_user`/`require_auth` chain (it removes and restores the `test_api.py` stand-ins) and proves
  `/#sso=<token>` is a working JWT accepted by `/api/auth/me`.

## 5. What §3 asks for that is missing

Nothing in §3 is outright missing: `configured()`, `discover()`, `start()`, `exchange()`,
`verify_id_token()`, `role_from_claims()`, `identity_from_claims()`, the three endpoints, the five audit
actions, the `LOCAL_LOGIN_ENABLED` switch, and all eleven B1 test cases exist and pass. The gaps are
hardening or conformance rather than spec breaches:

- **No startup validation ties `LOCAL_LOGIN_ENABLED` to a working OIDC config** (B1) — the "IdP outage must
  not lock the owner out" rule is honoured only in the default state, not when the operator flips the switch.
- **`azp` is not validated for multi-audience tokens** (B5) — OIDC Core conformance, not in §3's list.
- **No rate limiting on the SSO endpoints** (B6) — §4 defers per-identifier throttling to Phase C, but
  `/login` already has per-IP throttling and the SSO endpoints inherit none of it.
- **Discovery caching has no TTL** (B9) — §3 specifies key *rotation* (handled); endpoint rotation is not.
- **The `/#sso=<token>` fragment handoff and its `no-store`/lifetime story** (B10) — this is the documented
  B2 handoff, but B1 ships the token in the fragment today with none of the B2 read-and-clear machinery, so
  the exposure window is "however long the browser keeps history", not "until B2 clears it".

## Constraints checked (no "fix away")

- No new dependency beyond `cryptography` — held (`requirements.txt` adds exactly that one line).
- No schema change: `users.external_id`, `source`, nullable `password_hash` already existed — held
  (`models.py` unchanged in this range).
- Local password login stays available by default — held (`LOCAL_LOGIN_ENABLED` defaults true).
- Four global roles; OIDC maps to them, never invents a fifth — held (`validate_role` is the only writer).
- The Plane webhook stays HMAC-only with no role dependency — held (`main.py` includes it bare).
- Every Phase A behaviour: token versioning, `current_user` as the sole resolution point, an audit row per
  security event, no secret in any `detail` — held (all re-confirmed in this read; the Phase A `login_failed`
  identifier now stores a salted digest, and the denial audit and `X-Forwarded-For` handling from the Phase A
  fix-round are present).
