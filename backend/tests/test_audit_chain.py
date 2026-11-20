"""Phase C round 1 — tamper-evident audit chain.

``audit_logs`` is an ordinary mutable table, so nothing in it can prove a row
was not edited or deleted after the fact. These tests exercise the hash chain
that does: every audit row now gets a link whose hash commits to the row and to
the previous link, plus an optional anchor file that catches the one thing the
chain cannot — the deletion of a *suffix*.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import audit as audit_module
from backend import audit_chain
from backend.auth import bootstrap_admin, current_user, require_auth
from backend.database import Base, get_db
from backend.main import app
from backend.models import AuditChain, AuditLog

ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


@pytest.fixture(autouse=True)
def fresh_db():
    """Fresh in-memory tables per test, so no test sees another's chain."""
    Base.metadata.create_all(bind=ENGINE)
    yield
    Base.metadata.drop_all(bind=ENGINE)


def _audit(db, action="login_success", detail=None, **kw):
    """Write one audit row through the real writer, with defaults that make the
    payload deterministic and independent of the caller's setup."""
    return audit_module.audit(
        db,
        actor=kw.get("actor", "alice"),
        actor_role=kw.get("actor_role", "admin"),
        action=action,
        target_type=kw.get("target_type", "user"),
        target_id=kw.get("target_id", "1"),
        detail=detail if detail is not None else {"n": 1},
        ip=kw.get("ip", "127.0.0.1"),
    )


def _write_n(db, n):
    for i in range(n):
        _audit(db, detail={"n": i})
    db.commit()


# ── 1. a fresh trail is contiguous and verifies cleanly ──────────────────────
def test_chain_is_contiguous_and_verifies(fresh_db):
    n = 5
    with SessionLocal() as db:
        _write_n(db, n)

    with SessionLocal() as db:
        result = audit_chain.verify(db)
    assert result["ok"] is True
    assert result["checked"] == n
    assert result["unchained"] == 0
    assert result["broken_at"] is None
    assert result["head"]["seq"] == n

    with SessionLocal() as db:
        seqs = [s for (s,) in db.query(AuditChain.seq).order_by(AuditChain.seq).all()]
    assert seqs == list(range(1, n + 1))


# ── 2. editing a row's detail breaks the chain at that seq ───────────────────
def test_editing_detail_breaks_chain(fresh_db):
    n = 4
    with SessionLocal() as db:
        _write_n(db, n)

    # Tamper with the row behind chain seq 2, straight in the database.
    with SessionLocal() as db:
        link = db.query(AuditChain).filter(AuditChain.seq == 2).one()
        audit_row = db.query(AuditLog).filter(AuditLog.id == link.audit_id).one()
        audit_row.detail = {"n": 999}
        db.commit()

    with SessionLocal() as db:
        result = audit_chain.verify(db)
    assert result["ok"] is False
    assert result["broken_at"] == 2


# ── 3. a missing middle link is a gap, reported at the missing seq ───────────
def test_deleting_middle_chain_row_reports_gap(fresh_db):
    n = 5
    with SessionLocal() as db:
        _write_n(db, n)

    with SessionLocal() as db:
        link = db.query(AuditChain).filter(AuditChain.seq == 3).one()
        db.delete(link)
        db.commit()

    with SessionLocal() as db:
        result = audit_chain.verify(db)
    assert result["ok"] is False
    assert result["broken_at"] == 3


# ── 4. a truncated suffix still verifies; only the anchor catches it ─────────
def test_suffix_deletion_needs_the_anchor(fresh_db, tmp_path, monkeypatch):
    anchor = tmp_path / "anchor.txt"
    n = 5
    with SessionLocal() as db:
        _write_n(db, n)

    monkeypatch.setenv("AUDIT_ANCHOR_PATH", str(anchor))
    with SessionLocal() as db:
        audit_chain.append_anchor(db)

    # Delete the last two audit rows and their links — the truncation a hash
    # chain cannot see, because what remains is still a clean, shorter chain.
    with SessionLocal() as db:
        head_seq, _ = audit_chain.head(db)
        for seq in (head_seq, head_seq - 1):
            link = db.query(AuditChain).filter(AuditChain.seq == seq).one()
            audit_row = db.query(AuditLog).filter(AuditLog.id == link.audit_id).one()
            db.delete(link)
            db.delete(audit_row)
        db.commit()

    with SessionLocal() as db:
        verified = audit_chain.verify(db)
        anchored = audit_chain.check_anchor(db)

    assert verified["ok"] is True
    assert verified["head"]["seq"] == n - 2
    assert anchored["configured"] is True
    assert anchored["match"] is False
    assert anchored["anchor_seq"] == n
    assert anchored["db_seq"] == n - 2


# ── 5. pre-existing (pre-chain) rows are reported, not treated as tampering ──
def test_pre_existing_audit_row_is_unchained_not_broken(fresh_db):
    # Insert an audit row directly, bypassing the writer, as history from before
    # this round would look — no chain link was ever made for it.
    with SessionLocal() as db:
        db.add(AuditLog(actor="legacy", actor_role="admin", action="login_success",
                        detail={}))
        db.commit()

    with SessionLocal() as db:
        result = audit_chain.verify(db)
    assert result["ok"] is True
    assert result["checked"] == 0
    assert result["unchained"] == 1


# ── 6. the audit row and its link are atomic ─────────────────────────────────
def test_audit_and_link_are_atomic(fresh_db):
    with SessionLocal() as db:
        _audit(db)
        db.rollback()   # a deliberate failure after audit() — nothing may land

    with SessionLocal() as db:
        assert db.query(AuditLog).count() == 0
        assert db.query(AuditChain).count() == 0


# ── 7. an unknown action still raises, and writes no link ────────────────────
def test_unknown_action_raises_and_writes_nothing(fresh_db):
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            _audit(db, action="not_a_real_action")
        db.commit()

    with SessionLocal() as db:
        assert db.query(AuditLog).count() == 0
        assert db.query(AuditChain).count() == 0


# ── 8. the endpoints are admin-only ──────────────────────────────────────────
def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def roles():
    """Real auth for one test: removes test_api.py's session-scoped stand-ins so
    the real admin_only guard runs, and points get_db at this module's engine."""
    saved = {
        current_user: app.dependency_overrides.pop(current_user, None),
        require_auth: app.dependency_overrides.pop(require_auth, None),
    }
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=ENGINE)

    client = TestClient(app)
    with SessionLocal() as db:
        bootstrap_admin(db)

    admin = client.post("/api/auth/login", json={"identifier": "admin", "password": "admin"})
    assert admin.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin.json()['token']}"}
    identities = {"admin": {"headers": admin_headers}}

    for username, password in (
        ("viewer", "viewer-password"),
        ("contributor", "contributor-password"),
        ("pmo_lead", "pmo-lead-password"),
    ):
        created = client.post("/api/admin/users", json={
            "username": username,
            "email": f"{username}@example.com",
            "display_name": username.title(),
            "role": username,
            "password": password,
        }, headers=admin_headers)
        assert created.status_code == 200
        login = client.post("/api/auth/login", json={"identifier": username, "password": password})
        assert login.status_code == 200
        identities[username] = {"headers": {"Authorization": f"Bearer {login.json()['token']}"}}

    yield client, identities

    Base.metadata.drop_all(bind=ENGINE)
    app.dependency_overrides.pop(get_db, None)
    if previous_db is not None:
        app.dependency_overrides[get_db] = previous_db
    for dep, impl in saved.items():
        if impl is not None:
            app.dependency_overrides[dep] = impl


def test_endpoints_are_admin_only(roles):
    client, identities = roles
    for name in ("viewer", "contributor", "pmo_lead"):
        assert client.get("/api/admin/audit/verify", headers=identities[name]["headers"]).status_code == 403
        assert client.get("/api/admin/audit/head", headers=identities[name]["headers"]).status_code == 403
    assert client.get("/api/admin/audit/verify", headers=identities["admin"]["headers"]).status_code == 200
    assert client.get("/api/admin/audit/head", headers=identities["admin"]["headers"]).status_code == 200
