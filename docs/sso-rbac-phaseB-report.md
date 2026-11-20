# Phase B report — OIDC single sign-on (server side)

Status: **complete and verified** on 20 November 2026, at commit `be842c8`. Scope was
`docs/sso-rbac-plan.md` §3. The browser half — the "Sign in with SSO" button and consuming the handoff —
is round B2 and is not built yet.

Built by Claude Code (DeepSeek V4 Pro; GLM-5.2 was quota-limited), reviewed by gstack `/review`
(`docs/reviews/phaseB-code-review.md`), and every finding closed against a test.

## 1. What ships

| Piece | Where |
|---|---|
| Discovery, PKCE, token exchange, id-token verification, group→role mapping, identity gate, signed state cookie | `backend/integrations/oidc.py` (new) |
| `GET /api/auth/sso/enabled`, `GET /api/auth/sso/start`, `GET /api/auth/sso/callback`, `POST /api/auth/sso/exchange` | `backend/routers/auth.py` |
| Fail-closed startup guard for SSO-only deployments | `enforce_sso_config()` in `backend/main.py` |
| Shared last-admin definition, used by the admin router *and* the SSO path | `backend/auth.py::other_active_admins` |
| Audit outcomes | `sso_login`, `sso_login_failed`, `sso_user_provisioned`, `sso_user_linked`, `sso_role_updated` |
| One new dependency | `cryptography>=42` — PyJWT cannot verify RS256 without it |

No schema change: `users.external_id`, `source` and nullable `password_hash` were designed for this in
Phase A.

## 2. The flow, in the order the code enforces it

1. `/sso/start` mints 32 random bytes of `state`, a `nonce` and a PKCE verifier (S256), signs them into an
   HttpOnly, `SameSite=Lax` cookie scoped to `/api/auth/sso` with a 600-second expiry, and redirects to the
   discovered authorization endpoint.
2. `/sso/callback` checks the cookie exists, verifies its signature and purpose, compares `state`
   constant-time, then exchanges the code (client secret in the form body, never the URL).
3. The id token is verified: algorithm pinned to RS256, key selected by `kid` from a TTL'd JWKS that is
   replaced wholesale on refresh, one bounded refetch on an unknown `kid`, then `iss`, `aud` (with `azp` when
   the audience is a list), `exp`/`iat` with 60 seconds of leeway, and `nonce` constant-time.
4. Identity requires `email` and `email_verified`. The account is resolved by `external_id`, then by verified
   email: an email match **links** (keeping its role — linking proves identity, not authority, and the
   divergence between kept and mapped role is audited); no match provisions an `oidc` user when
   `OIDC_AUTO_PROVISION` allows it.
5. Refusals happen before any mutation is committed: a deactivated account, a conflicting `external_id`, a
   demotion that would remove the last active admin. Each writes one audit row with a coarse reason.
6. A role change bumps `token_version`, so tokens minted under the old role die — the Phase A rule.
7. The browser gets `/#sso=<handoff>`: a 120-second, single-use JWT whose only job is to be exchanged at
   `POST /api/auth/sso/exchange` for the real session token. Both SSO redirects carry `Cache-Control:
   no-store`.

The handoff's single-use set is in-process. A multi-worker deployment needs a shared store; that is stated in
the code and is the one piece of state this flow keeps.

## 3. Configuration

All optional; SSO is off unless every one of these is set:

| Variable | Default | Meaning |
|---|---|---|
| `OIDC_ISSUER` | — | e.g. `https://login.microsoftonline.com/<tenant>/v2.0` |
| `OIDC_CLIENT_ID` | — | the client registered at the IdP |
| `OIDC_CLIENT_SECRET` | — | required for the confidential-client exchange we perform |
| `OIDC_REDIRECT_URI` | — | must match the IdP registration exactly, e.g. `https://host/api/auth/sso/callback` |
| `OIDC_SCOPES` | `openid email profile` | |
| `OIDC_GROUP_CLAIM` | `groups` | |
| `OIDC_ROLE_MAP` | `{}` | JSON, e.g. `{"pmo-admins":"admin","pmo-leads":"pmo_lead","*":"viewer"}` |
| `OIDC_DEFAULT_ROLE` | `viewer` | when no group matches |
| `OIDC_AUTO_PROVISION` | `true` | create a user on first successful login |
| `LOCAL_LOGIN_ENABLED` | `true` | set `0` for SSO-only — and the app **refuses to start** if SSO is not fully configured |

Entra ID, Google Workspace and Okta all work unchanged, because all three are plain OIDC. SAML remains out
of scope for v1.

## 4. Verification

| Check | Result |
|---|---|
| `pytest backend/tests -q` | **166 passed** |
| `pytest backend/tests/test_oidc.py -q` | 41 passed |
| gstack `/review` verdict | "Yes — fit for an enterprise security review, with one reservation" |
| The reservation (B1: SSO-only could lock the owner out) | closed, with a startup guard and three tests |
| Every one of the eleven findings | closed, each with a test that fails before the fix |
| The one defect the reviewer proved at runtime (a deactivated local account being linked on the refusal path) | closed; `test_deactivated_local_user_is_not_linked_on_refusal` |

The tests stand in for an IdP: an RSA key generated in a fixture, a stub discovery document and JWKS served
through `httpx.MockTransport`, and id tokens minted locally — so every adversarial case (wrong key, wrong
audience, wrong nonce, expired, unknown kid, retired key, tampered state, unverified email, multi-audience
without `azp`) is proven with no network.

## 5. What is deliberately not here

- **The SPA button and the handoff consumption** — round B2. Until then the endpoints are complete but
  nothing in the interface links to them.
- **Refresh tokens, `jti` revocation for session tokens, per-identifier throttling, SCIM** — Phase C.
- **A shared store for handoff single-use** — needed only if the deployment runs multiple workers.
- **SAML** — a new decision with its own cost, as the plan says.

## 6. What an enterprise reviewer will ask next

1. Audit tamper-evidence (Phase A's F10): hash-chained rows or an append-only DB role.
2. Security headers at the proxy (`X-Frame-Options`, `Referrer-Policy`, HSTS) and `Cache-Control` on the API.
3. Per-identifier login throttling and a real password policy (zxcvbn) for the local accounts that remain.
4. A one-page RBAC matrix and an audit CSV export for the questionnaire.
5. Postgres, where the last-admin rule becomes `SELECT … FOR UPDATE` rather than relying on SQLite's
   serialised writer.
