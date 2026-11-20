"""OIDC SSO — the protocol proved against a locally generated identity provider.

No network: an RSA key is generated with ``cryptography``, a stub discovery
document and JWKS are served through ``httpx.MockTransport``, and id tokens are
minted locally with the same private key. That is the only way the flow — start,
exchange, verify, map, provision — is exercised end to end without a real IdP.

test_api.py installs a session-scoped stand-in for current_user/require_auth;
this suite removes it (and restores it afterwards) exactly as test_rbac.py does,
because the happy path must prove that ``/#sso=<token>`` is a *real* working JWT
accepted by ``/api/auth/me`` through the real token chain.
"""
import base64
import hashlib
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth as auth_module
from backend.auth import current_user, require_auth
from backend.database import Base, get_db
from backend.integrations import oidc
from backend.main import app
from backend.models import AuditLog, User
from backend.routers import auth as auth_router

ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

ISSUER = "https://issuer.test"
CLIENT_ID = "pmo-client"


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# No context manager: startup must not run, so the in-memory database the tests
# build is the only one touched.
client = TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


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


# ── Local "IdP" ──────────────────────────────────────────────────────────
def _b64url_int(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _s256(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def jwk_from_public_key(public_key, kid="key-1"):
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_int(numbers.n),
        "e": _b64url_int(numbers.e),
    }


class MockIdP:
    """A configurable OIDC provider behind httpx.MockTransport.

    Serves discovery, the JWKS and the token endpoint. ``pending`` holds the
    claim/key overrides for the next minted id_token, so a test can set the
    nonce (read from the signed cookie), the groups, the audience, or a
    different signing key before the callback fires.
    """

    def __init__(self, signing_key, jwk, issuer, client_id):
        self.signing_key = signing_key
        self.issuer = issuer
        self.client_id = client_id
        self.jwk = jwk
        self.jwks = {"keys": [jwk]}
        self.discovery = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks",
        }
        self.pending = {}
        self.discovery_calls = 0
        self.jwks_calls = 0
        self.token_calls = 0
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            self.discovery_calls += 1
            return httpx.Response(200, json=self.discovery)
        if path == "/jwks":
            self.jwks_calls += 1
            return httpx.Response(200, json=self.jwks)
        if path == "/token":
            self.token_calls += 1
            return httpx.Response(200, json={
                "id_token": self._mint(),
                "access_token": "access-token",
                "token_type": "Bearer",
            })
        return httpx.Response(404, json={"error": "unknown path"})

    def _mint(self):
        p = self.pending
        now = int(time.time())
        claims = {
            "iss": p.get("iss", self.issuer),
            "aud": p.get("aud", self.client_id),
            "sub": p.get("sub", "alice-123"),
            "email": p.get("email", "alice@example.com"),
            "email_verified": p.get("email_verified", True),
            "name": p.get("name", "Alice Example"),
            "iat": p.get("iat", now),
            "exp": p.get("exp", now + 3600),
            "nonce": p.get("nonce"),
        }
        if "groups" in p:
            claims["groups"] = p["groups"]
        key = p.get("signing_key", self.signing_key)
        kid = p.get("kid", self.jwk["kid"])
        return pyjwt.encode(claims, key, algorithm="RS256", headers={"kid": kid, "alg": "RS256"})


@pytest.fixture()
def idp(monkeypatch):
    """A fresh mock IdP wired into the oidc module, fully configured."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mock = MockIdP(key, jwk_from_public_key(key.public_key(), kid="key-1"),
                   ISSUER, CLIENT_ID)

    monkeypatch.setattr(oidc, "_client", httpx.Client(transport=mock.transport))
    oidc._discovery_cache.clear()
    oidc._jwks_cache.clear()
    monkeypatch.setattr(oidc, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(oidc, "OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(oidc, "OIDC_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(oidc, "OIDC_REDIRECT_URI", "http://testserver/api/auth/sso/callback")
    monkeypatch.setattr(oidc, "OIDC_SCOPES", "openid email profile")
    monkeypatch.setattr(oidc, "OIDC_GROUP_CLAIM", "groups")
    monkeypatch.setattr(oidc, "OIDC_ROLE_MAP", {"pmo-admins": "admin", "*": "viewer"})
    monkeypatch.setattr(oidc, "OIDC_DEFAULT_ROLE", "viewer")
    monkeypatch.setattr(oidc, "OIDC_AUTO_PROVISION", True)
    return mock


# ── helpers ─────────────────────────────────────────────────────────────
def extract_sso_cookie(resp):
    for raw in resp.headers.get_list("set-cookie"):
        if raw.startswith("pmo_sso="):
            return raw.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("pmo_sso cookie was not set")


def decode_cookie(value):
    return pyjwt.decode(value, auth_module.JWT_SECRET, algorithms=["HS256"])


def start_flow():
    """Hit /sso/start and return the decoded cookie session (state, nonce, verifier)."""
    resp = client.get("/api/auth/sso/start", follow_redirects=False)
    assert resp.status_code == 302
    return decode_cookie(extract_sso_cookie(resp))


def sso_token(resp):
    assert resp.status_code == 302, f"expected 302, got {resp.status_code}: {resp.text}"
    return resp.headers["location"].split("#sso=", 1)[1]


def login_token(idp, **pending):
    """Run a full SSO login and return the minted JWT."""
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], **pending}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "test-code", "state": session["state"]},
                      follow_redirects=False)
    return sso_token(resp)


# ── 1. disabled without configuration ───────────────────────────────────
def test_disabled_without_configuration():
    assert oidc.configured() is False
    assert client.get("/api/auth/sso/enabled").status_code == 503
    assert client.get("/api/auth/sso/start", follow_redirects=False).status_code == 503
    assert client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": "s"}).status_code == 503


# ── 2. start sets the cookie and redirects to the IdP ───────────────────
def test_start_sets_cookie_and_redirects(idp):
    resp = client.get("/api/auth/sso/start", follow_redirects=False)
    assert resp.status_code == 302

    set_cookie = resp.headers["set-cookie"].lower()
    assert "pmo_sso=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/api/auth/sso" in set_cookie
    assert "max-age=600" in set_cookie

    location = resp.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert urlparse(location).path == "/authorize"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["http://testserver/api/auth/sso/callback"]
    assert query["code_challenge_method"] == ["S256"]

    session = decode_cookie(extract_sso_cookie(resp))
    assert query["state"] == [session["state"]]
    assert query["nonce"] == [session["nonce"]]
    # the S256 challenge must be derived from the verifier stashed in the cookie
    assert query["code_challenge"] == [_s256(session["verifier"])]


# ── 3. happy path provisions the user and mints a working JWT ───────────
def test_happy_path_provisions_user(idp):
    token = login_token(idp, groups=["pmo-admins"])

    me = client.get("/api/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["role"] == "admin"
    assert me.json()["source"] == "oidc"

    with SessionLocal() as s:
        user = s.query(User).filter(User.email == "alice@example.com").one()
        assert user.source == "oidc"
        assert user.password_hash is None
        assert user.external_id == f"{ISSUER}#alice-123"
        assert user.role == "admin"

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_user_provisioned").all()
        assert rows
        assert rows[0].detail["issuer"] == ISSUER
        assert rows[0].detail["role"] == "admin"
        assert rows[0].detail["matched"] == ["pmo-admins"]


# ── 4. tampered state and missing cookie ────────────────────────────────
def test_tampered_state_and_missing_cookie(idp):
    session = start_flow()

    tampered = client.get("/api/auth/sso/callback",
                          params={"code": "c", "state": "not-the-state"},
                          follow_redirects=False)
    assert tampered.status_code == 400

    # a fresh client has no session cookie, so the callback cannot proceed
    fresh = TestClient(app)
    missing = fresh.get("/api/auth/sso/callback",
                        params={"code": "c", "state": session["state"]})
    assert missing.status_code == 400


# ── 5. verification failures are 401 ────────────────────────────────────
def test_token_signed_with_different_key_is_401(idp):
    session = start_flow()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.pending = {"nonce": session["nonce"], "signing_key": other_key, "kid": "key-1"}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 401


def test_wrong_audience_is_401(idp):
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "aud": "some-other-client"}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 401


def test_expired_token_is_401(idp):
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "exp": int(time.time()) - 60}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 401


def test_wrong_nonce_is_401(idp):
    session = start_flow()
    idp.pending = {"nonce": "a-different-nonce"}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 401


# ── 6. an unknown kid refetches the JWKS exactly once ───────────────────
def test_unknown_kid_refetches_once(idp):
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "kid": "unknown-kid"}
    idp.jwks_calls = 0
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 401
    # one initial fetch, then exactly one refetch before giving up
    assert idp.jwks_calls == 2


# ── 7. an unverified email is refused with 403 ──────────────────────────
def test_unverified_email_is_403(idp):
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "email_verified": False}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 403


# ── 8. an existing local user is linked, not duplicated or converted ────
def test_local_user_with_same_email_is_linked(idp):
    with SessionLocal() as s:
        local = User(username="alice", email="alice@example.com", display_name="Alice",
                     password_hash=auth_module.hash_password("local-password-123"),
                     role="viewer", source="local")
        s.add(local)
        s.commit()
        local_id = local.id

    token = login_token(idp, sub="alice-123", email="alice@example.com",
                        groups=["pmo-admins"])

    with SessionLocal() as s:
        users = s.query(User).filter(User.email == "alice@example.com").all()
        assert len(users) == 1, "linking must not create a second account"
        user = users[0]
        assert user.id == local_id
        assert user.external_id == f"{ISSUER}#alice-123"
        assert user.source == "local"            # not silently converted to oidc
        assert user.password_hash is not None    # the local password survives
        # Linking proves identity, not authority: the mapped role must NOT be
        # applied to a local account, so its role and token_version are untouched.
        assert user.role == "viewer"
        assert user.token_version == 0

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_user_linked").all()
        assert rows
        assert rows[0].detail["matched"] == ["pmo-admins"]
        assert rows[0].detail["linked"] is True
        assert rows[0].detail["role_kept"] == "viewer"
        assert rows[0].detail["mapped_role"] == "admin"


# ── 9. a group change on the next login bumps token_version ─────────────
def test_group_change_updates_role_and_bumps_version(idp):
    token1 = login_token(idp, groups=["pmo-admins"])
    assert client.get("/api/auth/me", headers=auth(token1)).json()["role"] == "admin"

    # A second admin lets the demotion below proceed: the last-admin invariant
    # (shared with the admin router) would otherwise refuse it.
    with SessionLocal() as s:
        s.add(User(username="otheradmin", email="other@example.com", display_name="Other",
                   password_hash=None, role="admin", source="oidc",
                   external_id=f"{ISSUER}#other"))
        s.commit()

    token2 = login_token(idp, groups=[])   # falls through to the "*" mapping
    assert client.get("/api/auth/me", headers=auth(token2)).json()["role"] == "viewer"

    # the first token carries the old role and version, so it must now fail
    assert client.get("/api/auth/me", headers=auth(token1)).status_code == 401

    with SessionLocal() as s:
        user = s.query(User).filter(User.email == "alice@example.com").one()
        assert user.role == "viewer"
        assert user.token_version == 1


# ── 10. provisioning off refuses an unknown user, local login survives ──
def test_auto_provision_off_unknown_user_is_403(monkeypatch, idp):
    monkeypatch.setattr(oidc, "OIDC_AUTO_PROVISION", False)

    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "sub": "new-person",
                   "email": "new@example.com", "groups": ["pmo-admins"]}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]}, follow_redirects=False)
    assert resp.status_code == 403

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_login_failed").all()
        assert rows and rows[0].detail["reason"] == "not_provisioned"

    # local password login is a separate switch and still works
    with SessionLocal() as s:
        s.add(User(username="localuser", email="local@example.com", display_name="Local",
                   password_hash=auth_module.hash_password("local-password-123"),
                   role="viewer", source="local"))
        s.commit()
    assert client.post("/api/auth/login",
                       json={"identifier": "localuser",
                             "password": "local-password-123"}).status_code == 200


# ── 11. LOCAL_LOGIN_ENABLED=0 disables passwords, SSO is unaffected ─────
def test_local_login_disabled(monkeypatch, idp):
    monkeypatch.setattr(oidc, "LOCAL_LOGIN_ENABLED", False)

    resp = client.post("/api/auth/login", json={"identifier": "admin", "password": "admin"})
    assert resp.status_code == 403
    assert "Password sign-in is disabled" in resp.json()["detail"]

    token = login_token(idp, groups=["pmo-admins"])
    me = client.get("/api/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


# ── 12. the SSO path must not leave the deployment with no administrator ─
def test_sso_cannot_demote_last_active_admin(idp):
    # A lone oidc admin whose group mapping now resolves to a lower role is the
    # last admin; the SSO path must refuse the demotion, or nobody can reach
    # /api/admin/* again (and bootstrap_admin cannot restore it — the table is
    # not empty).
    with SessionLocal() as s:
        s.add(User(username="ssoadmin", email="alice@example.com",
                   display_name="SSO Admin", password_hash=None,
                   role="admin", source="oidc",
                   external_id=f"{ISSUER}#alice-123"))
        s.commit()

    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "sub": "alice-123",
                   "email": "alice@example.com", "groups": []}   # maps to viewer
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]},
                      follow_redirects=False)
    assert resp.status_code == 403

    with SessionLocal() as s:
        user = s.query(User).filter(User.username == "ssoadmin").one()
        assert user.role == "admin"          # unchanged
        assert user.token_version == 0        # no bump

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_login_failed").all()
        assert rows and rows[0].detail["reason"] == "last_admin"


# ── 13. a deactivated user cannot complete SSO ──────────────────────────
def test_deactivated_user_cannot_complete_sso(idp):
    with SessionLocal() as s:
        s.add(User(username="ssoinactive", email="alice@example.com",
                   display_name="Inactive", password_hash=None,
                   role="viewer", source="oidc", is_active=0,
                   external_id=f"{ISSUER}#alice-123"))
        s.commit()

    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "sub": "alice-123",
                   "email": "alice@example.com", "groups": ["pmo-admins"]}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]},
                      follow_redirects=False)
    assert resp.status_code == 403
    assert "deactivated" in resp.json()["detail"].lower()

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_login_failed").all()
        assert rows and rows[0].detail["reason"] == "inactive"
        # no token was minted, so no success row either
        assert s.query(AuditLog).filter(AuditLog.action == "sso_login").count() == 0


# ── 14. last_login_at is naive UTC, like every other column ─────────────
def test_last_login_at_is_naive_utc(idp):
    login_token(idp, groups=["pmo-admins"])
    with SessionLocal() as s:
        user = s.query(User).filter(User.email == "alice@example.com").one()
        assert user.last_login_at is not None
        assert user.last_login_at.tzinfo is None


# ── 15. the provider can refuse with ?error= instead of a code ──────────
def test_provider_error_is_400(idp):
    resp = client.get("/api/auth/sso/callback",
                      params={"error": "access_denied", "state": "whatever"},
                      follow_redirects=False)
    assert resp.status_code == 400
    assert "cancelled" in resp.json()["detail"].lower()

    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "sso_login_failed").all()
        assert rows and rows[0].detail["reason"] == "provider_error"
        assert rows[0].detail["error"] == "access_denied"


# ── 16. a provisioning race is a 409, not a 500 ────────────────────────
def test_provisioning_conflict_returns_409_not_500(idp, monkeypatch):
    with SessionLocal() as s:
        s.add(User(username="taken", email="taken@example.com", display_name="Taken",
                   password_hash=None, role="viewer", source="local"))
        s.commit()

    monkeypatch.setattr(auth_router, "_unique_username", lambda db, email, sub: "taken")

    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "sub": "new-sub",
                   "email": "new@example.com", "groups": ["pmo-admins"]}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]},
                      follow_redirects=False)
    assert resp.status_code == 409

    with SessionLocal() as s:
        assert s.query(User).filter(User.email == "new@example.com").count() == 0


def test_provisioning_race_adopts_winning_row(idp, monkeypatch):
    # A concurrent first login wins the unique index: the losing request rolls
    # back its insert and adopts the row that won, rather than 500ing.
    with SessionLocal() as s:
        s.add(User(username="taken", email="taken@example.com", display_name="Taken",
                   password_hash=None, role="viewer", source="local"))
        s.commit()

    def collide_and_win(db, email, sub):
        # Simulate the racing request inserting the same person first.
        with SessionLocal() as s:
            s.add(User(username="winner", email=email, display_name="Winner",
                       password_hash=None, role="viewer", source="oidc",
                       external_id=f"{ISSUER}#{sub}"))
            s.commit()
        return "taken"   # collides with the pre-created username

    monkeypatch.setattr(auth_router, "_unique_username", collide_and_win)

    token = login_token(idp, sub="new-sub", email="new@example.com", groups=["pmo-admins"])

    with SessionLocal() as s:
        rows = s.query(User).filter(User.email == "new@example.com").all()
        assert len(rows) == 1
        assert rows[0].username == "winner"
        assert rows[0].role == "admin"     # an oidc winner still gets role sync

    me = client.get("/api/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "winner"


# ── 17. a retired JWKS key is dropped once the cache is stale ───────────
def test_retired_key_is_not_trusted_once_cache_is_stale(idp):
    # Warm the cache with key-1 by completing a login.
    login_token(idp, groups=["pmo-admins"])
    jwks_uri = f"{ISSUER}/jwks"
    assert "key-1" in oidc._jwks_cache[jwks_uri][1]

    # The provider rotates: key-1 is retired, key-2 signs from now on.
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    idp.jwks = {"keys": [jwk_from_public_key(new_key.public_key(), kid="key-2")]}

    # Age the cached key set past the TTL so the next lookup refetches.
    fetched_at, keys = oidc._jwks_cache[jwks_uri]
    oidc._jwks_cache[jwks_uri] = (fetched_at - oidc.JWKS_TTL - 1, keys)

    # A token still signed by the retired key-1 must now be refused.
    session = start_flow()
    idp.pending = {"nonce": session["nonce"], "kid": "key-1"}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]},
                      follow_redirects=False)
    assert resp.status_code == 401


# ── 18. an iat a few seconds in the future still verifies (leeway) ──────
def test_future_iat_within_leeway_verifies(idp):
    session = start_flow()
    future_iat = int(time.time()) + 30
    idp.pending = {"nonce": session["nonce"], "iat": future_iat,
                   "exp": future_iat + 3600}
    resp = client.get("/api/auth/sso/callback",
                      params={"code": "c", "state": session["state"]},
                      follow_redirects=False)
    assert resp.status_code == 302
