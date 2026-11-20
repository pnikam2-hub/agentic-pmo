"""OIDC single sign-on — the protocol half, kept out of the router.

Everything in here is about talking to an OpenID Connect provider correctly:
discovery, the authorise redirect, the token exchange, id-token verification,
the group→role mapping, and the signed session cookie. The router only wires
these together with the HTTP layer and the users table, so no protocol detail
leaks into request handling.

The httpx client is injectable on every public function (``client=None`` falls
back to a module-level client) so the tests can run the whole flow against an
``httpx.MockTransport`` with no network. That is the only reason the suite can
stand in for a real identity provider.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_decode

from backend.auth import JWT_SECRET, validate_role


class OIDCError(Exception):
    """A protocol failure the caller can map to an HTTP status.

    Deliberately carries no claims, tokens, codes or verifiers: the router
    chooses the status and a short reason code, and the message never echoes
    secret material back to the client.
    """


def _env_flag(name, default):
    raw = os.getenv(name, "").strip().lower()
    if raw == "":
        return default
    return raw in ("1", "true", "yes", "on")


def _parse_role_map(raw):
    """Parse the OIDC_ROLE_MAP JSON, defaulting to an empty map.

    A broken map is treated as empty rather than crashing the import: an empty
    map denies every mapped role and falls back to the default, which fails
    closed (least privilege) instead of silently granting admin on a typo.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ── Config from environment ─────────────────────────────────────────────
# SSO is off unless both OIDC_ISSUER and OIDC_CLIENT_ID are set (see
# configured()). Everything else has a safe default so a partial config never
# half-enables the flow.
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "").strip()
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "").strip()
OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid email profile").strip()
OIDC_GROUP_CLAIM = os.getenv("OIDC_GROUP_CLAIM", "groups").strip()
OIDC_DEFAULT_ROLE = os.getenv("OIDC_DEFAULT_ROLE", "viewer").strip()
OIDC_ROLE_MAP = _parse_role_map(os.getenv("OIDC_ROLE_MAP", ""))
OIDC_AUTO_PROVISION = _env_flag("OIDC_AUTO_PROVISION", default=True)
# Local password login stays on by default: an IdP outage must never lock the
# owner out. Set LOCAL_LOGIN_ENABLED=0 to run SSO-only.
LOCAL_LOGIN_ENABLED = _env_flag("LOCAL_LOGIN_ENABLED", default=True)

SSO_COOKIE_NAME = "pmo_sso"
SSO_COOKIE_TTL = 600  # seconds; mirrors the cookie's max_age


# ── HTTP client and caches ──────────────────────────────────────────────
_client = None
_discovery_cache = {}   # issuer -> discovery document
# jwks_uri -> (monotonic fetch time, {kid: RSA public key}). Per-issuer with a
# timestamp so a refresh replaces that issuer's key set wholesale once it is
# stale — a key the provider has retired must stop being trusted, which is the
# whole point of rotation.
_jwks_cache = {}
JWKS_TTL = 3600         # seconds a fetched key set stays fresh before a refetch


def _resolve_client(client=None):
    if client is not None:
        return client
    global _client
    if _client is None:
        _client = httpx.Client(timeout=10.0)
    return _client


def _request(client, method, url, **kwargs):
    """Run an httpx request, translating failures to OIDCError.

    The message stays generic on purpose: an error body from a badly-behaved
    provider can carry a code or a token, so it must never leak into our own
    logs or responses.
    """
    try:
        resp = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise OIDCError("provider request failed") from exc
    if resp.is_error:
        raise OIDCError("provider request failed")
    return resp


def configured() -> bool:
    """SSO is on only when the two values that identify us to an IdP are set."""
    return bool(OIDC_ISSUER and OIDC_CLIENT_ID)


# ── Discovery ───────────────────────────────────────────────────────────
def discover(client=None):
    """Fetch and validate the provider's discovery document, cached per issuer.

    The cache is keyed by issuer, not by a single slot, so a config change to a
    different issuer never serves a stale document from the previous one.
    """
    c = _resolve_client(client)
    issuer = OIDC_ISSUER
    cached = _discovery_cache.get(issuer)
    if cached is not None:
        return cached

    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    resp = _request(c, "GET", url)
    try:
        doc = resp.json()
    except ValueError as exc:
        raise OIDCError("malformed discovery document") from exc
    if not isinstance(doc, dict):
        raise OIDCError("malformed discovery document")
    for field in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not isinstance(doc.get(field), str) or not doc[field]:
            raise OIDCError(f"discovery document is missing '{field}'")
    # The OIDC spec requires the document's issuer to match the configured one;
    # a mismatch means we are being redirected through a confused or hostile
    # endpoint, so refuse rather than trust its keys or token URL.
    if doc["issuer"] != issuer:
        raise OIDCError("discovery document issuer does not match the configured issuer")

    _discovery_cache[issuer] = doc
    return doc


# ── Authorise redirect ──────────────────────────────────────────────────
def _s256(verifier):
    """RFC 7636 S256 challenge: base64url(SHA-256(verifier)), no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def start(redirect_uri, client=None):
    """Build the authorise URL and the per-attempt session state.

    Returns ``(authorize_url, session_state)`` where session_state holds the
    state, nonce and PKCE verifier. These are generated fresh here, never
    stored in a module global, so two overlapping sign-ins cannot collide.
    """
    c = _resolve_client(client)
    doc = discover(client=c)
    authorize_endpoint = doc["authorization_endpoint"]

    state = secrets.token_urlsafe(32)      # 32 random bytes, urlsafe
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)   # 64 bytes → 86 chars, within PKCE 43–128
    challenge = _s256(verifier)

    params = {
        "response_type": "code",
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    sep = "&" if "?" in authorize_endpoint else "?"
    authorize_url = f"{authorize_endpoint}{sep}{urlencode(params)}"
    session_state = {"state": state, "nonce": nonce, "verifier": verifier}
    return authorize_url, session_state


# ── Token exchange ──────────────────────────────────────────────────────
def exchange(code, verifier, redirect_uri, client=None):
    """Redeem the authorisation code at the token endpoint (client_secret_post).

    Returns ``(id_token, access_token)`` or raises OIDCError. The client secret
    travels in the form body, never in the URL, so it cannot leak into access
    logs the way a query parameter would.
    """
    c = _resolve_client(client)
    doc = discover(client=c)
    resp = _request(
        c, "POST", doc["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": OIDC_CLIENT_ID,
            "client_secret": OIDC_CLIENT_SECRET,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        data = resp.json()
    except ValueError as exc:
        raise OIDCError("token endpoint returned a non-JSON response") from exc
    id_token = data.get("id_token")
    if not id_token:
        raise OIDCError("token endpoint did not return an id_token")
    return id_token, data.get("access_token")


# ── JWKS ────────────────────────────────────────────────────────────────
def _jwk_to_key(jwk):
    n = int.from_bytes(base64url_decode(jwk["n"]), "big")
    e = int.from_bytes(base64url_decode(jwk["e"]), "big")
    return rsa.RSAPublicNumbers(e, n).public_key()


def _fetch_jwks(jwks_uri, client=None):
    """Fetch the JWKS and replace that issuer's cached key set wholesale.

    Each jwks_uri has its own entry stamped with the fetch time. Replacing the
    whole set (rather than merging, as the old cache did) means a key the
    provider has retired is dropped on the next refresh instead of being
    trusted for the life of the process — the opposite of what rotation is for.
    """
    c = _resolve_client(client)
    resp = _request(c, "GET", jwks_uri)
    try:
        doc = resp.json()
    except ValueError as exc:
        raise OIDCError("malformed JWKS document") from exc
    keys = doc.get("keys", []) if isinstance(doc, dict) else []
    key_map = {}
    for jwk in keys:
        key_id = jwk.get("kid")
        if not key_id:
            continue
        try:
            key_map[key_id] = _jwk_to_key(jwk)
        except (KeyError, ValueError):
            # One unparseable entry must not sink the keys we do understand.
            continue
    _jwks_cache[jwks_uri] = (time.monotonic(), key_map)


def _jwk_key(jwks_uri, kid, client=None):
    cached = _jwks_cache.get(jwks_uri)
    if cached is not None:
        fetched_at, keys = cached
        if kid in keys and time.monotonic() - fetched_at < JWKS_TTL:
            return keys[kid]
    _fetch_jwks(jwks_uri, client=client)
    keys = _jwks_cache[jwks_uri][1]
    if kid in keys:
        return keys[kid]
    # The kid may be brand new — a provider rotating keys between our fetch and
    # the token it just signed — so refetch exactly once before giving up.
    _fetch_jwks(jwks_uri, client=client)
    keys = _jwks_cache[jwks_uri][1]
    if kid not in keys:
        raise OIDCError("id_token key is not present in the provider's JWKS")
    return keys[kid]


# ── id_token verification ───────────────────────────────────────────────
def verify_id_token(id_token, nonce, client=None):
    """Verify an id_token and return its claims, or raise OIDCError.

    Validates, in order: the header carries a kid; the signature matches the
    key for that kid; iss equals the configured issuer; aud contains the
    configured client id; exp/iat are sane (pyjwt rejects an expired or a
    future-issued token, with a 60 s leeway so an IdP a few seconds ahead of
    our clock does not reject every login); and nonce matches constant-time so
    the token is bound to the authorisation attempt that started it.
    """
    c = _resolve_client(client)
    doc = discover(client=c)

    try:
        header = pyjwt.get_unverified_header(id_token)
    except pyjwt.PyJWTError as exc:
        raise OIDCError("id_token has a malformed header") from exc
    kid = header.get("kid")
    if not kid:
        raise OIDCError("id_token header has no kid")

    key = _jwk_key(doc["jwks_uri"], kid, client=c)
    try:
        claims = pyjwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            issuer=OIDC_ISSUER,
            audience=OIDC_CLIENT_ID,
            leeway=60,
            options={"require": ["iss", "aud", "exp", "iat"]},
        )
    except pyjwt.PyJWTError as exc:
        raise OIDCError("id_token verification failed") from exc

    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
        raise OIDCError("id_token nonce mismatch")
    return claims


# ── Claims → role / identity ────────────────────────────────────────────
def role_from_claims(claims):
    """Map the group claim to a role.

    Returns ``(role, matched, degraded)``. ``role`` is always one of the four
    valid roles. ``matched`` lists the group names that produced it, for the
    audit trail. ``degraded`` is set when a mapped value was not a known role
    and the least-privileged default was substituted instead — the router
    audits that rather than letting the login 500.
    """
    groups = claims.get(OIDC_GROUP_CLAIM, [])
    if isinstance(groups, str):
        groups = [groups]
    elif not isinstance(groups, list):
        groups = []

    matched = []
    role = None
    # Exact group name first, so a specific mapping wins over the wildcard.
    for group in groups:
        if isinstance(group, str) and group in OIDC_ROLE_MAP:
            role = OIDC_ROLE_MAP[group]
            matched = [group]
            break
    if role is None and "*" in OIDC_ROLE_MAP:
        role = OIDC_ROLE_MAP["*"]
        matched = ["*"]
    if role is None:
        role = OIDC_DEFAULT_ROLE

    try:
        role = validate_role(role)
        return role, matched, None
    except ValueError:
        # A configured value outside the four known roles must not elevate
        # anyone; fall back to the least-privileged role and flag the bad
        # value so the caller can audit it.
        return "viewer", [], role


def identity_from_claims(claims):
    """Extract the verified identity from claims, or raise OIDCError.

    Refuses a missing email or an unverified one: the whole point of SSO is
    that the IdP has attested to who this is, so an unverified email is not
    enough to provision or link an account on.
    """
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise OIDCError("id_token carries no usable email address")
    if claims.get("email_verified") is not True:
        raise OIDCError("id_token email address is not verified by the provider")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise OIDCError("id_token carries no subject")
    name = claims.get("name") or claims.get("preferred_username") or ""
    if not isinstance(name, str):
        name = ""
    return sub, email.strip().lower(), name, OIDC_ISSUER


# ── Session cookie ──────────────────────────────────────────────────────
def encode_session_cookie(session_state):
    """Sign the state/nonce/verifier into a short-lived JWT cookie.

    Signed with JWT_SECRET (HS256) so a tampered cookie fails signature
    verification instead of being trusted; its exp mirrors the cookie's max_age
    so the browser and the server agree on the lifetime.
    """
    now = datetime.datetime.now(datetime.UTC)
    payload = dict(session_state)
    payload["iat"] = now
    payload["exp"] = now + datetime.timedelta(seconds=SSO_COOKIE_TTL)
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_session_cookie(token):
    """Return the signed session dict, or None if invalid, expired or tampered."""
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        return None
