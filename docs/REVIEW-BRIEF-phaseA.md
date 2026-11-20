# gstack review pass — Phase A (authentication and role-based permissions)

Repository: /root/projects/agentic-pmo. Run `/review` against the Phase A change.

## What to review

`git diff 7d0c7aa..HEAD` — three commits that add the `users` and `audit_logs` tables, rewrite
authentication around a single `current_user` resolution point, add token versioning and invalidation,
add the admin user/audit API, put the four-role matrix on every router, write audit rows for the actions
that matter, and make the SPA hide what the caller cannot use.

Read the diff and the files it touches. The governing documents are `docs/sso-rbac-plan.md` (the
specification, with the role matrix in §1 and the acceptance gate in §6), `docs/BUILD-phaseA-r1.md`,
`-r2.md`, `-r3.md` and `-r4.md` (each round's hard constraints). A finding that contradicts a constraint
is still worth raising — say which constraint it collides with and why the constraint is wrong.

## The constraints a reviewer must not "fix" away

- No new dependencies, and no new tables beyond `users` and `audit_logs`. There is no migration tool:
  `Base.metadata.create_all()` cannot alter an existing table, so any "just add a column" advice is
  unbuildable here.
- Four global roles only — viewer, contributor, pmo_lead, admin. Per-project ACLs, SCIM and our own MFA
  are deliberately out of scope for v1.
- The Plane webhook endpoint authenticates by HMAC signature and has no user. It must never gain a role
  dependency.
- Existing tests must keep passing (114 today). A reviewer may propose a test, never the deletion or
  weakening of an assertion that currently encodes a rule.

## What makes this review worth its cost

- **Be adversarial.** Think like an attacker and a chaos engineer: token replay, role change races,
  deactivation while a request is in flight, the last-admin guard under concurrency, the audit trail's
  own integrity, a 403 that leaks information, a timing or enumeration oracle in login, `token_version`
  bypass, SQL or JSON handling in `detail`, the difference between 401 and 403, an over-broad router gate
  on the webhook.
- **Be specific.** Every finding cites `file:line`, states the attacker or failure mode, the consequence,
  and the concrete fix. A finding without a line number is not a finding.
- **Severity vocabulary: `blocker`, `major`, `minor`.** Blockers are things that make the permission model
  wrong or forgeable. Major: incorrect or missing behaviour with a workaround. Minor: polish.
- **If you find fewer than ten substantive findings you have not looked hard enough.** Read every changed
  file rather than skimming the diff, and check what the code does at the edges: an empty users table, a
  deleted user's token, a role changed twice in one request, an audit row whose target has been deleted,
  a `detail` payload that could carry a secret.
- **Verify, don't speculate.** You may run `pytest`, `git`, `grep` and the app against a throwaway
  database (`DATABASE_URL=sqlite:////tmp/review.db`, `ALLOW_INSECURE_DEFAULTS=0`, a strong
  `ADMIN_PASSWORD`, `JWT_SECRET=$(openssl rand -hex 32)`, `PLANE_WEBHOOK_SECRET` set). If a finding
  depends on runtime behaviour, run it. Say "verified by running X" or "not verified" against each.

## Output

Write the complete review to `docs/reviews/phaseA-code-review.md`. Change no other file — no source
edits, no test edits, no new code. The structure:

1. One-paragraph verdict: is this fit to put in front of an enterprise security review, yes or no, and the
   two reasons why.
2. A findings table: id, severity, file:line, one-line summary.
3. Each finding in full: what it is, how it fails, the fix, and whether you verified it.
4. What the change gets right — stated plainly, so the next reader does not re-litigate it.
5. Anything the specification asks for that is missing altogether.

Do not soften the verdict. An agreeable review is worse than none, because it launders an unexamined
change as validated.
