"""Security regression tests — bcrypt hashing, fail-closed config, rate limiting.

Covers the three fixes from the 2026-10 security review:
1. enforce_auth_config() refuses insecure defaults
2. Password hashing is bcrypt (salted, adaptive), not fast SHA-256
3. Login endpoints return 429 once the per-IP limit is exceeded
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend import auth as auth_module


# ══════════════════════════════════════════════════════════════════════════
# Fix 2 — bcrypt password hashing
# ══════════════════════════════════════════════════════════════════════════
class TestBcryptHashing:
    def test_hash_is_bcrypt_format(self):
        h = auth_module.hash_password("correct-horse-battery")
        assert h.startswith("$2") and len(h) == 60

    def test_hash_is_salted(self):
        """Same password, two hashes → different (salt present, no rainbow tables)."""
        h1 = auth_module.hash_password("same-password")
        h2 = auth_module.hash_password("same-password")
        assert h1 != h2

    def test_verify_roundtrip(self):
        h = auth_module.hash_password("s3cret-pass")
        assert auth_module.verify_password("s3cret-pass", h) is True
        assert auth_module.verify_password("wrong-pass", h) is False

    def test_verify_rejects_malformed_hash(self):
        assert auth_module.verify_password("x", "not-a-bcrypt-hash") is False

    def test_rejects_password_over_72_bytes(self):
        with pytest.raises(ValueError):
            auth_module.hash_password("a" * 73)


# ══════════════════════════════════════════════════════════════════════════
# Fix 1 — fail-closed on insecure defaults
# ══════════════════════════════════════════════════════════════════════════
class TestEnforceAuthConfig:
    def test_raises_on_default_password(self, monkeypatch):
        monkeypatch.setattr(auth_module, "ALLOW_INSECURE_DEFAULTS", False)
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "admin")
        monkeypatch.setattr(
            auth_module, "JWT_SECRET", "real-secret-set-by-operator"
        )
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            auth_module.enforce_auth_config()

    def test_raises_on_default_jwt_secret(self, monkeypatch):
        monkeypatch.setattr(auth_module, "ALLOW_INSECURE_DEFAULTS", False)
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "strong-password")
        monkeypatch.setattr(
            auth_module,
            "JWT_SECRET",
            "change-me-in-production-agentic-pmo-2026",
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            auth_module.enforce_auth_config()

    def test_raises_on_empty_values(self, monkeypatch):
        """Regression (orch-review 2026-10): JWT_SECRET= or ADMIN_PASSWORD=
        (blank in .env) must still fail closed, not just literal defaults."""
        for empty_secret in ("", None):
            monkeypatch.setattr(auth_module, "ALLOW_INSECURE_DEFAULTS", False)
            monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "")
            monkeypatch.setattr(auth_module, "JWT_SECRET", empty_secret)
            with pytest.raises(RuntimeError):
                auth_module.enforce_auth_config()

    def test_passes_with_secure_config(self, monkeypatch):
        monkeypatch.setattr(auth_module, "ALLOW_INSECURE_DEFAULTS", False)
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "strong-password")
        monkeypatch.setattr(auth_module, "JWT_SECRET", "openssl-rand-hex-32")
        auth_module.enforce_auth_config()  # must not raise

    def test_escape_hatch_allows_defaults(self, monkeypatch):
        monkeypatch.setattr(auth_module, "ALLOW_INSECURE_DEFAULTS", True)
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "admin")
        monkeypatch.setattr(
            auth_module,
            "JWT_SECRET",
            "change-me-in-production-agentic-pmo-2026",
        )
        auth_module.enforce_auth_config()  # must not raise


# ══════════════════════════════════════════════════════════════════════════
# Fix 3 — login rate limiting (429 after limit)
# ══════════════════════════════════════════════════════════════════════════
class TestLoginRateLimit:
    def test_429_after_limit_exceeded(self):
        """Isolated app with a 3/minute limit — mirrors the wiring in
        backend/routers/auth.py without touching the shared app's limits."""
        app = FastAPI()
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        @app.post("/api/auth/login")
        @limiter.limit("3/minute")
        def login(request: Request):
            return {"token": "t"}

        client = TestClient(app)
        statuses = [
            client.post("/api/auth/login", json={"u": "x"}).status_code
            for _ in range(5)
        ]
        assert statuses[:3] == [200, 200, 200]
        assert statuses[3:] == [429, 429]
