# ROUND B2 — the SPA half of SSO, and the version badge

Repository: /root/projects/agentic-pmo at 0.2.0. Phase B's server side is complete: `/api/auth/sso/enabled`,
`/api/auth/sso/start`, `/api/auth/sso/callback` (which redirects to `/#sso=<handoff>`) and
`POST /api/auth/sso/exchange` (single-use, 120 s, returns the normal login response shape). Read
`docs/sso-rbac-phaseB-report.md` §2 for the flow, then `frontend/js/app.js`, `frontend/js/api.js`,
`frontend/index.html`.

Nothing in the interface reaches SSO yet. This round wires it, and makes the shell stop lying about the
version.

## 1. `frontend/js/api.js`

- `ssoEnabled()` → `GET /auth/sso/enabled`, returning `{enabled, issuer}`; a 503 means "not configured", which
  is **not** an error to show — return `{enabled: false}` for it, and let a genuine network failure surface.
- `ssoStartUrl()` → the string `/api/auth/sso/start` (a full-page navigation, not a fetch — the flow needs
  the provider's redirects and the cookie).
- `exchangeHandoff(handoff)` → `POST /auth/sso/exchange` with `{handoff}`; returns the login response.
  Do not route it through `apiRequest` (that would attach an expired bearer token and clear the session on a
  401 meant for the handoff) — a small dedicated `fetch`, surfacing the server's `detail` on failure, the way
  `loginRequest` already does.
- `issuerHost()` helper is not needed; render the issuer as given.

## 2. `frontend/js/app.js` — the login screen

`_renderLogin()` becomes async: ask `ssoEnabled()` once and, when enabled, render above the password form:

```
[ Sign in with <provider host> ]     ← anchor href = ssoStartUrl()
—————— or sign in with a password ——————
```

The SSO option must be an `<a href>`, not a button with a click handler: the browser has to follow the 302 to
the provider. Show the password form regardless (local login is the fallback and may be disabled server-side,
which will surface as a 403 the existing error path already displays).

If `ssoEnabled()` fails to resolve, render the password form only — never leave a blank login page because a
status endpoint was slow.

## 3. `frontend/js/app.js` — consuming the handoff on boot

In `init()`, before routing:

- if `location.hash` starts with `#sso=` — take the value, immediately replace the URL with `#dashboard`
  (or `#login` on failure) using `history.replaceState` so the handoff is gone from the address bar and back
  button, then `exchangeHandoff(value)`; on success `setSession(data)` and route to the dashboard; on failure
  clear the session, show the login page, and render the server's `detail` in the existing error element
  (prefix it: "Single sign-on failed: …").
- if `location.hash` starts with `#sso-error=` — clear it the same way and show the decoded message on the
  login page.

A handoff that has already been consumed must land on the login page with a readable message, not a JSON
document and not a blank screen.

## 4. Backend: a browser must not be shown raw JSON on an SSO failure

Today a refused callback returns `{"detail": "..."}` with a 4xx and the browser renders it as text. Change
the three SSO handlers (`/sso/start`, `/sso/callback`, `/sso/exchange`) so that, when the request's `Accept`
header contains `text/html`, a failure **redirects** to `/#sso-error=<urlencoded detail>` with
`Cache-Control: no-store` instead of returning JSON. Requests that do not ask for HTML (the tests, the SPA's
`fetch`, curl) keep the current status codes and bodies — the existing 41 SSO tests must pass untouched.

Add one test: a callback with `Accept: text/html` and a tampered state answers `302` to a `/#sso-error=`
location carrying no token and no claim, and a callback without that header still answers `400`.

## 5. The version badge

`frontend/index.html` hardcodes `v0.1` and the app is at `0.2.0`. Read it from `GET /api/health` (the shell
already calls that for the connection dot) and write it into the badge, so it can never drift again. If the
call fails, leave the existing text.

## 6. Constraints

- No frameworks, no build step, no new dependency. Match the existing view style and CSS vocabulary.
- `data-requires` remains the only visibility mechanism; do not add role checks that duplicate the server's.
- Do not touch role gating, the admin view, or any Phase A behaviour.
- No emoji in new code, British spelling in prose, comments that explain why.
- No commit.

## 7. When you are done

1. `.venv/bin/python -m pytest backend/tests -q` — paste the summary (expect 167).
2. `node --check` every file you touched under `frontend/js/`.
3. Start the app on a spare port against a throwaway database and paste the evidence: `GET /api/auth/sso/enabled`
   → 503, `GET /api/auth/health` version → 0.2.0, and `GET /` contains the new script/version wiring.
4. Report: files changed, how the handoff is consumed and cleared, what the login screen shows when SSO is off
   and when it is on, and anything you could not do.
