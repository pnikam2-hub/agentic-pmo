/* Agentic PMO — Agent Activity Log View */
const AgentsView = {
  async render() {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading agent log...</div>';

    try {
      // Fetch actions across ALL projects
      const projects = await api.listProjects();
      let allActions = [];

      for (const p of projects) {
        try {
          const actions = await api.listAgentActions(p.id);
          allActions = allActions.concat(
            actions.map(a => ({ ...a, project_name: p.name }))
          );
        } catch (e) { /* skip projects without actions */ }
      }

      allActions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

      container.innerHTML = this._html(allActions);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
    }
  },

  _html(actions) {
    return `
      <div class="page-header">
        <div>
          <h1 class="page-title">Agent Activity Log</h1>
          <p class="page-subtitle">${actions.length} action${actions.length !== 1 ? 's' : ''} across all projects</p>
        </div>
      </div>

      ${actions.length === 0
        ? `<div class="empty-state">
            <div class="empty-state-icon">🤖</div>
            <div class="empty-state-title">No agent activity yet</div>
            <div class="empty-state-text">Run the Plan, Monitor, or Alert agents on your projects to see their output here.</div>
           </div>`
        : `<div class="activity-feed">${actions.map(a => this._actionRow(a)).join('')}</div>`
      }
    `;
  },

  _actionRow(a) {
    const icons = { plan: '🧠', monitor: '👁️', alert: '🔔' };
    const sevClass = a.severity === 'critical' ? 'badge-danger' :
                     a.severity === 'warning' ? 'badge-warning' : 'badge-muted';
    const timeAgo = this._timeAgo(a.created_at);

    return `
      <div class="activity-item" style="cursor:pointer" onclick="App.navigate('project-detail',{id:${a.project_id}})">
        <div class="activity-icon ${a.agent_type}">${icons[a.agent_type] || '🤖'}</div>
        <div class="activity-content">
          <div class="activity-summary">${esc(a.summary)}</div>
          <div class="activity-meta">
            <span class="badge badge-accent">${esc(a.project_name || `Project #${a.project_id}`)}</span>
            <span>${a.agent_type} · ${a.action_type}</span>
            <span class="activity-severity ${sevClass}">${a.severity}</span>
            <span>${timeAgo}</span>
          </div>
          ${a.details && Object.keys(a.details).length
            ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted)">${esc(JSON.stringify(a.details, null, 2))}</div>`
            : ''
          }
        </div>
      </div>
    `;
  },

  _timeAgo(dateStr) {
    const now = new Date();
    const d = new Date(dateStr);
    const sec = Math.floor((now - d) / 1000);
    if (sec < 60) return 'just now';
    if (sec < 3600) return `${Math.floor(sec/60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec/3600)}h ago`;
    return `${Math.floor(sec/86400)}d ago`;
  },
};
