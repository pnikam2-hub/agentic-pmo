"""Test configuration — set env BEFORE backend modules import.

backend.auth and backend.rate_limit read environment variables at import
time, so they must be pinned here (pytest loads conftest before test
modules) to keep the suite deterministic and immune to the host's .env.
"""
import os

os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-not-for-production")
# Tests intentionally use default creds; declare the escape hatch explicitly.
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")
# Raise the login rate limit so the suite's repeated logins don't trip it. A
# slow run across 139 tests can approach even 1000/minute, and a 429 inside the
# roles fixture surfaces as an unrelated assertion error — test_security.py
# builds its own app and limiter to cover the 429 path, so nothing loses
# coverage by raising this well out of reach.
os.environ.setdefault("LOGIN_RATE_LIMIT", "100000/minute")
# No real LLM key in tests — agents use deterministic fallbacks.
os.environ.setdefault("LLM_API_KEY", "")
# test_plane_webhook.py runs startup via TestClient(app) as a context manager, so bootstrap_admin() executes against DATABASE_URL — pin it to a scratch file or the suite writes a users row with the test password into the demo DB and, since bootstrap never overwrites, locks the real .env admin out.
# The pid in the filename keeps one run's leftover file from ever being read by
# the next, so two runs can never share a scratch database.
os.environ.setdefault("DATABASE_URL", f"sqlite:///./.pytest-scratch-{os.getpid()}.db")
