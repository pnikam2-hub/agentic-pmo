/* Agentic PMO — API Client with JWT auth */
const API_BASE = '/api';

// Session keys. The token alone was the pre-RBAC session; role and name ride
// alongside it so the SPA can render (and hide) controls without a second call.
const TOKEN_KEY = 'agentic_pmo_token';
const ROLE_KEY = 'agentic_pmo_role';
const NAME_KEY = 'agentic_pmo_name';

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

// The full session, written once on login. Role and display name are
// presentation aids only — the server is the authority and re-validates every
// token on every request.
function setSession({ token, role, display_name }) {
  setToken(token);
  localStorage.setItem(ROLE_KEY, role || '');
  localStorage.setItem(NAME_KEY, display_name || '');
}
function getRole() { return localStorage.getItem(ROLE_KEY) || ''; }
function getDisplayName() { return localStorage.getItem(NAME_KEY) || ''; }
function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(NAME_KEY);
}

// Re-read role and display name from /me and rewrite the cached copies, so the
// SPA never keeps showing buttons for a role the user no longer holds. Called
// once on boot and again after any 403; returns false when the token is gone
// or the call fails, leaving the existing cache untouched.
async function refreshSession() {
  const token = getToken();
  if (!token) return false;
  try {
    const me = await api.me();
    localStorage.setItem(ROLE_KEY, me.role || '');
    localStorage.setItem(NAME_KEY, me.display_name || '');
    return true;
  } catch (e) {
    return false;
  }
}

// What each role may do, for presentation only. The server's copy in
// backend/routers/auth.py (PERMISSIONS) is the authority and enforces every
// rule at the router boundary; this table exists solely so the SPA does not
// render buttons that would only ever produce a 403.
const ROLE_PERMISSIONS = {
  viewer:      ['read'],
  contributor: ['read', 'update_tasks'],
  pmo_lead:    ['read', 'update_tasks', 'manage_projects', 'run_agents', 'manage_plane', 'apply_packs'],
  admin:       ['read', 'update_tasks', 'manage_projects', 'run_agents', 'manage_plane', 'apply_packs',
                'manage_users'],
};

// Presentation-only permission check. Hiding a button is convenience, never
// security — the server refuses the underlying call regardless of what the UI
// shows, so this can never decide anything.
function can(permission) {
  const role = getRole();
  return !!role && (ROLE_PERMISSIONS[role] || []).includes(permission);
}

// A stored token is only a session if it has not expired. Without this check the
// SPA renders the dashboard shell for any leftover string and only bounces to the
// login page after the first API call returns 401.
function tokenIsExpired(token) {
  try {
    const part = token.split('.')[1];
    if (!part) return true;
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(
      part.length + (4 - (part.length % 4)) % 4, '='));
    const payload = JSON.parse(json);
    return payload.exp ? Date.now() >= payload.exp * 1000 : true;
  } catch (e) {
    return true;
  }
}

function isLoggedIn() {
  const t = getToken();
  if (!t || tokenIsExpired(t)) {
    if (t) clearSession();
    return false;
  }
  // A token without a role is a session from before roles existed. Rendering a
  // UI from it would lie about what the user may do, so force a fresh login.
  if (!getRole()) {
    clearSession();
    return false;
  }
  return true;
}


async function apiRequest(method, path, body = null) {
  const token = getToken();
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (token) opts.headers['Authorization'] = `Bearer ${token}`;
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, opts);

  if (res.status === 401 && path !== '/auth/login') {
    // Session expired or revoked — redirect to login
    clearSession();
    window.location.hash = 'login';
    throw new Error('Session expired. Please login again.');
  }

  if (res.status === 403 && path !== '/auth/me') {
    // A role may have changed behind this session (an admin demoted the user);
    // refresh the cached role from /me once so the UI stops offering actions
    // the server now refuses, then still surface the 403 to the caller.
    await refreshSession();
    if (typeof applyRoleVisibility === 'function') applyRoleVisibility();
  }

  if (!res.ok) {
    // Surface FastAPI's `detail` rather than the raw body — a 409 boundary message in the PMO
    // should read as guidance, not as an HTTP dump.
    let message = `${res.status} ${res.statusText}`;
    try {
      const text = await res.text();
      try {
        const parsed = JSON.parse(text);
        message = parsed.detail || parsed.error || text || message;
      } catch {
        message = text || message;
      }
    } catch {
      /* body unreadable — keep the status line */
    }
    throw new Error(message);
  }

  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

// Auth-specific (no token required for login)
async function loginRequest(username, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => 'Login failed');
    throw new Error(err);
  }
  return res.json();
}

const api = {
  // Dashboard
  getDashboard() { return apiRequest('GET', '/dashboard'); },

  // Projects
  listProjects() { return apiRequest('GET', '/projects'); },
  getProject(id) { return apiRequest('GET', `/projects/${id}`); },
  createProject(d) { return apiRequest('POST', '/projects', d); },
  updateProject(id, d) { return apiRequest('PATCH', `/projects/${id}`, d); },
  deleteProject(id) { return apiRequest('DELETE', `/projects/${id}`); },

  // Tasks
  listTasks(pid) { return apiRequest('GET', `/projects/${pid}/tasks`); },
  createTask(pid, d) { return apiRequest('POST', `/projects/${pid}/tasks`, d); },
  updateTask(pid, tid, d) { return apiRequest('PATCH', `/projects/${pid}/tasks/${tid}`, d); },
  deleteTask(pid, tid) { return apiRequest('DELETE', `/projects/${pid}/tasks/${tid}`); },

  // Agents
  runPlanAgent(pid, ctx) {
    return apiRequest('POST', `/projects/${pid}/agents/plan`, { project_id: pid, additional_context: ctx || '' });
  },
  runMonitorAgent(pid) { return apiRequest('POST', `/projects/${pid}/agents/monitor`); },
  runAlertAgent(pid, anomaly) {
    return apiRequest('POST', `/projects/${pid}/agents/alert?anomaly=${encodeURIComponent(anomaly || '')}`);
  },
  listAgentActions(pid) { return apiRequest('GET', `/projects/${pid}/agents/actions`); },
  resolveAgentAction(pid, aid) { return apiRequest('PATCH', `/projects/${pid}/agents/actions/${aid}/resolve`); },

  // Alerts
  alertStatus() { return apiRequest('GET', '/alerts/status'); },
  testAlert(d) { return apiRequest('POST', '/alerts/test', d); },

  // Templates
  listTemplates() { return apiRequest('GET', '/templates'); },
  getTemplate(id) { return apiRequest('GET', `/templates/${id}`); },
  applyTemplate(tid, pid) { return apiRequest('POST', `/templates/${tid}/apply`, { project_id: pid }); },

  // Domain packs
  listPacks() { return apiRequest('GET', '/packs'); },
  getPack(id) { return apiRequest('GET', `/packs/${id}`); },
  applyPack(id, payload) { return apiRequest('POST', `/packs/${id}/apply`, payload); },
  getProjectPack(pid) { return apiRequest('GET', `/projects/${pid}/pack`); },
  detachPack(pid) { return apiRequest('DELETE', `/projects/${pid}/pack`); },

  // Identity
  me() { return apiRequest('GET', '/auth/me'); },
  changeOwnPassword(oldPassword, newPassword) {
    return apiRequest('POST', '/auth/password', { old_password: oldPassword, new_password: newPassword });
  },

  // Admin — user management and the audit trail. The admin router is admin-only
  // on the server; the SPA merely hides these for everyone else.
  listUsers() { return apiRequest('GET', '/admin/users'); },
  createUser(d) { return apiRequest('POST', '/admin/users', d); },
  updateUser(id, d) { return apiRequest('PATCH', `/admin/users/${id}`, d); },
  resetUserPassword(id, password) {
    return apiRequest('POST', `/admin/users/${id}/password`, { new_password: password });
  },
  deactivateUser(id) { return apiRequest('DELETE', `/admin/users/${id}`); },
  listAudit({ limit, actor, action } = {}) {
    const params = new URLSearchParams();
    if (limit) params.set('limit', String(limit));
    if (actor) params.set('actor', actor);
    if (action) params.set('action', action);
    const qs = params.toString();
    return apiRequest('GET', `/admin/audit${qs ? `?${qs}` : ''}`);
  },
};
