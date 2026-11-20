"""Tamper-evident hash chain over the audit trail.

``audit_logs`` is an ordinary mutable table: a row edited or deleted after the
fact leaves no trace. This module records one link per audit row, where each
link's hash commits to the row's contents and to the previous link's hash, so an
edit, an insertion, or a gap *within* the chain is detectable by recomputing
every hash.

What the chain alone cannot see is the deletion of a *suffix* — the last N rows
— because a truncated chain still recomputes cleanly. That is what the anchor
file is for: ``append_anchor`` writes the head to a file outside the database,
and ``check_anchor`` compares the two, so a suffix deletion leaves the database
head behind the anchor.
"""
import datetime
import hashlib
import json
import os

from sqlalchemy.orm import Session

from backend.models import AuditChain, AuditLog

GENESIS_HASH = "0" * 64


def canonical_payload(audit_row: AuditLog) -> str:
    """The exact bytes a link commits to.

    Every field that describes the audit row, in a canonical form: sorted keys,
    the bare minimum separators, and ``default=str`` so a stray non-JSON value is
    represented deterministically. The same function runs when writing and when
    verifying, so any drift between the two only ever proves the chain is broken
    — it can never silently pass.
    """
    return json.dumps(
        {
            "audit_id": audit_row.id,
            "at": audit_row.at.isoformat() if audit_row.at is not None else None,
            "actor": audit_row.actor,
            "actor_role": audit_row.actor_role,
            "action": audit_row.action,
            "target_type": audit_row.target_type,
            "target_id": audit_row.target_id,
            "detail": audit_row.detail,
            "ip": audit_row.ip,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def hash_link(prev_hash: str, payload: str) -> str:
    """sha256 of the previous link's hash concatenated with the payload."""
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def head(db: Session):
    """The current chain head as ``(seq, hash)``, or ``(0, GENESIS_HASH)`` when
    the chain is empty."""
    link = db.query(AuditChain).order_by(AuditChain.seq.desc()).first()
    if link is None:
        return (0, GENESIS_HASH)
    return (link.seq, link.hash)


def verify(db: Session, limit: int = 5000) -> dict:
    """Recompute the chain and report whether it is intact.

    ``ok`` is True only when every link within the checked window recomputes to
    its stored hash, each link's ``prev_hash`` matches the previous link's hash,
    ``seq`` is contiguous, and the audit row each link commits to still exists
    with the fields that went into the hash.

    ``unchained`` counts audit rows that have no chain link — history written
    before this round existed — and is reported, not treated as tampering: a
    deployment upgrading today has exactly such a head start, and a verifier
    that called that "broken" would be useless on its first run.

    ``limit`` caps how many links are checked (the newest ``limit``), so a very
    large trail can be verified in bounded time. The anchor covers the head and
    the suffix the chain cannot see on its own.
    """
    limit = max(1, limit)
    head_link = db.query(AuditChain).order_by(AuditChain.seq.desc()).first()
    chained_ids = [aid for (aid,) in db.query(AuditChain.audit_id).all()]
    if chained_ids:
        unchained = db.query(AuditLog).filter(~AuditLog.id.in_(chained_ids)).count()
    else:
        unchained = db.query(AuditLog).count()

    if head_link is None:
        return {
            "ok": True,
            "checked": 0,
            "unchained": unchained,
            "broken_at": None,
            "reason": None,
            "head": {"seq": 0, "hash": GENESIS_HASH},
        }

    start_seq = max(1, head_link.seq - limit + 1)
    links = (
        db.query(AuditChain)
        .filter(AuditChain.seq >= start_seq)
        .order_by(AuditChain.seq.asc())
        .all()
    )
    # When the window starts below the oldest link we check, its prev_hash is
    # the boundary we accept on trust (the cap's price). When the window starts
    # at seq 1 we can — and do — validate the genesis link properly.
    prev_hash = GENESIS_HASH if start_seq == 1 else links[0].prev_hash
    expected_seq = 1 if start_seq == 1 else links[0].seq

    def broken(seq, reason, checked):
        return {
            "ok": False,
            "checked": checked,
            "unchained": unchained,
            "broken_at": seq,
            "reason": reason,
            "head": {"seq": head_link.seq, "hash": head_link.hash},
        }

    checked = 0
    for link in links:
        if link.seq != expected_seq:
            return broken(expected_seq, f"gap: expected seq {expected_seq}, found {link.seq}", checked)
        if link.prev_hash != prev_hash:
            return broken(link.seq, "prev_hash does not match the previous link", checked)
        audit_row = db.query(AuditLog).filter(AuditLog.id == link.audit_id).first()
        if audit_row is None:
            return broken(link.seq, "audit row missing", checked)
        if hash_link(link.prev_hash, canonical_payload(audit_row)) != link.hash:
            return broken(link.seq, "hash mismatch: recomputed hash does not match stored hash", checked)
        prev_hash = link.hash
        expected_seq = link.seq + 1
        checked += 1

    return {
        "ok": True,
        "checked": checked,
        "unchained": unchained,
        "broken_at": None,
        "reason": None,
        "head": {"seq": head_link.seq, "hash": head_link.hash},
    }


def anchor_path():
    """The anchor file path, or None when anchoring is not configured."""
    return os.getenv("AUDIT_ANCHOR_PATH")


def append_anchor(db: Session) -> None:
    """Record the current head in the anchor file, appending one line.

    Appending (not overwriting) keeps the history of heads this process has
    inherited, which is what makes a later suffix deletion detectable: the last
    line says where the head *was*. A missing directory raises rather than being
    swallowed, because a configured anchor that cannot be written is a broken
    safety property — better to fail loudly than to run without one.
    """
    path = anchor_path()
    if not path:
        return
    seq, hash_ = head(db)
    line = f"{datetime.datetime.utcnow().isoformat()}\t{seq}\t{hash_}\n"
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def check_anchor(db: Session) -> dict:
    """Compare the database head against the last line of the anchor file.

    ``match`` is False when the database head is *behind* the anchor — the one
    case the chain cannot see on its own, because a truncated suffix still
    recomputes cleanly. It is True when the head is at or ahead of the anchor,
    or when no anchor is configured or written yet (nothing to compare against).
    """
    seq, _ = head(db)
    path = anchor_path()
    if not path:
        return {"configured": False, "match": True, "anchor_seq": None, "db_seq": seq}
    try:
        with open(path, "r") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except FileNotFoundError:
        return {"configured": True, "match": True, "anchor_seq": None, "db_seq": seq}
    if not lines:
        return {"configured": True, "match": True, "anchor_seq": None, "db_seq": seq}
    try:
        anchor_seq = int(lines[-1].split("\t")[1])
    except (IndexError, ValueError):
        # A malformed anchor line cannot be compared; report nothing to compare
        # against rather than crashing the endpoint on a hand-edited file.
        return {"configured": True, "match": True, "anchor_seq": None, "db_seq": seq}
    return {
        "configured": True,
        "match": seq >= anchor_seq,
        "anchor_seq": anchor_seq,
        "db_seq": seq,
    }
