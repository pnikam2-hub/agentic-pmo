# ROUND 4 of 4 — the frontend: role-aware navigation, a users screen, an audit screen

Repository: /root/projects/agentic-pmo. Phase A backend is complete: four roles, token versioning, audit
trail, admin API (`/api/admin/users`, `/api/admin/audit`), `/api/auth/me`, `/api/auth/password`.

Read first: `docs/sso-rbac-plan.md` §A7, `frontend/js/api.js`, `frontend/js/app.js`,
`frontend/js/projects.js`, `frontend/js/agents.js`, `frontend/js/kanban.js`, `frontend/index.html`, and
`frontend/css/app.css` (skim its class names — reuse them, do not invent a parallel design).

The rule for this round in one sentence: **the SPA hides what the caller cannot use and never decides
anything.** The server already refuses; a hidden button is convenience, not security. Say that in a
comment where the visibility rule lives, so nobody later "simplifies" a check into the client.

## 1. `frontend/js/api.js`

- Session storage: `setSession({token, role, display_name})`, `getRole()`, `getDisplayName()`,
  `clearSession()`. Keep `getToken`/`setToken`/`clearToken` working (other files call them) but have them
  read and write the same keys. Keys: `agentic_pmo_token`, `agentic_pmo_role`, `agentic_pmo_name`.
- `isLoggedIn()` stays as it is (token present and not expired) — but a missing role with a valid token
  means a stale session from before this change: treat it as logged out and force a fresh login, because
  a session with no role would render a UI that lies about what it can do.
- `can(permission)` — one function, one table, presentation only:

  ```js
  const ROLE_PERMISSIONS = {
    viewer:      ['read'],
    contributor: ['read', 'update_tasks'],
    pmo_lead:    ['read', 'update_tasks', 'manage_projects', 'run_agents', 'manage_plane', 'apply_packs'],
    admin:       ['read', 'update_tasks', 'manage_projects', 'run_agents', 'manage_plane', 'apply_packs',
                  'manage_users'],
  };
  ```

  It must mirror `PERMISSIONS` in `backend/routers/auth.py`. Note in a comment that the server's copy is
  the authority and this one exists to avoid rendering dead buttons.
- New API methods: `me()`, `listUsers()`, `createUser(d)`, `updateUser(id, d)`, `resetUserPassword(id, pw)`,
  `deactivateUser(id)` (DELETE), `listAudit({limit, actor, action})`, `changeOwnPassword(old, new)`.
- `apiRequest` already surfaces the server's `detail` on failure and clears the session on 401. Leave that
  behaviour alone; the admin screens depend on it showing the last-admin refusal verbatim.

## 2. `frontend/js/app.js` and `frontend/index.html`

- `_doLogin` calls `setSession(data)` using the login response's `token`, `role`, `display_name`.
- Sidebar footer: replace the static "Powered by AI agents" line with `Signed in as <display_name>` and a
  muted role label, keeping the existing Logout button.
- Add one nav item `#admin` ("Users & Audit") to `index.html`, marked `data-requires="manage_users"`.
- In `App.route()` add `case 'admin': AdminView.render(); break;`, and before rendering, if the view
  requires a permission the caller lacks, redirect to `#dashboard` with a toast — do not render a locked
  page.
- One function `applyRoleVisibility()` that walks `[data-requires]` elements and hides the ones `can()`
  refuses. Call it after login, after `route()` resolves, and on logout. Every permission-gated element in
  the app gets that attribute — do not scatter `if (can(...))` through the views.
- Add `<script src="/js/admin.js"></script>` before `app.js`.

## 3. `frontend/js/admin.js` — new view, `const AdminView = { async render() {...} }`

Two sections on one page, matching the existing view style (cards, `class="card"`, existing table
classes if present, `showToast`, `openModal`):

**Users.** A table: username, display name, email, role, source, active, last sign-in. Per row: a role
`<select>` (the four roles, disabled for your own row), an Activate/Deactivate button, and a "Reset
password" button that opens the existing modal with a password field. Above the table a "New user" button
opening a modal with username, email, display name, role, password. Every write re-renders the list from
the server rather than patching local state — the API is the truth, and a last-admin refusal must leave
the row as it was.

**Audit.** The newest 100 entries, with an action filter and an actor filter (a text input each, applied
on change), showing time, actor, actor role, action, target and a compact `detail` summary. Render
`detail` as `key=value` pairs; never dump raw JSON at the reader.

Handling: every failed write shows the server's `detail` in a toast (the API client already throws it),
so "Cannot demote or deactivate the last active admin" appears word for word. Do not add role checks that
duplicate the server's; the buttons are hidden for non-admins by `data-requires` and the server refuses
the rest.

## 4. Hiding what cannot be used (the rest of §A7)

- `projects.js`: hide "New project", edit and delete controls for callers without `manage_projects`;
  project deletion stays admin-only — gate the delete control on `manage_users` if that is how the server
  treats it, and say so in the comment. (It does: `DELETE /api/projects/{id}` is `admin_only`.)
- `agents.js`: hide the three "Run agent" buttons without `run_agents`; keep the action log readable to
  all.
- `kanban.js`: a viewer cannot drag a card (status is a write). Disable the drag affordance for roles
  without `update_tasks` rather than letting the drop fail with a 403.
- `packs.js` / `templates.js`: hide "Apply" without `apply_packs` / `manage_projects` respectively.

## 5. Constraints

- No frameworks, no build step, no new dependencies, no CDN assets. Plain globals, template strings, the
  existing CSS vocabulary; small additions to `frontend/css/app.css` are allowed and should reuse its
  tokens (`var(--text-muted)`, `var(--red)`, and so on).
- No emoji in new code. British spelling in prose. Comments explain why.
- **Do not change the backend or any test in this round.**
- No commit.

## 6. Proving it works (required, this is the round's evidence)

Start the app against a throwaway database and exercise the real HTTP surface, then report the output:

```bash
TS=$(date +%s)
DATABASE_URL="sqlite:////tmp/r4-$TS.db" ADMIN_USERNAME=admin ADMIN_PASSWORD='round4-admin-pass' \
JWT_SECRET="$(openssl rand -hex 32)" ALLOW_INSECURE_DEFAULTS=0 LOGIN_RATE_LIMIT=1000/minute \
.venv/bin/uvicorn backend.main:app --port 8123 &
```

Then with `curl`: log in as the admin, create a viewer, log in as the viewer, confirm
`GET /api/admin/users` is 403 for the viewer and 200 for the admin, and confirm
`GET /js/admin.js` is served with a 200 and a non-empty body. Paste those status codes in your report.
Kill the server afterwards; do not leave a process holding the port.

## 7. When you are done

Report: files changed, the permission table as the UI applies it, the curl evidence above, and anything
in §A7 you could not do. Do not write a report file.
