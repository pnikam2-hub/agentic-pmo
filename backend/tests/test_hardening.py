"""Phase C round C2 — login throttling, password policy, response headers.

Three hardening items that a security questionnaire asks about after Phase A/B:

1. Per-identifier login throttling, counted on the audit trail so it survives a
   restart and needs no shared store. A 429 + Retry-After is returned once there
   are LOGIN_FAILURE_LIMIT failures for one identifier digest within the window.
2. A password policy that is not just a length: zxcvbn score >= 3, on top of the
   12-character floor and the 72-byte ceiling, with zxcvbn's own feedback as the
   rejection message.
3. Response security headers in one middleware, HSTS only when HTTPS is in play.

Like test_rbac.py, this file drives the real dependency chain end to end — real
logins, real audit rows — so it removes test_api.py's session-scoped stand-ins
for current_user/require_auth exactly as test_rbac.py does.
"""
import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth as auth_module
from backend.auth import bootstrap_admin, current_user, require_auth
from backend.database import Base, get_db
from backend.main import app
from backend.models import AuditLog, User

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

# A passphrase that clears zxcvbn's score-3 floor, used as the "right" password.
STRONG = "correct-horse-battery-staple"


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


@pytest.fixture()
def victim():
    """One local account whose identifier can be failed against."""
    with SessionLocal() as s:
        s.add(User(
            username="victim",
            email="victim@example.com",
            display_name="Victim",
            password_hash=auth_module.hash_password(STRONG),
            role="viewer",
            source="local",
        ))
        s.commit()


# ── 1. Per-identifier login throttling ─────────────────────────────────────
class TestLoginThrottling:
    def test_sixth_attempt_with_correct_password_is_429(self, victim):
        """Five failures for one digest lock the sixth attempt — even with the
        right password — before any bcrypt runs, and write a login_throttled
        audit row carrying the digest, never the identifier."""
        for _ in range(auth_module.LOGIN_FAILURE_LIMIT):
            assert login("victim", "wrong-password-here").status_code == 401

        resp = login("victim", STRONG)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0

        with SessionLocal() as s:
            rows = s.query(AuditLog).filter(AuditLog.action == "login_throttled").all()
            assert len(rows) == 1
            assert rows[0].actor == "anonymous"
            assert rows[0].detail["identifier_sha256"] == auth_module.identifier_digest("victim")
            # The digest, never the identifier.
            assert "victim" not in str(rows[0].detail)

    def test_failure_beyond_window_does_not_lock(self, victim):
        """Failures older than the window are not counted, so the identifier is
        not locked once they have aged out."""
        digest = auth_module.identifier_digest("victim")
        old = datetime.datetime.utcnow() - datetime.timedelta(
            minutes=auth_module.LOGIN_FAILURE_WINDOW_MINUTES + 1
        )
        with SessionLocal() as s:
            for _ in range(auth_module.LOGIN_FAILURE_LIMIT):
                s.add(AuditLog(
                    actor="anonymous",
                    action="login_failed",
                    detail={"identifier_sha256": digest},
                    at=old,
                    ip="127.0.0.1",
                ))
            s.commit()

        assert login("victim", STRONG).status_code == 200

    def test_different_identifier_is_unaffected(self, victim):
        """Locking one identifier does not touch any other."""
        with SessionLocal() as s:
            s.add(User(
                username="other",
                email="other@example.com",
                display_name="Other",
                password_hash=auth_module.hash_password(STRONG),
                role="viewer",
                source="local",
            ))
            s.commit()

        for _ in range(auth_module.LOGIN_FAILURE_LIMIT):
            assert login("victim", "wrong-password-here").status_code == 401

        assert login("other", STRONG).status_code == 200


# ── 2. Password policy (zxcvbn, additional to length and byte ceilings) ────
class TestPasswordPolicy:
    def test_rejects_common_password(self):
        """The exact string the plan calls out is refused. It is ten characters,
        so the 12-character floor catches it before zxcvbn runs — still refused,
        which is the property under test."""
        with pytest.raises(ValueError):
            auth_module.validate_password("Password1!")

    def test_rejects_weak_long_password_with_reason(self):
        """A password that clears the length floor but not the strength floor is
        refused with zxcvbn's own words, not a bare 'too weak'."""
        with pytest.raises(ValueError) as exc:
            auth_module.validate_password("password12345")
        # zxcvbn's own words: "This is similar to a commonly used password."
        assert "common" in str(exc.value).lower()

    def test_accepts_long_passphrase(self):
        auth_module.validate_password("correct horse battery staple")

    def test_rejects_password_over_72_bytes(self):
        with pytest.raises(ValueError, match="72 bytes"):
            auth_module.validate_password("a" * 80)

    def test_keeps_length_floor(self):
        with pytest.raises(ValueError, match="at least 12"):
            auth_module.validate_password("short")

    def test_422_carries_zxcvbn_feedback(self):
        """The policy applies at user creation, and the 422 body carries the
        reason, not a bare 'too weak'."""
        with SessionLocal() as s:
            bootstrap_admin(s)
        admin = login("admin", "admin")
        assert admin.status_code == 200
        headers = {"Authorization": f"Bearer {admin.json()['token']}"}

        resp = client.post("/api/admin/users", json={
            "username": "weak",
            "email": "weak@example.com",
            "role": "viewer",
            "password": "password12345",
        }, headers=headers)
        assert resp.status_code == 422
        assert "common" in resp.json()["detail"].lower()


# ── 3. Response security headers ──────────────────────────────────────────
class TestSecurityHeaders:
    def test_api_health_carries_static_headers_and_no_store(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
        assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert resp.headers["Cache-Control"] == "no-store"
        # Plain HTTP (no trusted proxy) — no HSTS.
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_only_with_trusted_https(self):
        # A loopback peer is the documented trusted proxy, so X-Forwarded-Proto
        # is honoured; a request without it stays plain.
        loopback = TestClient(app, client=("127.0.0.1", 50000))
        https = loopback.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert https.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

        plain = loopback.get("/api/health")
        assert "Strict-Transport-Security" not in plain.headers

    def test_static_asset_is_not_marked_no_store(self):
        resp = client.get("/js/api.js")
        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") != "no-store"
