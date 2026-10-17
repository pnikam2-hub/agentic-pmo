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
# Raise the login rate limit so TestAuth's repeated logins don't trip it.
os.environ.setdefault("LOGIN_RATE_LIMIT", "1000/minute")
# No real LLM key in tests — agents use deterministic fallbacks.
os.environ.setdefault("LLM_API_KEY", "")
