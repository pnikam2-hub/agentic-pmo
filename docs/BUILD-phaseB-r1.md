# PHASE B — OIDC single sign-on (round B1: the protocol, no UI yet)

Repository: /root/projects/agentic-pmo, now at 0.2.0 with Phase A shipped and reviewed. Read
`docs/sso-rbac-plan.md` §3 (the specification) and `docs/sso-rbac-phaseA-report.md` §6 (why this is next).

This round builds the **server side of OIDC** and proves it against a locally generated identity provider.
No frontend work: the SPA button and the `#sso=<token>` handoff are round B2.

## The one dependency you may add

`cryptography>=42` in `backend/requirements.txt`, then install it in `.venv`. PyJWT cannot verify RS256
without it (`jwt.algorithms.get_default_algorithms()` excludes RS256 today), and hand-rolling RSA
verification is not an option. httpx is already a dependency — use it, do not add another HTTP client.

## New module: `backend/integrations/oidc.py`

Owns everything protocol-shaped so the router stays thin:

- `configured() -> bool` — true only when `OIDC_ISSUER` and `OIDC_CLIENT_ID` are set.
- `discover()` — GET `{issuer}/.well-known/openid-configuration`, cached in-process (issuer, authorization
  endpoint, token endpoint, jwks_uri). Raise a typed error on a malformed document.
- `start(redirect_uri)` — returns `(authorize_url, session_state)` where the state is a random 32-byte
  urlsafe token, a nonce, and a PKCE `code_verifier` (S256 challenge). One function, no globals.
- `exchange(code, verifier, redirect_uri)` — POST the token endpoint (`application/x-www-form-urlencoded`,
  `client_secret_post`), return the id_token and access token or raise.
- `verify_id_token(id_token, nonce)` — fetch JWKS (cache by `kid`, refetch once on an unknown `kid`, then
  fail), verify signature with the key matching `kid`, then validate `iss` == configured issuer,
  `aud` contains `OIDC_CLIENT_ID`, `exp`/`iat` sane, and `nonce` constant-time equal. Return the claims.
- `role_from_claims(claims)` — read `OIDC_GROUP_CLAIM` (default `groups`), match against `OIDC_ROLE_MAP`
  (JSON object; exact group name first, then the `"*"` key), else `OIDC_DEFAULT_ROLE` (default `viewer`).
  Validate the result with `backend.auth.validate_role`; an unknown mapped value falls back to the default
  and is audited rather than 500-ing.
- `identity_from_claims(claims)` — requires `email` and `email_verified` true (refuse otherwise), returns
  `(sub, email, name, issuer)`.
- The httpx client must be **injectable** (`client=None` parameter defaulting to a module-level one) so the
  tests can pass an `httpx.MockTransport`. This is the only reason tests can run with no network.

## Router: `backend/routers/auth.py` (extend)

- `GET /api/auth/sso/enabled` — `{"enabled": bool, "issuer": <issuer or null>}`. Never leak the secret.
- `GET /api/auth/sso/start` — 302 to the authorize URL; sets a signed, HttpOnly, `SameSite=Lax`,
  `Secure`-when-https cookie holding state+nonce+verifier, `max_age=600`, `path=/api/auth/sso`. Sign it with
  `JWT_SECRET` (HS256) — no new secret to manage.
- `GET /api/auth/sso/callback?code=&state=` — verify the cookie exists, its signature is valid, it has not
  expired, and `state` matches constant-time. Exchange, verify the id token, map the role, then:
  1. find the user by `external_id` = `"{issuer}#{sub}"`, else by verified email;
  2. on an email match with `source="local"`, **link** it (set `external_id`, keep the password) and say so
     in the audit row — do not silently convert an existing account to OIDC-only;
  3. no user and `OIDC_AUTO_PROVISION` (default true) → create with `source="oidc"`, `password_hash=NULL`;
  4. no user and provisioning off → 403 with a clear message;
  5. if the resolved role differs from the stored one, update it and bump `token_version` (the Phase A rule:
     a role change invalidates live tokens);
  6. issue our own JWT and redirect to `/#sso=<token>` — the fragment is never sent to a server, which is
     why it is used for the handoff. Round B2 consumes it and clears it.
- Failure responses: missing/expired/tampered cookie → 400 with a message a human can act on; a failed
  verification → 401; unknown user with provisioning off → 403. Nothing about why a signature failed beyond
  a short reason code — do not echo the claims back.
- When OIDC is not configured, all three endpoints return **503** with `{"detail": "Single sign-on is not
  configured"}` and register no other side effects.
- `LOCAL_LOGIN_ENABLED` (default true) — when `0`, `POST /api/auth/login` returns 403 "Password sign-in is
  disabled for this deployment" while SSO continues to work. Local login stays the default because an IdP
  outage must not lock the owner out.

## Audit

Add to `ACTIONS`: `sso_login`, `sso_login_failed`, `sso_user_provisioned`, `sso_user_linked`,
`sso_role_updated`. Write one row per outcome, with `detail` carrying the issuer, the mapped role and the
group names that matched — never the id token, the code, the verifier or the client secret.

## Tests: `backend/tests/test_oidc.py` (new)

No network. Generate an RSA key with `cryptography` in a fixture, publish a stub discovery document and a
JWKS through `httpx.MockTransport`, and mint id tokens locally. Cover, one test each:

1. `sso/enabled` is false with no configuration and the three endpoints answer 503.
2. `sso/start` sets an HttpOnly cookie and redirects to the stub authorize endpoint with
   `response_type=code`, the client id, the redirect uri, a state, a nonce and an S256 challenge.
3. the happy path: callback with a valid code and a valid id token provisions the user, sets
   `source="oidc"`, maps the role from `groups`, and redirects to `/#sso=<token>` which is a working JWT
   (`/api/auth/me` accepts it).
4. a tampered state → 400; a missing cookie → 400.
5. a token signed with a different key → 401; a wrong `aud` → 401; an expired token → 401; a wrong nonce → 401.
6. an unknown `kid` triggers exactly one JWKS refetch, and still-failing verification is a 401.
7. `email_verified` false → 403.
8. an existing local user with the same email is **linked** (external_id set, password kept, audited), not
   duplicated and not converted.
9. a group change on the second login updates the role and bumps `token_version` (the first token stops
   working).
10. `OIDC_AUTO_PROVISION=0` with an unknown user → 403 and an audit row; local login still works.
11. `LOCAL_LOGIN_ENABLED=0` → password login 403, and the SSO path unaffected.

## Constraints

- No schema change: `users.external_id`, `source` and `password_hash` already exist for this.
- Nothing in Phase A may regress: `pytest backend/tests -q` must stay green (125 today, more after this).
- The Plane webhook stays untouched. No frontend files. No commit.
- Never log or audit a token, code, verifier or secret. British spelling, comments that say why.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` and `.venv/bin/python -m pytest backend/tests/test_oidc.py -q`
   — paste both summary lines.
2. `.venv/bin/python -c "import backend.main"`.
3. A short report: the endpoints as built, the claims validated and why each, what the cookie holds, how the
   tests stand in for an IdP, anything in §3 you did not do. Do not write a report file.
