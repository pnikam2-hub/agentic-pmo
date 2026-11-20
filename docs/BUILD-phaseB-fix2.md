# PHASE B round B1 — second fix round (the gstack review's eleven findings)

Repository: /root/projects/agentic-pmo. `docs/reviews/phaseB-code-review.md` is the review; read it first,
then `backend/integrations/oidc.py`, the SSO section of `backend/routers/auth.py`, and
`backend/tests/test_oidc.py`. Verdict was "fit, with one reservation (B1)". Close all eleven.

Fix each with a test that fails before it. The 147-test suite must stay green.

## B1 (major) — SSO-only must be impossible unless SSO actually works

Two gates are unlinked: `LOCAL_LOGIN_ENABLED=0` closes password login, while `configured()` needs only
`OIDC_ISSUER` + `OIDC_CLIENT_ID`. Flip the switch with a missing client id, a wrong issuer, or a provider
that is down, and nobody can sign in — including the owner.

- `configured()` requires `OIDC_ISSUER`, `OIDC_CLIENT_ID` **and** `OIDC_REDIRECT_URI`, and (for the
  confidential-client exchange we perform) `OIDC_CLIENT_SECRET`.
- Add a startup guard beside `enforce_auth_config()` in `backend/main.py`: if local login is disabled and SSO
  is not configured, raise `RuntimeError` naming both variables — fail closed at boot, exactly as an insecure
  `ADMIN_PASSWORD` does today. A deployment that cannot sign anyone in must not start.
- Tests: (a) the startup guard raises with `LOCAL_LOGIN_ENABLED=0` and no OIDC config; (b) it does not raise
  when both are configured; (c) `configured()` is false when the redirect uri is missing.

## B2 — the SSO last-admin guard needs the post-write recheck too

`admin.py` re-counts after the mutation and rolls back. `sso_callback` only pre-checks. Mirror the admin
path: after `user.role = role`, before `db.commit()`, count again; if zero other active admins, `rollback()`
and refuse with the same 403 and a `last_admin` audit row. Test with `other_active_admins` monkeypatched to
report 1 while the true count is 0 — the demotion must be refused and the role unchanged.

## B3 — the deactivated-account refusal must happen before any mutation

Proven defect: on the email-link path the callback sets `user.external_id` and *then* refuses an inactive
account, and `_sso_fail` commits — so a deactivated local account gets bound to the claimant's `sub` on a
sign-in that returned 403. Move the `is_active` check to immediately after the user is resolved (both the
`external_id` match and the email match) and **before** `user.external_id` is assigned. `_sso_fail` should
not be able to flush pending mutations: give it an explicit `db.rollback()` first.
Test: a deactivated local user with a matching verified email → 403 **and** `external_id` still `None`.

## B4 — the cookie's `Secure` flag must follow the proxy

`request.url.scheme` is `http` behind the documented TLS-terminating proxy, so the cookie carrying the PKCE
verifier and nonce is neither marked `Secure` nor protected on the wire. Add a helper beside `client_ip` —
`is_https(request)` — that trusts `X-Forwarded-Proto: https` only when the direct peer is loopback/private
(the same rule `client_ip` already uses), and use it for the cookie's `secure=`. Test both directions with
`TestClient` headers.

## B5 — multi-audience id tokens need the `azp` check

After decode, when `aud` is a list of more than one entry, require `claims["azp"] == OIDC_CLIENT_ID`. Test: a
token with `aud=["other-client", OIDC_CLIENT_ID]` and no `azp` → 401; with the correct `azp` → accepted.

## B6 — rate-limit the SSO endpoints

`/sso/start` and `/sso/callback` are anonymous and unthrottled, unlike `/login`. Apply the same
`@limiter.limit(LOGIN_RATE_LIMIT)` decorator (they already take `request: Request`). One test asserting the
decorator is applied is enough — do not build a 429 harness.

## B7 — never store the raw `error` query value

Allow-list the OAuth error codes (`invalid_request`, `unauthorized_client`, `access_denied`,
`unsupported_response_type`, `invalid_scope`, `server_error`, `temporarily_unavailable`); anything else is
recorded as `"unrecognised"`. Test: `?error=<script>` yields a detail value of `unrecognised`.

## B8 — do not silently re-bind an `external_id`

If the email-matched account already carries a **different** `external_id`, refuse with 403 ("this account
is already linked to a different identity provider account") and audit `sso_login_failed` reason
`external_id_conflict`, naming neither sub in `detail` (store a short hash of each if you want correlation).
Test the refusal and that the stored `external_id` is unchanged.

## B9 — discovery needs a TTL

Cache the discovery document with a monotonic timestamp and refetch after `JWKS_TTL` (reuse the same
constant or add `DISCOVERY_TTL`), keeping the fail-closed validation. Test: with the cache aged past the TTL,
a changed `jwks_uri` in the provider document is picked up.

## B10 — replace the fragment handoff with a single-use exchange

A live 8-hour bearer token in `/#sso=<token>` sits in browser history and the `Location` header. Instead:

- the callback issues a **handoff JWT**: `purpose="sso-handoff"`, `jti` (random), `sub` = user id,
  `ver` = the user's token version, `iss="agentic-pmo"`, `exp` = now + **120 s**;
- redirect to `/#sso=<handoff>` with `Cache-Control: no-store` on both SSO redirects;
- new `POST /api/auth/sso/exchange` accepting `{"handoff": "..."}`: verify purpose, signature, `iss`, `exp`;
  reject a `jti` already used or a `ver` that no longer matches; consume the `jti`; return the normal login
  response shape (token, token_type, role, display_name, expires_at). Single-use is enforced by an
  in-process `jti` set with a TTL sweep — comment that a multi-worker deployment needs a shared store, and
  that this is the one piece of state the flow keeps.
- Tests: the callback's redirect target is a handoff token, not a session token; exchange returns a working
  token; a second exchange of the same handoff is 401; an expired handoff is 401; a handoff with a stale
  `ver` is 401; `Cache-Control: no-store` is present on the redirect.

## B11 — the session cookie needs a purpose and a required `exp`

`decode_session_cookie` accepts any HS256 JWT signed with `JWT_SECRET`. Stamp `iss="agentic-pmo-sso-state"`
in `encode_session_cookie` and decode with `issuer="agentic-pmo-sso-state"` and
`options={"require": ["exp", "iat"]}`; then assert the payload has string `state`, `nonce`, `verifier`
before use. Test: a session token minted by `create_token` is rejected as a cookie, and a cookie without
`exp` is rejected.

## Constraints

- No new dependency. No schema change. No frontend work this round. No commit.
- Phase A behaviour untouched: token versioning, `current_user`, audit-per-event, no secrets in `detail`.
- British spelling, comments that explain why, and say plainly in the report anything you cannot do.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — three consecutive runs, three summary lines.
2. `.venv/bin/python -m pytest backend/tests/test_oidc.py -q`.
3. `.venv/bin/python -c "import backend.main"`.
4. Per-finding table: what changed, the covering test, and the failing-before assertion for B1, B3, B5, B8,
   B10, B11.
