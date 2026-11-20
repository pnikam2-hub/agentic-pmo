# PHASE C round C1 — audit tamper-evidence

Repository: /root/projects/agentic-pmo at 0.2.0, 167 tests green. This is the first Phase C item and the one
both review passes named as next: `audit_logs` is an ordinary mutable table, so nothing currently detects a
row that was edited or deleted after the fact.

Read `backend/audit.py`, the `AuditLog` model, `backend/routers/admin.py` (the audit query), and
`docs/sso-rbac-phaseA-report.md` §6.

## The constraint that shapes the design

There is no migration tool: `Base.metadata.create_all()` can only create tables. **No column may be added to
`audit_logs`.** Tamper-evidence therefore lives in a *new* table written in the same transaction as the audit
row.

## What to build

### 1. `AuditChain` — a new model, appended to `backend/models.py`

`id` (pk), `seq` (int, unique, not null), `audit_id` (int, not null), `prev_hash` (str 64), `hash` (str 64),
`at` (datetime, default utcnow). No foreign key to `audit_logs`: the chain must outlive anything, exactly as
the audit row itself does.

### 2. `audit()` writes the chain link, atomically

Keep `audit(db, ...)` as the single writer. After adding the audit row it must:

- flush to get the audit id (the caller's `db.flush()` pattern already exists elsewhere);
- read the current head: the chain row with the greatest `seq` (0 rows → genesis);
- compute `hash = sha256(prev_hash || canonical_payload)` where `canonical_payload` is a canonical JSON dump
  (`sort_keys=True`, `separators=(",", ":")`, `default=str`) of: audit id, `at` as ISO-8601, actor,
  actor_role, action, target_type, target_id, `detail`, ip;
- insert the chain row with `seq = head.seq + 1`.

Genesis: `prev_hash = "0" * 64`, `seq = 1`. Do not commit inside `audit()` — it still belongs to the caller's
transaction, so the audit row and its link land together or not at all.

Document in the docstring precisely what this does and does not prove: it detects an edit, an insertion or a
gap **within** the chain; it cannot detect deletion of a *suffix* (the last N rows) unless an external anchor
exists, which is why §4 below writes one.

### 3. `backend/audit_chain.py` — verify and head

- `head(db)` → `(seq, hash)` or `(0, genesis)`.
- `verify(db, limit=5000)` → a dict: `{"ok": bool, "checked": int, "unchained": int, "broken_at": seq|None,
  "reason": str|None, "head": {"seq": int, "hash": str}}`.
  Walk the chain newest→oldest (or oldest→newest, capped by `limit`) and check: the recomputed hash matches
  the stored one, `prev_hash` matches the previous row's `hash`, `seq` is contiguous, and the joined audit row
  still exists with the fields that went into the hash.
  `unchained` counts audit rows created before this round existed (audit id with no chain row) — report them
  as pre-chain, **not** as tampering: a deployment upgrading today has history that was never chained, and a
  verifier that calls that "broken" would be useless on the first run.
- `anchor_path()` — `AUDIT_ANCHOR_PATH`, optional.
- `append_anchor(db)` — append `"<iso8601>\t<seq>\t<hash>\n"` to that path when set, opening with
  `O_APPEND|O_CREAT`, mode `0o600`. A missing directory is an error worth raising, not swallowing.
- `check_anchor(db)` → compares the DB head against the last line of the anchor file: `{"configured": bool,
  "match": bool, "anchor_seq": int|None, "db_seq": int}`. A DB head **behind** the anchor means a suffix was
  deleted — that is the case the chain alone cannot see.

### 4. Where the anchor is written

Call `append_anchor` from application startup after `init_db()` (so each process start records the head it
inherited), and from the verify endpoint after a successful check. Never from `audit()` — anchoring on every
row would serialise writes for no extra detection.

### 5. Admin endpoints (`backend/routers/admin.py`, admin-only like the rest)

- `GET /api/admin/audit/verify` → `verify(...)` merged with `check_anchor(...)`.
- `GET /api/admin/audit/head` → the head plus whether an anchor is configured.

Both are read-only and must not be able to raise a 500 on an empty or pre-chain database.

### 6. Tests — `backend/tests/test_audit_chain.py` (new)

1. writing N audit rows produces a contiguous chain, `verify` is ok, `checked == N`.
2. editing a row's `detail` directly in the database makes `verify` report `ok == False` with `broken_at` at
   that row's seq (the recomputed hash no longer matches).
3. deleting a chain row in the middle reports a broken chain at the gap.
4. deleting the **last two** audit rows and their chain rows still verifies `ok == True` — and, with
   `AUDIT_ANCHOR_PATH` set to a tmp file and an anchor written first, `check_anchor` reports the head behind
   the anchor (the truncation the chain cannot see).
5. an unchained pre-existing audit row is reported as `unchained == 1` and does **not** fail the check.
6. the audit row and its chain row are atomic: if the transaction is rolled back, neither is stored (use a
   deliberate failure after `audit(...)`, e.g. a `db.rollback()`).
7. `audit()` still raises `ValueError` for an action outside `ACTIONS`, and no chain row is written for it.
8. the endpoints 403 for viewer/contributor/pmo_lead and 200 for admin.

Use a tmp anchor path via `monkeypatch.setenv` — never write into the repo or a real `/var` path in a test.

## Constraints

- New table only; no change to `audit_logs` or any other existing table. No new dependency.
- `audit()` stays the only writer of both rows; nothing may bypass it.
- No secret, token or hash of a secret goes into `detail` (unchanged rule) — chain hashes are fine.
- The full suite (167 + new) stays green. British spelling, comments that say why.
- No commit.

## When you are done

1. `.venv/bin/python -m pytest backend/tests -q` and `... test_audit_chain.py -q` — paste both.
2. `.venv/bin/python -c "import backend.main"`.
3. A short report: the hash payload exactly as implemented, what the chain detects versus what only the anchor
   detects, the sequence of an empty database, and anything you could not do. Do not write a report file.
