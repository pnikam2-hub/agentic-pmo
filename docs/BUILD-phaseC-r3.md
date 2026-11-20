# PHASE C round C3 — the audit export, and the paperwork a questionnaire asks for

Repository: /root/projects/agentic-pmo at 0.2.0+, 187 tests green, audit chain and hardening in place.
Read `backend/routers/admin.py`, `backend/audit_chain.py`, `docs/rbac-matrix.md`.

Two deliverables: an audit export an auditor can open in a spreadsheet, and the README brought up to date so
the security posture is discoverable without reading the code.

## 1. `GET /api/admin/audit/export.csv` (admin only)

- One row per audit entry, newest first, columns in this order:
  `at, id, seq, actor, actor_role, action, target_type, target_id, ip, hash, prev_hash, detail`.
- `seq`, `hash` and `prev_hash` come from the chain; a row with no link (pre-chain history) leaves them empty
  rather than inventing values.
- `detail` is the JSON object serialised compactly (no newlines). The whole file must be RFC 4180: quote any
  field containing a comma, quote, newline or leading/trailing space; escape an embedded quote by doubling it.
  Write the quoting yourself — `csv` from the stdlib is fine and is not a new dependency.
- `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="audit-<UTC
  timestamp>.csv"`, and `Cache-Control: no-store` (the middleware already adds that for `/api/`; do not fight
  it).
- Query parameters: `limit` (default 5000, max 50000) and `since` (ISO date, optional). Reject a bad `since`
  with 422, and reject `limit` outside the range with 422 — not by silently clamping.
- Record the export itself: write an `audit_exported` row (new action) **before** streaming, with the row
  count exported and the filters used. Exporting the trail is a security event; it must not be the one thing
  the trail does not know about. Take care that the export does not then include a row written after it
  counted — read head, write the export row, then stream up to the head you read.
- Do it without loading the whole trail into memory in one list where you reasonably can: a `yield`-based
  generator response is fine, and say in a comment that the row cap is what bounds the work.

## 2. Tests (`backend/tests/test_audit_export.py`, new)

1. admin gets a CSV whose header row matches the column list exactly.
2. one row per audit entry, newest first, and `detail` is valid JSON when parsed back.
3. a `detail` containing a comma, a double quote and a newline round-trips through the quoting correctly
   (create one through a task title or an identifier; assert by parsing the CSV back with `csv.reader`).
4. `limit` and `since` filter as documented; a bad `since` and an out-of-range `limit` are 422.
5. viewer, contributor and pmo_lead get 403.
6. the export writes exactly one `audit_exported` row, and that row is **not** in the file it describes.

## 3. README

Add a `## Security` section (after `## Roles and permissions`) that links `docs/rbac-matrix.md` and states, in
a short table, what is enforced where: four roles on every route, hash-chained audit with an anchor,
per-identifier login lockout, zxcvbn password policy, response headers, SSO with local fallback, and the
deliberate exclusions (per-project ACLs, SCIM, our own MFA, SAML). Link
`docs/sso-rbac-phaseA-report.md` and `docs/sso-rbac-phaseB-report.md` rather than repeating them.

Also add the two new endpoints to the administration table: `/api/admin/audit/verify` and
`/api/admin/audit/export.csv`.

## Constraints

- No new dependency. No schema change. Admin-only on the new route.
- No secret may reach the CSV — the same rule as `detail`, and the export is the one artefact most likely to
  be emailed around.
- British spelling, comments that explain why. No commit.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — paste the summary.
2. Show the first three lines of a real export against a throwaway database (run the app, log in as admin,
   curl the endpoint, `head -3`).
3. Report: the exact column list, how the export row avoids describing itself, and anything you could not do.
