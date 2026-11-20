"""Phase C round 3 — the audit export CSV.

``GET /api/admin/audit/export.csv`` turns the trail into a spreadsheet-ready
RFC 4180 file. Like test_rbac.py this drives the real auth chain end to end —
real logins, real guards, real audit rows — so it removes test_api.py's
session-scoped stand-ins for current_user/require_auth and points get_db at its
own in-memory engine, exactly as test_rbac.py does.
"""
import csv
import datetime
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import bootstrap_admin, current_user, require_auth
from backend.database import Base, get_db
from backend.main import app
from backend.models import AuditLog
from backend.routers.admin import CSV_COLUMNS, _csv_field

ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def _real_deps():
    """Fresh tables plus the real auth chain, per test (see test_rbac.py)."""
    saved = {
        current_user: app.dependency_overrides.pop(current_user, None),
        require_auth: app.dependency_overrides.pop(require_auth, None),
    }
    previous_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=ENGINE)
    yield
    Base.metadata.drop_all(bind=ENGINE)
    app.dependency_overrides.pop(get_db, None)
    if previous_db is not None:
        app.dependency_overrides[get_db] = previous_db
    for dep, impl in saved.items():
        if impl is not None:
            app.dependency_overrides[dep] = impl


def login(identifier, password):
    return client.post("/api/auth/login", json={
        "identifier": identifier, "password": password,
    })


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def parse_csv(text):
    """Parse the response body as RFC 4180 CSV (universal newlines)."""
    return list(csv.reader(io.StringIO(text, newline="")))


@pytest.fixture()
def roles():
    """Ready-made identities: the bootstrap admin plus one viewer, contributor
    and pmo_lead, each logged in over HTTP so every Authorization header carries
    a real JWT (mirrors test_audit_chain.py)."""
    with SessionLocal() as s:
        bootstrap_admin(s)

    admin = login("admin", "admin")
    assert admin.status_code == 200
    identities = {"admin": {"headers": auth(admin.json()["token"])}}

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
        }, headers=identities["admin"]["headers"])
        assert created.status_code == 200, created.text
        resp = login(username, password)
        assert resp.status_code == 200, resp.text
        identities[username] = {"headers": auth(resp.json()["token"])}
    return identities


def test_export_header_matches_columns(roles):
    """The header row is exactly the published column list, and the response
    carries the spreadsheet-ready content type and an attachment filename."""
    resp = client.get("/api/admin/audit/export.csv", headers=roles["admin"]["headers"])
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert resp.headers["Content-Disposition"].startswith('attachment; filename="audit-')
    assert resp.headers["Cache-Control"] == "no-store"

    rows = parse_csv(resp.text)
    assert rows[0] == list(CSV_COLUMNS)


def test_export_is_one_row_per_entry_newest_first(roles):
    """Every audit entry appears exactly once, newest first, and each detail
    cell parses back to a JSON object."""
    with SessionLocal() as s:
        total = s.query(AuditLog).count()
    assert total > 0

    resp = client.get("/api/admin/audit/export.csv", headers=roles["admin"]["headers"])
    assert resp.status_code == 200
    header, data = parse_csv(resp.text)[0], parse_csv(resp.text)[1:]
    assert header == list(CSV_COLUMNS)
    # One row per entry — the export row it writes for itself is excluded.
    assert len(data) == total

    ids = [int(r[1]) for r in data]
    assert ids == sorted(ids, reverse=True)   # newest first

    for r in data:
        assert isinstance(json.loads(r[-1]), dict)   # detail is valid JSON


def test_detail_with_comma_quote_newline_round_trips(roles):
    """A detail whose value holds a comma, a double quote and a newline survives
    the quoting and comes back identical — and the quoting rule for a literal
    newline or leading/trailing space is exercised directly."""
    name = 'a,b"c\nd'   # comma, double quote, newline
    project = client.post("/api/projects", json={"name": name},
                          headers=roles["pmo_lead"]["headers"])
    assert project.status_code == 200

    resp = client.get("/api/admin/audit/export.csv", headers=roles["admin"]["headers"])
    assert resp.status_code == 200
    rows = parse_csv(resp.text)
    created = [r for r in rows[1:] if r[5] == "project_created"][0]
    assert json.loads(created[-1])["name"] == name

    # The RFC 4180 rules the round-trip above does not touch (a literal newline
    # and leading/trailing whitespace are escaped away by JSON, so they only
    # occur in other columns — but the quoting must still handle them).
    assert _csv_field('he said "hi"') == '"he said ""hi"""'
    assert _csv_field("two\nlines") == '"two\nlines"'
    assert _csv_field(" padded ") == '" padded "'
    assert _csv_field("plain") == "plain"


def test_limit_and_since_filter(roles):
    """limit caps the row count and out-of-range limits are 422; since keeps
    only rows at or after the given ISO date and a bad since is 422."""
    admin_headers = roles["admin"]["headers"]

    assert client.get("/api/admin/audit/export.csv?limit=0",
                      headers=admin_headers).status_code == 422
    assert client.get("/api/admin/audit/export.csv?limit=50001",
                      headers=admin_headers).status_code == 422

    resp = client.get("/api/admin/audit/export.csv?limit=2", headers=admin_headers)
    assert resp.status_code == 200
    assert len(parse_csv(resp.text)) - 1 == 2

    # Pre-chain rows, written straight into the table, so the since filter and
    # the "no link → empty seq/hash/prev_hash" behaviour are both covered.
    with SessionLocal() as s:
        s.add(AuditLog(actor="t", action="old_row",
                       at=datetime.datetime(2020, 1, 1), detail={"m": "old"}))
        s.add(AuditLog(actor="t", action="future_row",
                       at=datetime.datetime(2099, 1, 1), detail={"m": "future"}))
        s.commit()

    resp = client.get("/api/admin/audit/export.csv?since=2025-01-01",
                      headers=admin_headers)
    assert resp.status_code == 200
    data = parse_csv(resp.text)[1:]
    actions = {r[5] for r in data}
    assert "future_row" in actions
    assert "old_row" not in actions

    future = [r for r in data if r[5] == "future_row"][0]
    assert future[2] == ""   # seq — pre-chain, left empty rather than invented
    assert future[9] == ""   # hash
    assert future[10] == ""  # prev_hash

    assert client.get("/api/admin/audit/export.csv?since=not-a-date",
                      headers=admin_headers).status_code == 422


def test_export_is_admin_only(roles):
    """Viewer, contributor and pmo_lead are refused; only admin gets a file."""
    for name in ("viewer", "contributor", "pmo_lead"):
        resp = client.get("/api/admin/audit/export.csv",
                          headers=roles[name]["headers"])
        assert resp.status_code == 403, f"{name} should be refused"
    assert client.get("/api/admin/audit/export.csv",
                      headers=roles["admin"]["headers"]).status_code == 200


def test_export_writes_one_audit_exported_row_not_in_file(roles):
    """Exporting the trail is itself audited exactly once, and the row it writes
    does not appear in the file it describes."""
    admin_headers = roles["admin"]["headers"]
    with SessionLocal() as s:
        assert s.query(AuditLog).filter(AuditLog.action == "audit_exported").count() == 0

    resp = client.get("/api/admin/audit/export.csv", headers=admin_headers)
    assert resp.status_code == 200
    data = parse_csv(resp.text)[1:]
    assert "audit_exported" not in {r[5] for r in data}

    with SessionLocal() as s:
        exported = s.query(AuditLog).filter(AuditLog.action == "audit_exported").all()
    assert len(exported) == 1
    assert exported[0].detail["count"] == len(data)
    assert exported[0].detail["limit"] == 5000
    assert exported[0].detail["since"] is None
