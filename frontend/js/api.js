/* Agentic PMO — API Client with JWT auth */
const API_BASE = '/api';

function getToken() { return localStorage.getItem('agentic_pmo_token'); }
function setToken(t) { localStorage.setItem('agentic_pmo_token', t); }
function clearToken() { localStorage.removeItem('agentic_pmo_token'); }
function isLoggedIn() { return !!getToken(); }

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
    // Session expired — redirect to login
    clearToken();
    window.location.hash = 'login';
    throw new Error('Session expired. Please login again.');
  }

  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText);
    throw new Error(`API ${method} ${path}: ${res.status} ${err}`);
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
};
