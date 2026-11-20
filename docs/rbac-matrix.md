# Access control matrix — Agentic PMO v0.2.0

One page for a security questionnaire. It states what the code enforces, where it enforces it, and what is
deliberately out of scope.

## 1. Roles

Four cumulative roles. There is no per-project ACL in v1: a role is global to the deployment.

| Role | Intended holder |
|---|---|
| `viewer` | Client stakeholder, auditor, observer |
| `contributor` | Delivery team member (works the plan, does not shape it) |
| `pmo_lead` | PMO lead / project manager (shapes the plan, runs the agents) |
| `admin` | Platform owner (manages people and the record) |

## 2. Capabilities

| Capability | viewer | contributor | pmo_lead | admin |
|---|---|---|---|---|
| Read projects, tasks, dashboard, domain packs, templates, Plane status, agent log | ✔ | ✔ | ✔ | ✔ |
| Move a task between statuses; log actual hours | — | ✔ | ✔ | ✔ |
| Edit any other task field (title, assignee, estimate, priority, dependencies) | — | — | ✔ | ✔ |
| Create / edit projects and tasks; run Plan, Monitor and Alert agents; acknowledge agent recommendations | — | — | ✔ | ✔ |
| Apply a template or a domain pack; attach/detach a pack | — | — | ✔ | ✔ |
| Link, push, sync or reconcile with Plane; register alert webhooks | — | — | ✔ | ✔ |
| Delete a project | — | — | — | ✔ |
| Create users, change roles, deactivate, reset passwords; read and verify the audit trail | — | — | — | ✔ |
| Change your own password | ✔ | ✔ | ✔ | ✔ |

The three cells that go beyond the four-role table in the plan are deliberate and documented in
`docs/sso-rbac-phaseA-report.md` §2: project deletion is admin-only (it cascades and cannot be undone),
acknowledging an agent recommendation is contributor-level (it records a decision, it does not edit the plan),
and alert-webhook registration is lead-level (an outbound webhook moves alert payloads off-site).

## 3. Where it is enforced

| Boundary | Mechanism |
|---|---|
| Every HTTP route | Router-level dependency plus a per-route guard: `any_role`, `contributor_up`, `pmo_lead_up`, `admin_only` |
| Identity | One function, `current_user`, resolves a bearer token to a user. Every guard depends on it, so there is one place to audit and one place to change |
| The role itself | Read from the database on every request, never trusted from the JWT `role` claim (the claim is for display only) |
| Task field writes | The contributor field rule is enforced in the handler, after the role guard: `status` and `actual_hours` only |
| The browser | `data-requires` hides controls a role cannot use. **Presentation only** — the server refuses the call regardless |
| Plane webhook | HMAC signature only, no user, no role — intended for machine delivery |

## 4. Session model

- Token: HS256 JWT, claims `sub`, `usr`, `role`, `ver`, `iss="agentic-pmo"`, `iat`, `exp`. Lifetime from
  `JWT_EXPIRY_HOURS`, default 8.
- Revocation: the user row carries `token_version`, mirrored in the token. A password change, a role change or
  a deactivation increments it, so **every live token for that user dies immediately**. There is no
  per-token revocation list in v1 (no `jti`), so a stolen token is usable until it expires — mitigated by the
  8-hour lifetime and by roles being re-read from the database on each request.
- Local accounts: bcrypt, 12-character minimum and a 72-byte ceiling, with a dummy comparison on unknown or
  inactive identifiers so login timing does not disclose whether an account exists.
- SSO (OIDC): id token verified against the provider JWKS (RS256 pinned, `iss`, `aud` + `azp`, `exp`, `iat`,
  constant-time `nonce`); the browser receives a single-use 120-second handoff, exchanged for the session
  token. An account matched by verified email is **linked and keeps its role** — SSO proves identity, it does
  not grant or remove authority. Local login stays available by default so a provider outage cannot lock the
  owner out; setting `LOCAL_LOGIN_ENABLED=0` makes the app refuse to start unless SSO is fully configured.
- Last administrator: the admin API and the SSO path both refuse any change that would leave no active admin,
  re-checked after the mutation and before commit.

## 5. Audit

Every security-relevant event writes a row: logins (success and failure), role and password changes, user
creation and deactivation, project create/update/delete, task deletion, agent runs, Plane link/push/sync, and
every refused request (`access_denied`, with method, path and the roles required). Rows hold the actor, the
actor's role at the time, the action, the target and a JSON detail; **no password, hash, token, code or
verifier is ever stored**.

The trail is tamper-evident: each row is hash-chained to its predecessor in a separate table, and an optional
external anchor file records the chain head so a truncated tail is detectable. `GET /api/admin/audit/verify`
reports the result.

## 6. Deliberately out of scope in v1

| Not built | Why | Consequence to accept |
|---|---|---|
| Per-project ACLs | Doubling the matrix before anyone has used the four roles is how permission systems become unusable | A viewer sees every project in the deployment |
| SCIM provisioning | SSO login-time provisioning covers the need until a client asks for lifecycle sync | Deprovisioning is manual |
| Multi-factor authentication of our own | It is the identity provider's job once SSO is on; building it locally would be worse | Local accounts are single-factor — use SSO where MFA matters |
| Refresh tokens / per-token revocation | `token_version` gives coarse, immediate revocation | A stolen token lives until expiry (≤ 8 h) |
| SAML | A new decision with its own cost; all major providers speak OIDC | A WAS-tied client would need a separate build |

## 7. Questions this matrix answers, in order

1. *Can a read-only user change anything?* No — 403 at the server on every write route; the UI hides the
   controls as well.
2. *Can a user act with a role they no longer hold?* No — the role is re-read from the database per request and
   a role change bumps `token_version`.
3. *Can a deactivated user keep working?* No — the token is rejected and login is refused.
4. *Can the deployment be left with no administrator?* Not through the API or SSO; both paths refuse it.
5. *Who did what, and can the record be edited?* Every event is recorded; rows are hash-chained and the chain
   can be verified on demand.
6. *How does SSO map to roles?* `OIDC_ROLE_MAP` (group → role, with a wildcard and a default of `viewer`); an
   unknown mapped value degrades to `viewer` and is audited.
