# gstack review pass — Phase B (OIDC single sign-on)

Repository: /root/projects/agentic-pmo. Run `/review` against the Phase B change.

## What to review

`git diff <phase-A-head>..HEAD` — read it from `docs/sso-rbac-phaseA-report.md` to find the Phase A head, or
simply review `backend/integrations/oidc.py` in full plus the SSO section of `backend/routers/auth.py`,
their tests, and the audit additions. That module is the whole protocol surface; the router only wires it to
HTTP and the users table.

The specification is `docs/sso-rbac-plan.md` §3. The build briefs are `docs/BUILD-phaseB-r1.md` and
`docs/BUILD-phaseB-fix1.md`.

## Constraints a reviewer must not "fix" away

- No new dependency beyond `cryptography` (added for RS256 verification — PyJWT cannot do it without).
- No schema change: `users.external_id`, `source` and nullable `password_hash` already existed.
- Local password login stays available by default (`LOCAL_LOGIN_ENABLED`), because an IdP outage must not
  lock the owner out of their own PMO.
- Four global roles. OIDC supplies the identity and a mapped role; it does not invent a fifth.
- The Plane webhook stays HMAC-only with no role dependency.
- Every Phase A behaviour stays: token versioning, `current_user` as the only resolution point, an audit row
  per security event, no secret in any `detail`.

## Where to aim

The threat model for this code is **not** "is the happy path wired up" — the tests prove that. It is:

- **Token substitution and confusion.** An id_token minted for another client, another issuer, another
  nonce, or signed with a key we should not trust. An HS256 token offered where RS256 is expected. Our own
  session JWT replayed as the `pmo_sso` cookie, or the cookie replayed as a bearer token.
- **Session fixation and CSRF on the callback.** State that is absent, replayed, or attacker-chosen; a
  callback that completes a sign-in the browser did not start; a cookie that survives too long or is too
  widely scoped.
- **Provisioning as an escalation path.** A verified email that matches an existing account, a group map
  that yields a role the operator did not intend, a deactivated user, the last administrator being demoted
  or deactivated through the SSO path rather than the admin API, a race between two first logins.
- **Key rotation and cache staleness.** A retired key still trusted, an unbounded cache, a JWKS refetch that
  is a denial-of-service vector, a provider that is unreachable at the wrong moment.
- **Information leaks.** Claims echoed in errors, tokens in URLs, secrets in audit detail, a login that
  reveals whether an account exists, a failure message that says which check failed.
- **Availability of the escape hatch.** `LOCAL_LOGIN_ENABLED=0` set by mistake with SSO misconfigured; OIDC
  configured but the discovery document unreachable at start-up.

## Standards for the output

- Severity: `blocker`, `major`, `minor`. Blockers are things that let an attacker in or lock the owner out.
- Every finding cites `file:line`, the attacker or failure mode, the consequence, and the concrete fix.
- Verify by running where you can: the suite is `pytest backend/tests -q`; the OIDC tests use
  `httpx.MockTransport` with a locally generated RSA key, so you can extend that to test a specific attack
  without any network. Say "verified by running X" or "not verified" per finding.
- Fewer than eight substantive findings means the pass was shallow.
- State plainly what the change gets right, so the next reader does not re-litigate it.

## Output

Write the review to `docs/reviews/phaseB-code-review.md` and change no other file. Structure: verdict
paragraph (fit for an enterprise security review — yes or no, and the two decisive reasons), a findings
table (id, severity, file:line, one line), each finding in full, what it gets right, and anything §3 asks
for that is missing.
