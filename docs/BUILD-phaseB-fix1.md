# PHASE B round B1 — fixes from the review pass

Repository: /root/projects/agentic-pmo. Round B1 shipped (139 tests green) but reading the SSO path found
three real defects and four smaller ones. Fix them, each with a test that would fail before the fix.

Read `backend/integrations/oidc.py`, `backend/routers/auth.py` (the SSO section), `backend/routers/admin.py`
(the last-admin rule) and `backend/tests/test_oidc.py` first.

## Must fix

**1. The SSO path can leave the deployment with no administrator (major).**
`admin.py` refuses to demote, deactivate or delete the last active admin. `sso_callback` has no such rule:
an existing `source="oidc"` admin whose group mapping now resolves to `viewer` is demoted, `token_version`
is bumped, and if they were the last admin nobody can reach `/api/admin/*` again — `bootstrap_admin` will
not restore it because the table is not empty. Add the same invariant to the SSO path: when the mapped
role differs, and the user is an active `admin`, and there is no other active admin, refuse with 403
("…would leave this deployment with no administrator") and an `sso_login_failed` row whose reason is
`last_admin`. Write it as a small helper in `auth.py` or `oidc.py` that both the admin router and the SSO
callback can call, so there is one definition of "last admin", not two.

**2. Linking an existing account must not change its authority (major).**
Today a verified-email match links the account and then applies the mapped role, so the first SSO login can
silently demote (or promote) a local user — including the bootstrap admin, whose email may match an IdP
identity with no role groups. Linking proves identity; it does not grant or remove authority. On a link,
keep the existing role, and record `{"linked": true, "role_kept": "<role>", "mapped_role": "<role>"}` in the
`sso_user_linked` row so the divergence is visible and can be resolved deliberately in Users & Audit.
Role sync continues to apply to `source="oidc"` accounts, which have no local authority to preserve — and
that path is what finding 1 guards.

**3. A deactivated user can complete SSO (major).**
`verify_token` refuses an inactive user, but the callback never looks at `is_active`: it mints a token for
them, writes an `sso_login` row as if it succeeded, and the SPA receives a token that every subsequent
request rejects with 401. Refuse at the callback with 403 "Your account has been deactivated. Contact an
administrator." and an `sso_login_failed` row with reason `inactive`. No token, no success row.

## Smaller, still worth fixing

**4. Mixed naive and aware datetimes.** `last_login_at` is set with `datetime.datetime.now(datetime.UTC)`
while Phase A's `authenticate` writes `datetime.datetime.utcnow()`; the column is naive everywhere else.
Use `utcnow()` here too so comparisons and sorting stay consistent.

**5. The provider can return `error=` instead of a code.** A cancelled sign-in or a refused scope arrives
as `?error=access_denied&state=…`. Today that falls through to "missing the authorisation code". Read
`error` and answer 400 "Sign-in was cancelled at the identity provider" with an `sso_login_failed` reason of
`provider_error` and the error code in `detail` (the code is not a secret).

**6. Provisioning can race itself.** Two first logins for the same new person, or a username that a
concurrent request just took, raise `IntegrityError` and become a 500. Catch it, roll back, re-query by
`external_id` then email, and continue with whichever row won; if there is still no row, return 409 with a
clear message.

**7. The JWKS cache never forgets a key.** `_jwks_cache` merges and never evicts, so a key the provider has
retired is trusted for the life of the process — the opposite of what rotation is for. Cache per `jwks_uri`
with a timestamp (TTL 3600 s); a refresh replaces that issuer's key set wholesale while keeping the
existing "refetch once on an unknown kid" behaviour. Add a test: a key removed from the JWKS is no longer
accepted once the cache is stale.

**8. No clock-skew tolerance.** `iat`/`exp` are validated with zero leeway, so an IdP a few seconds ahead
of us rejects every login. Pass `leeway=60` to `pyjwt.decode`. Test: a token with `iat` 30 seconds in the
future still verifies.

## Test hygiene (this is what makes the suite flaky)

Two runs of the full suite out of roughly ten reported `ERROR … test_rbac.py::test_long_password_is_422_not_500`
— an assertion inside the `roles` fixture, seen twice and never reproduced on demand afterwards. Treat both
plausible causes:

- **Raise the test login ceiling.** `backend/tests/conftest.py` pins `LOGIN_RATE_LIMIT=1000/minute`; a slow
  run across 139 tests can approach it, and a 429 inside a fixture appears exactly this way. Raise it to
  `100000/minute` — `test_security.py` builds its own app and limiter to test the 429 path, so nothing loses
  coverage.
- **Stop sharing one scratch database between runs.** The `DATABASE_URL` pin should include
  `os.getpid()` so a file left by a previous run can never be read by this one. Keep the same comment
  explaining why the pin exists at all.

Then run the full suite **six times** and report the six summary lines. A suite that fails one run in ten
is worse than a failing test, because it teaches everyone to re-run.

## Constraints

- No new dependencies. No schema change. Local login, the Plane webhook and every Phase A behaviour stay as
  they are. No frontend work. No commit.
- The five audit actions from B1 stay; add nothing that carries a token, code, verifier, secret or raw claim.
- British spelling, comments that explain why.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — six consecutive runs, six summary lines.
2. `.venv/bin/python -m pytest backend/tests/test_oidc.py -q`.
3. `.venv/bin/python -c "import backend.main"`.
4. A per-finding table: what changed, the test that covers it, and the failing-before assertion for 1, 2
   and 3. State plainly anything you could not do.
