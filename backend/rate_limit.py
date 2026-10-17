"""Rate limiting — slowapi limiter shared across routers.

Lives in its own module so routers and main.py can import the same
instance without circular imports. Limits are env-configurable so tests
can raise them (LOGIN_RATE_LIMIT=1000/minute in backend/tests/conftest.py).

Deployment notes:
- Behind a reverse proxy (nginx/traefik), get_remote_address() sees the
  proxy's IP, so ALL clients share one bucket. Run uvicorn with
  --proxy-headers and a trusted X-Forwarded-For setup, or swap the key
  function for a forwarded-IP helper.
- Storage is in-memory: per-worker and reset on restart. Fine for the
  single-worker MVP; set a redis:// storage_uri before scaling out.
"""
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# Login attempts per IP. Default is deliberately strict: bcrypt plus
# 5/minute makes online brute force impractical.
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/minute")

limiter = Limiter(key_func=get_remote_address)
