"""Phase A release gate — roles, tokens, denials and the audit trail.

test_api.py overrides `current_user` to exercise business logic without a real
token; this file does the opposite. It drives the real dependency chain end to
end — real JWTs from a real login, real guards, real audit rows — because the
role matrix is only worth testing when nothing in the chain is faked.

One deliberate wrinkle: test_api.py installs a session-scoped autouse override
of `current_user`/`require_auth` for its own convenience, and that stand-in is
still installed when this module runs. A fake admin would let every viewer walk
through the very guards this suite exists to prove, so the fixture below removes
the stand-ins (and restores them afterwards) rather than overriding anything.
"""
import json

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth as auth_module
from backend.auth import bootstrap_admin, current_user, require_auth
from backend.database import Base, get_db
from backend.main import app
from backend.models import User
from backend.routers import admin as admin_router
from backend.tests.test_plane_webhook import post as webhook_post

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


# No context manager: startup must not run, so the in-memory database the tests
# build is the only one touched (bootstrap_admin runs from the fixture instead).
client = TestClient(app)


def assert_status(resp, code):
    """Fail with the server's own detail, not just the bare status code — a 403
    carrying a role message is far more useful than "403 != 200"."""
    assert resp.status_code == code, f"expected {code}, got {resp.status_code}: {resp.text}"


def login(identifier, password):
    return client.post("/api/auth/login", json={
        "identifier": identifier, "password": password,
    })


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _real_deps():
    """Fresh tables plus the real auth chain, per test.

    Removes test_api.py's session-scoped stand-ins for current_user/require_auth
    (a fake admin would defeat every refusal below) and points get_db at this
    module's engine, saving the prior state so sibling modules are unaffected.
    """
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


ROLE_USERS = [
    ("viewer", "viewer@example.com", "viewer-password"),
    ("contributor", "contributor@example.com", "contributor-password"),
    ("pmo_lead", "pmo_lead@example.com", "pmo-lead-password"),
]


@pytest.fixture()
def roles():
    """Ready-made identities: the bootstrap admin plus one viewer, contributor
    and pmo_lead, each created through the admin API and logged in over HTTP so
    every Authorization header carries a real JWT."""
    with SessionLocal() as s:
        bootstrap_admin(s)

    admin_resp = login("admin", "admin")
    assert_status(admin_resp, 200)
    admin_headers = auth(admin_resp.json()["token"])

    with SessionLocal() as s:
        admin_id = s.query(User).filter(User.username == "admin").one().id
    identities = {"admin": {"username": "admin", "id": admin_id, "headers": admin_headers}}

    for username, email, password in ROLE_USERS:
        created = client.post("/api/admin/users", json={
            "username": username,
            "email": email,
            "display_name": username.replace("_", " ").title(),
            "role": username,
            "password": password,
        }, headers=admin_headers)
        assert_status(created, 200)
        resp = login(username, password)
        assert_status(resp, 200)
        identities[username] = {
            "username": username,
            "email": email,
            "password": password,
            "id": created.json()["id"],
            "headers": auth(resp.json()["token"]),
        }
    return identities


def test_bootstrap_admin_creates_exactly_one_user():
    """The env admin is bootstrapped only against an empty table; a second call
    creates nothing, so a restart never duplicates or overwrites the account."""
    with SessionLocal() as s:
        assert s.query(User).count() == 0
        first = bootstrap_admin(s)
        assert first is not None
        assert first.role == "admin"
        assert s.query(User).count() == 1

        again = bootstrap_admin(s)
        assert again is None
        assert s.query(User).count() == 1


def test_login_by_username_email_and_inactive_user(roles):
    """Login accepts a username or an email alike; a wrong password and an
    inactive user return the same 401, so the response does not reveal whether
    the account exists."""
    assert_status(login("contributor", "contributor-password"), 200)
    assert_status(login("viewer@example.com", "viewer-password"), 200)

    wrong = login("viewer", "not-the-password")
    assert_status(wrong, 401)

    resp = client.patch(f"/api/admin/users/{roles['viewer']['id']}",
                        json={"is_active": False}, headers=roles["admin"]["headers"])
    assert_status(resp, 200)

    inactive = login("viewer", "viewer-password")
    assert_status(inactive, 401)
    assert inactive.json()["detail"] == wrong.json()["detail"]


def test_stale_token_and_deactivation_kill_live_tokens(roles):
    """A token is only valid while its user's version matches and the user is
    active; bumping the version or deactivating the user turns a live token into
    a 401 and locks the account out of login."""
    viewer_headers = roles["viewer"]["headers"]

    with SessionLocal() as s:
        viewer = s.query(User).filter(User.username == "viewer").one()
        viewer.token_version += 1
        s.commit()

    assert_status(client.get("/api/projects", headers=viewer_headers), 401)

    fresh = login("viewer", "viewer-password")
    assert_status(fresh, 200)
    fresh_headers = auth(fresh.json()["token"])
    assert_status(client.get("/api/projects", headers=fresh_headers), 200)

    resp = client.patch(f"/api/admin/users/{roles['viewer']['id']}",
                        json={"is_active": False}, headers=roles["admin"]["headers"])
    assert_status(resp, 200)

    assert_status(client.get("/api/projects", headers=fresh_headers), 401)
    assert_status(login("viewer", "viewer-password"), 401)


def test_role_boundaries_on_writes(roles):
    """Viewer reads but cannot move a task; contributor may move a task and log
    hours but cannot create a project or touch any other task field; pmo_lead
    can create a project."""
    project = client.post("/api/projects", json={"name": "Boundary"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]

    task = client.post(f"/api/projects/{pid}/tasks", json={"title": "Move me"},
                       headers=roles["pmo_lead"]["headers"])
    assert_status(task, 200)
    tid = task.json()["id"]

    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"status": "in_progress"},
                               headers=roles["viewer"]["headers"]), 403)
    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"status": "in_progress"},
                               headers=roles["contributor"]["headers"]), 200)

    assert_status(client.post("/api/projects", json={"name": "Forbidden"},
                              headers=roles["contributor"]["headers"]), 403)
    assert_status(client.post("/api/projects", json={"name": "Allowed"},
                              headers=roles["pmo_lead"]["headers"]), 200)

    # a contributor may send status and actual_hours, and nothing else
    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"status": "done", "actual_hours": 12.5},
                               headers=roles["contributor"]["headers"]), 200)
    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"title": "Renamed by a contributor"},
                               headers=roles["contributor"]["headers"]), 403)

    task_after = client.get(f"/api/projects/{pid}/tasks/{tid}",
                            headers=roles["viewer"]["headers"])
    assert_status(task_after, 200)
    assert task_after.json()["title"] == "Move me"
    assert task_after.json()["status"] == "done"


def test_admin_surface_and_project_deletion(roles):
    """Only an admin reaches /api/admin/*, and deleting a project is admin-only
    even for a pmo_lead."""
    for name in ("viewer", "contributor", "pmo_lead"):
        assert_status(client.get("/api/admin/users", headers=roles[name]["headers"]), 403)
        assert_status(client.get("/api/admin/audit", headers=roles[name]["headers"]), 403)

    assert_status(client.get("/api/admin/users", headers=roles["admin"]["headers"]), 200)
    assert_status(client.get("/api/admin/audit", headers=roles["admin"]["headers"]), 200)

    project = client.post("/api/projects", json={"name": "Doomed"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]

    assert_status(client.delete(f"/api/projects/{pid}",
                                headers=roles["pmo_lead"]["headers"]), 403)
    assert_status(client.delete(f"/api/projects/{pid}",
                                headers=roles["admin"]["headers"]), 200)


def test_last_active_admin_is_protected(roles):
    """The last active admin cannot be demoted, deactivated or deleted; once a
    second admin exists the first may be demoted."""
    admin_id = roles["admin"]["id"]
    admin_headers = roles["admin"]["headers"]

    assert_status(client.patch(f"/api/admin/users/{admin_id}", json={"role": "viewer"},
                               headers=admin_headers), 400)
    assert_status(client.patch(f"/api/admin/users/{admin_id}", json={"is_active": False},
                               headers=admin_headers), 400)
    assert_status(client.delete(f"/api/admin/users/{admin_id}", headers=admin_headers), 400)

    second = client.post("/api/admin/users", json={
        "username": "admin2", "email": "admin2@example.com", "role": "admin",
        "password": "admin2-password",
    }, headers=admin_headers)
    assert_status(second, 200)

    assert_status(client.patch(f"/api/admin/users/{admin_id}", json={"role": "viewer"},
                               headers=admin_headers), 200)


def test_audit_trail_records_failures_and_denials(roles):
    """A failed login writes login_failed and a role-denied write writes
    access_denied with the path and the caller's role; no audit detail contains
    a password, a bcrypt hash or a token."""
    assert_status(login("viewer", "not-the-password"), 401)

    project = client.post("/api/projects", json={"name": "Audited"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]
    task = client.post(f"/api/projects/{pid}/tasks", json={"title": "T"},
                       headers=roles["pmo_lead"]["headers"])
    assert_status(task, 200)
    tid = task.json()["id"]

    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"status": "done"},
                               headers=roles["viewer"]["headers"]), 403)

    rows = client.get("/api/admin/audit?limit=500", headers=roles["admin"]["headers"]).json()

    assert any(r["action"] == "login_failed" for r in rows)
    denied = [r for r in rows if r["action"] == "access_denied"]
    assert denied, "expected an access_denied audit row"
    d = denied[0]
    assert d["actor"] == "viewer"
    assert d["actor_role"] == "viewer"
    assert d["detail"]["method"] == "PATCH"
    assert d["detail"]["path"] == f"/api/projects/{pid}/tasks/{tid}"
    assert d["detail"]["required_roles"] == ["contributor", "pmo_lead", "admin"]
    assert d["ip"] is not None

    # Secrets are facts that must never be recorded. The demo admin password is
    # literally "admin", indistinguishable from the admin username and role, so
    # it is not a usable marker; the other passwords, bcrypt hashes and JWTs are.
    for r in rows:
        detail = json.dumps(r["detail"])
        for password in ("viewer-password", "contributor-password", "pmo-lead-password",
                         "admin2-password"):
            assert password not in detail
        assert "$2" not in detail      # bcrypt hash prefix
        assert "eyJ" not in detail     # JWT prefix


def test_plane_webhook_accepts_signed_delivery_without_jwt(monkeypatch):
    """The inbound Plane webhook authenticates by HMAC signature, not a user
    session, so a correctly signed delivery is accepted with no JWT at all and a
    wrong signature is refused."""
    monkeypatch.setenv("PLANE_WEBHOOK_SECRET", "test-webhook-secret")
    payload = {"event": "module", "action": "updated", "data": {"id": "m1"}}

    assert_status(webhook_post(client, payload), 200)
    assert_status(webhook_post(client, payload, signature="deadbeef"), 401)


# ── F1 — login timing normalisation ────────────────────────────────────────
def test_authenticate_runs_dummy_comparison(monkeypatch):
    """authenticate() runs one bcrypt comparison even for a missing or inactive
    identifier, so the response time does not reveal whether the account
    exists. Deterministic: counts the verify_password calls, not the clock."""
    calls = []
    real_verify = auth_module.verify_password

    def spy(password, hashed):
        calls.append(hashed)
        return real_verify(password, hashed)

    monkeypatch.setattr(auth_module, "verify_password", spy)

    with SessionLocal() as s:
        bootstrap_admin(s)

    with SessionLocal() as s:
        assert auth_module.authenticate("no-such-user", "x", s) is None
    assert len(calls) == 1

    with SessionLocal() as s:
        s.add(User(username="ghost", display_name="Ghost", role="viewer",
                   password_hash=auth_module.hash_password("ghost-password"),
                   is_active=0, source="local"))
        s.commit()

    with SessionLocal() as s:
        assert auth_module.authenticate("ghost", "ghost-password", s) is None
    assert len(calls) == 2


# ── F2 — last-admin guard survives a stale read ─────────────────────────────
def _stale_admins(monkeypatch):
    """Simulate the TOCTOU: the pre-check count is stale and always returns 1,
    so only the post-write re-check can stop the demotion/deactivation."""
    monkeypatch.setattr(admin_router, "_other_active_admins", lambda db, user: 1)


def test_stale_read_cannot_demote_last_admin(roles, monkeypatch):
    _stale_admins(monkeypatch)
    admin_id = roles["admin"]["id"]
    admin_headers = roles["admin"]["headers"]

    assert_status(client.patch(f"/api/admin/users/{admin_id}", json={"role": "viewer"},
                               headers=admin_headers), 400)
    with SessionLocal() as s:
        admin = s.query(User).filter(User.id == admin_id).one()
        assert admin.role == "admin"
        assert admin.is_active == 1


def test_stale_read_cannot_deactivate_last_admin(roles, monkeypatch):
    _stale_admins(monkeypatch)
    admin_id = roles["admin"]["id"]
    admin_headers = roles["admin"]["headers"]

    assert_status(client.patch(f"/api/admin/users/{admin_id}", json={"is_active": False},
                               headers=admin_headers), 400)
    with SessionLocal() as s:
        admin = s.query(User).filter(User.id == admin_id).one()
        assert admin.role == "admin"
        assert admin.is_active == 1


def test_stale_read_cannot_soft_delete_last_admin(roles, monkeypatch):
    _stale_admins(monkeypatch)
    admin_id = roles["admin"]["id"]
    admin_headers = roles["admin"]["headers"]

    assert_status(client.delete(f"/api/admin/users/{admin_id}", headers=admin_headers), 400)
    with SessionLocal() as s:
        admin = s.query(User).filter(User.id == admin_id).one()
        assert admin.role == "admin"
        assert admin.is_active == 1


# ── F3 — contributor modal payload ──────────────────────────────────────────
def test_contributor_modal_payload_saves_without_assignee(roles):
    """The SPA now sends only changed fields, so a contributor's save carries
    status and actual_hours and no assignee; the old over-sending payload
    (assignee included) is still refused, keeping the contract explicit."""
    project = client.post("/api/projects", json={"name": "Modal"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]
    task = client.post(f"/api/projects/{pid}/tasks", json={"title": "Hours"},
                       headers=roles["pmo_lead"]["headers"])
    assert_status(task, 200)
    tid = task.json()["id"]

    # The exact payload the modal now sends for a contributor.
    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"status": "in_progress", "actual_hours": 2.5},
                               headers=roles["contributor"]["headers"]), 200)
    after = client.get(f"/api/projects/{pid}/tasks/{tid}",
                       headers=roles["viewer"]["headers"]).json()
    assert after["status"] == "in_progress"
    assert after["actual_hours"] == 2.5

    # The old payload that always included assignee is still refused.
    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"status": "done", "actual_hours": 3.0,
                                     "assignee": "bob"},
                               headers=roles["contributor"]["headers"]), 403)


# ── F4 — field refusal leaves an access_denied trace ────────────────────────
def test_field_refusal_writes_access_denied(roles):
    """A contributor's field refusal is a manual 403, not a guard 403, so it
    must still write the same access_denied row naming the refused fields."""
    project = client.post("/api/projects", json={"name": "Refusal"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]
    task = client.post(f"/api/projects/{pid}/tasks", json={"title": "T"},
                       headers=roles["pmo_lead"]["headers"])
    assert_status(task, 200)
    tid = task.json()["id"]

    before = sum(1 for r in client.get("/api/admin/audit?limit=500",
                                       headers=roles["admin"]["headers"]).json()
                 if r["action"] == "access_denied")

    assert_status(client.patch(f"/api/projects/{pid}/tasks/{tid}",
                               json={"title": "renamed"},
                               headers=roles["contributor"]["headers"]), 403)

    rows = client.get("/api/admin/audit?limit=500", headers=roles["admin"]["headers"]).json()
    denied = [r for r in rows if r["action"] == "access_denied"]
    assert len(denied) == before + 1
    assert denied[0]["detail"]["refused_fields"] == ["title"]
    assert denied[0]["detail"]["required_roles"] == ["pmo_lead", "admin"]


# ── F6 — long passwords are a 422, not a 500 ────────────────────────────────
def test_long_password_is_422_not_500(roles):
    """A password over bcrypt's 72-byte ceiling is a 422 on create and reset,
    not an unhandled 500, and no user is created."""
    admin_headers = roles["admin"]["headers"]
    long_password = "x" * 80

    assert_status(client.post("/api/admin/users", json={
        "username": "longpass", "email": "longpass@example.com",
        "role": "viewer", "password": long_password,
    }, headers=admin_headers), 422)
    with SessionLocal() as s:
        assert s.query(User).filter(User.username == "longpass").count() == 0

    assert_status(client.post(f"/api/admin/users/{roles['viewer']['id']}/password",
                              json={"new_password": long_password},
                              headers=admin_headers), 422)


# ── F7 — login rows record an IP ────────────────────────────────────────────
def test_login_failed_row_records_ip(roles):
    assert_status(login("nobody", "whatever"), 401)
    rows = client.get("/api/admin/audit?limit=500&action=login_failed",
                      headers=roles["admin"]["headers"]).json()
    assert rows
    assert rows[0]["ip"] is not None


# ── F8 — token issuer and subject are validated ─────────────────────────────
def test_token_issuer_and_subject_are_validated(roles):
    """A token signed with the same secret but a different issuer is refused,
    and a non-numeric subject is refused too."""
    with SessionLocal() as s:
        viewer = s.query(User).filter(User.username == "viewer").one()
        viewer_id = viewer.id
        version = viewer.token_version

    wrong_iss = pyjwt.encode(
        {"sub": str(viewer_id), "ver": version, "iss": "other-issuer"},
        auth_module.JWT_SECRET, algorithm=auth_module.JWT_ALGORITHM,
    )
    assert_status(client.get("/api/projects", headers=auth(wrong_iss)), 401)

    bad_sub = pyjwt.encode(
        {"sub": "not-a-number", "ver": version, "iss": "agentic-pmo"},
        auth_module.JWT_SECRET, algorithm=auth_module.JWT_ALGORITHM,
    )
    assert_status(client.get("/api/projects", headers=auth(bad_sub)), 401)


# ── F9 — empty and whitespace emails are rejected ───────────────────────────
def test_empty_email_is_rejected(roles):
    admin_headers = roles["admin"]["headers"]
    assert_status(client.post("/api/admin/users", json={
        "username": "emptyemail", "email": "", "role": "viewer",
        "password": "long-enough-password",
    }, headers=admin_headers), 422)
    assert_status(client.post("/api/admin/users", json={
        "username": "spaceemail", "email": "   ", "role": "viewer",
        "password": "long-enough-password",
    }, headers=admin_headers), 422)
    with SessionLocal() as s:
        assert s.query(User).filter(User.username.in_(["emptyemail", "spaceemail"])).count() == 0


# ── project update is audited ───────────────────────────────────────────────
def test_project_update_is_audited(roles):
    """A project PATCH writes a project_updated row naming the fields changed,
    never their values (a goal or brief can be long prose)."""
    project = client.post("/api/projects", json={"name": "Audit Me", "goal": "before"},
                          headers=roles["pmo_lead"]["headers"])
    assert_status(project, 200)
    pid = project.json()["id"]

    assert_status(client.patch(f"/api/projects/{pid}",
                               json={"goal": "a much longer goal value",
                                     "priority": "critical"},
                               headers=roles["pmo_lead"]["headers"]), 200)

    rows = client.get("/api/admin/audit?limit=500", headers=roles["admin"]["headers"]).json()
    updated = [r for r in rows if r["action"] == "project_updated"]
    assert updated
    assert updated[0]["detail"]["fields"] == ["goal", "priority"]
    detail = json.dumps(updated[0]["detail"])
    assert "a much longer goal value" not in detail
    assert "critical" not in detail
