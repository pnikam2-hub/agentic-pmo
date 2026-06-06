/* Agentic PMO — API Client */
const API_BASE = '/api';

const api = {
  async request(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`API ${method} ${path}: ${res.status} ${err}`);
    }
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return res.json();
    return res.text();
  },

  // Dashboard
  getDashboard() { return this.request('GET', '/dashboard'); },

  // Projects
  listProjects() { return this.request('GET', '/projects'); },
  getProject(id) { return this.request('GET', `/projects/${id}`); },
  createProject(data) { return this.request('POST', '/projects', data); },
  updateProject(id, data) { return this.request('PATCH', `/projects/${id}`, data); },
  deleteProject(id) { return this.request('DELETE', `/projects/${id}`); },

  // Tasks
  listTasks(projectId) { return this.request('GET', `/projects/${projectId}/tasks`); },
  createTask(projectId, data) { return this.request('POST', `/projects/${projectId}/tasks`, data); },
  updateTask(projectId, taskId, data) { return this.request('PATCH', `/projects/${projectId}/tasks/${taskId}`, data); },
  deleteTask(projectId, taskId) { return this.request('DELETE', `/projects/${projectId}/tasks/${taskId}`); },

  // Agents
  runPlanAgent(projectId, context = '') {
    return this.request('POST', `/projects/${projectId}/agents/plan`, { project_id: projectId, additional_context: context });
  },
  runMonitorAgent(projectId) {
    return this.request('POST', `/projects/${projectId}/agents/monitor`);
  },
  runAlertAgent(projectId, anomaly = '') {
    return this.request('POST', `/projects/${projectId}/agents/alert?anomaly=${encodeURIComponent(anomaly)}`);
  },
  listAgentActions(projectId) {
    return this.request('GET', `/projects/${projectId}/agents/actions`);
  },
  resolveAgentAction(projectId, actionId) {
    return this.request('PATCH', `/projects/${projectId}/agents/actions/${actionId}/resolve`);
  },
};
