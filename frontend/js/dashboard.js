/* Agentic PMO — Dashboard View */
const DashboardView = {
  async render() {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading dashboard...</div>';

    try {
      const data = await api.getDashboard();
      container.innerHTML = this._html(data);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error loading dashboard: ${err.message}</p></div>`;
    }
  },

  _html(data) {
    const pct = data.total_tasks > 0 ? Math.round((data.done_tasks / data.total_tasks) * 100) : 0;
    return `
      <div class="page-header">
        <div>
          <h1 class="page-title">Dashboard</h1>
          <p class="page-subtitle">AI-powered project oversight at a glance</p>
        </div>
        <button class="btn btn-primary" onclick="App.navigate('projects', {action:'new'})">+ New Project</button>
      </div>

      <div class="stats-grid">
        <div class="card stat-card">
          <div class="card-header"><span class="card-title">Projects</span></div>
          <div class="card-value">${data.active_projects}<span style="font-size:16px;color:var(--text-muted);font-weight:400"> / ${data.total_projects}</span></div>
          <div class="card-footer">Active</div>
        </div>
        <div class="card stat-card">
          <div class="card-header"><span class="card-title">Tasks</span></div>
          <div class="card-value">${data.total_tasks}</div>
          <div class="card-footer">${pct}% complete</div>
        </div>
        <div class="card stat-card">
          <div class="card-header"><span class="card-title">Done</span></div>
          <div class="card-value" style="color:var(--green)">${data.done_tasks}</div>
          <div class="card-footer">${data.blocked_tasks} blocked</div>
        </div>
        <div class="card stat-card">
          <div class="card-header"><span class="card-title">Overdue</span></div>
          <div class="card-value" style="color:${data.overdue_tasks > 0 ? 'var(--red)' : 'var(--text-primary)'}">${data.overdue_tasks}</div>
          <div class="card-footer">Tasks past due date</div>
        </div>
      </div>

      <div class="section-header">
        <h2 class="section-title">Projects</h2>
      </div>
      ${data.projects.length === 0 ? this._emptyState() : this._projectList(data.projects)}
    `;
  },

  _emptyState() {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div class="empty-state-title">No projects yet</div>
        <div class="empty-state-text">Create your first project and let the AI Plan Agent build your execution plan.</div>
        <button class="btn btn-primary" onclick="App.navigate('projects', {action:'new'})">Create Project</button>
      </div>
    `;
  },

  _projectList(projects) {
    return `
      <div class="project-list">
        ${projects.map(p => this._projectRow(p)).join('')}
      </div>
    `;
  },

  _projectRow(p) {
    const pct = p.task_count > 0 ? Math.round((p.done_count / p.task_count) * 100) : 0;
    const statusBadge = this._statusBadge(p.status);
    return `
      <div class="project-row" onclick="App.navigate('project-detail', {id: ${p.id}})">
        <div class="project-row-info">
          <div class="project-row-name">${this._escape(p.name)}</div>
          <div class="project-row-meta">
            ${statusBadge}
            <span>${p.task_count} tasks</span>
            ${p.priority ? `<span class="badge badge-info">${p.priority}</span>` : ''}
          </div>
        </div>
        <div class="project-row-stats">
          <span>${p.done_count}/${p.task_count}</span>
          <div class="progress-bar">
            <div class="progress-fill" style="width:${pct}%;background:var(--accent)"></div>
          </div>
        </div>
      </div>
    `;
  },

  _statusBadge(status) {
    const map = {
      planning: ['badge-muted', 'Planning'],
      active: ['badge-success', 'Active'],
      paused: ['badge-warning', 'Paused'],
      completed: ['badge-info', 'Completed'],
      cancelled: ['badge-danger', 'Cancelled'],
    };
    const [cls, label] = map[status] || ['badge-muted', status];
    return `<span class="badge ${cls}">${label}</span>`;
  },

  _escape(s) {
    const div = document.createElement('div');
    div.textContent = s || '';
    return div.innerHTML;
  }
};
