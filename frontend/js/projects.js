/* Agentic PMO — Projects View (list + detail + create/edit) */
const ProjectsView = {
  async render(params) {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';

    try {
      if (params?.action === 'new') {
        this._renderForm(container, null);
      } else if (params?.id && params?.action === 'edit') {
        const project = await api.getProject(params.id);
        this._renderForm(container, project);
      } else if (params?.id) {
        const project = await api.getProject(params.id);
        const tasks = await api.listTasks(params.id);
        const actions = await api.listAgentActions(params.id);
        this._renderDetail(container, project, tasks, actions);
      } else {
        const projects = await api.listProjects();
        this._renderList(container, projects);
      }
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
    }
  },

  // ── List View ────────────────────────────────────
  _renderList(container, projects) {
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Projects</h1>
          <p class="page-subtitle">${projects.length} project${projects.length !== 1 ? 's' : ''}</p>
        </div>
        <button class="btn btn-primary" onclick="App.navigate('projects', {action:'new'})">+ New Project</button>
      </div>
      ${projects.length === 0
        ? '<div class="empty-state"><div class="empty-state-icon">📁</div><div class="empty-state-title">No projects</div><div class="empty-state-text">Create your first project.</div></div>'
        : `<div class="project-list">${projects.map(p => this._listRow(p)).join('')}</div>`
      }
    `;
  },

  _listRow(p) {
    const pct = p.task_count > 0 ? Math.round((p.done_count / p.task_count) * 100) : 0;
    return `
      <div class="project-row" onclick="App.navigate('project-detail', {id: ${p.id}})">
        <div class="project-row-info">
          <div class="project-row-name">${esc(p.name)}</div>
          <div class="project-row-meta">
            <span class="badge ${statusClass(p.status)}">${p.status}</span>
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

  // ── Detail View ──────────────────────────────────
  _renderDetail(container, project, tasks, actions) {
    const pct = project.task_count > 0 ? Math.round((project.done_count / project.task_count) * 100) : 0;
    const todo = tasks.filter(t => t.status === 'todo');
    const inProgress = tasks.filter(t => t.status === 'in_progress');
    const review = tasks.filter(t => t.status === 'review');
    const done = tasks.filter(t => t.status === 'done');
    const blocked = tasks.filter(t => t.status === 'blocked');

    container.innerHTML = `
      <div>
        <button class="detail-back" onclick="App.navigate('projects')">← Back to Projects</button>
        <div class="detail-header">
          <div>
            <h1 class="detail-title">${esc(project.name)}</h1>
            <div class="detail-meta">
              <span class="badge ${statusClass(project.status)}">${project.status}</span>
              <span>${project.task_count} tasks · ${pct}% done</span>
              ${project.priority ? `<span class="badge badge-info">${project.priority}</span>` : ''}
              ${project.tags?.length ? project.tags.map(t => `<span class="tag">${esc(t)}</span>`).join('') : ''}
            </div>
          </div>
          <div class="action-row">
            <button class="btn btn-secondary btn-sm" onclick="App.navigate('projects', {id: ${project.id}, action:'edit'})">✏ Edit</button>
            <button class="btn btn-primary btn-sm" onclick="ProjectsView.runPlan(${project.id})">🤖 Run Plan Agent</button>
            <button class="btn btn-secondary btn-sm" onclick="ProjectsView.runMonitor(${project.id})">📊 Monitor</button>
            <button class="btn btn-secondary btn-sm" onclick="ProjectsView.runAlert(${project.id})">🚨 Alert</button>
          </div>
        </div>

        ${project.goal ? `<div class="card" style="margin-bottom:20px"><div style="font-size:13px;color:var(--text-secondary);margin-bottom:4px">Goal / Brief</div><div>${esc(project.goal)}</div></div>` : ''}

        <div class="section-header"><h2 class="section-title">Tasks</h2></div>
        ${tasks.length === 0
          ? `<div class="empty-state" style="padding:32px"><div class="empty-state-text">No tasks yet. Run the Plan Agent to generate a project plan.</div></div>`
          : this._kanbanHTML(tasks)
        }

        <div style="margin-top:32px" id="agent-actions-section">
          <div class="section-header"><h2 class="section-title">Agent Activity</h2></div>
          <div class="activity-feed">
            ${actions.length === 0
              ? '<div style="color:var(--text-muted);font-size:14px;padding:16px">No agent activity yet.</div>'
              : actions.map(a => this._actionRow(a)).join('')
            }
          </div>
        </div>
      </div>
    `;
  },

  _kanbanHTML(tasks) {
    const cols = [
      { status: 'todo', label: 'To Do', icon: '📋' },
      { status: 'in_progress', label: 'In Progress', icon: '🔄' },
      { status: 'review', label: 'Review', icon: '🔍' },
      { status: 'done', label: 'Done', icon: '✅' },
    ];
    return `
      <div class="kanban-board">
        ${cols.map(col => {
          const items = tasks.filter(t => t.status === col.status);
          return `
            <div class="kanban-column">
              <div class="kanban-column-header">
                <span class="kanban-column-title">${col.icon} ${col.label}</span>
                <span class="kanban-column-count">${items.length}</span>
              </div>
              ${items.map(t => this._kanbanCard(t)).join('')}
            </div>
          `;
        }).join('')}
        ${tasks.filter(t => t.status === 'blocked').length > 0 ? `
          <div class="kanban-column" style="border-color:var(--red)">
            <div class="kanban-column-header">
              <span class="kanban-column-title" style="color:var(--red)">🚫 Blocked</span>
              <span class="kanban-column-count">${tasks.filter(t => t.status === 'blocked').length}</span>
            </div>
            ${tasks.filter(t => t.status === 'blocked').map(t => this._kanbanCard(t)).join('')}
          </div>
        ` : ''}
      </div>
    `;
  },

  _kanbanCard(task) {
    const prioClass = `priority-${task.priority || 'medium'}`;
    return `
      <div class="kanban-card" draggable="true"
           onclick="ProjectsView.editTask(${task.project_id}, ${task.id})"
           ondragstart="App.dragData={taskId:${task.id},projectId:${task.project_id}}">
        <div class="kanban-card-title">${esc(task.title)}</div>
        <div class="kanban-card-meta">
          <span class="kanban-card-priority ${prioClass}"></span>
          ${task.assignee ? `<span>${esc(task.assignee)}</span>` : ''}
          ${task.estimated_hours ? `<span>${task.estimated_hours}h</span>` : ''}
        </div>
      </div>
    `;
  },

  _actionRow(action) {
    const icons = { plan: '🧠', monitor: '👁️', alert: '🔔' };
    const sevClass = action.severity === 'critical' ? 'badge-danger' :
                     action.severity === 'warning' ? 'badge-warning' : 'badge-muted';
    return `
      <div class="activity-item">
        <div class="activity-icon ${action.agent_type}">${icons[action.agent_type] || '🤖'}</div>
        <div class="activity-content">
          <div class="activity-summary">${esc(action.summary)}</div>
          <div class="activity-meta">
            <span>${action.agent_type} · ${action.action_type}</span>
            <span class="activity-severity ${sevClass}">${action.severity}</span>
            <span>${this._timeAgo(action.created_at)}</span>
            ${!action.resolved ? `<span class="badge badge-warning" style="cursor:pointer" onclick="ProjectsView.resolveAction(${action.project_id}, ${action.id})">Resolve</span>` : ''}
          </div>
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

  // ── Create/Edit Form ─────────────────────────────
  _renderForm(container, project) {
    const isEdit = !!project;
    container.innerHTML = `
      <div>
        <button class="detail-back" onclick="${isEdit ? `App.navigate('project-detail',{id:${project.id}})` : "App.navigate('projects')"}">← Back</button>
        <h1 class="page-title" style="margin-bottom:24px">${isEdit ? 'Edit Project' : 'New Project'}</h1>
        <div class="card" style="max-width:600px">
          <div class="form-group">
            <label class="form-label">Project Name *</label>
            <input class="form-input" id="form-name" value="${isEdit ? esc(project.name) : ''}" placeholder="e.g. Green Fuel Processing Plant" />
          </div>
          <div class="form-group">
            <label class="form-label">Goal / Brief</label>
            <textarea class="form-textarea" id="form-goal" placeholder="Describe the project goal — the AI Plan Agent will use this to generate tasks...">${isEdit ? esc(project.goal) : ''}</textarea>
          </div>
          <div class="form-group">
            <label class="form-label">Description</label>
            <textarea class="form-textarea" id="form-desc" placeholder="Additional context...">${isEdit ? esc(project.description) : ''}</textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Priority</label>
              <select class="form-select" id="form-priority">
                <option value="low" ${project?.priority === 'low' ? 'selected' : ''}>Low</option>
                <option value="medium" ${!project || project?.priority === 'medium' ? 'selected' : ''}>Medium</option>
                <option value="high" ${project?.priority === 'high' ? 'selected' : ''}>High</option>
                <option value="critical" ${project?.priority === 'critical' ? 'selected' : ''}>Critical</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Tags (comma-separated)</label>
              <input class="form-input" id="form-tags" value="${isEdit && project.tags ? project.tags.join(', ') : ''}" placeholder="green-fuel, manufacturing" />
            </div>
          </div>
          <div style="display:flex;gap:8px;margin-top:8px">
            <button class="btn btn-primary" onclick="ProjectsView._saveForm(${isEdit ? project.id : 'null'})">${isEdit ? 'Update' : 'Create'} Project</button>
            <button class="btn btn-secondary" onclick="${isEdit ? `App.navigate('project-detail',{id:${project.id}})` : "App.navigate('projects')"}">Cancel</button>
          </div>
        </div>
      </div>
    `;
  },

  async _saveForm(projectId) {
    const data = {
      name: document.getElementById('form-name').value.trim(),
      goal: document.getElementById('form-goal').value.trim(),
      description: document.getElementById('form-desc').value.trim(),
      priority: document.getElementById('form-priority').value,
      tags: document.getElementById('form-tags').value.split(',').map(s => s.trim()).filter(Boolean),
    };
    if (!data.name) { showToast('Project name is required', 'error'); return; }
    try {
      if (projectId) {
        await api.updateProject(projectId, data);
        showToast('Project updated', 'success');
        App.navigate('project-detail', { id: projectId });
      } else {
        const p = await api.createProject(data);
        showToast('Project created! Run the Plan Agent to generate tasks.', 'success');
        App.navigate('project-detail', { id: p.id });
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  },

  // ── Agent Actions ─────────────────────────────────
  async runPlan(projectId) {
    showToast('🤖 Plan Agent running...', 'info');
    try {
      const result = await api.runPlanAgent(projectId);
      showToast(`Plan Agent complete: ${result.status}`, 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Plan Agent error: ${err.message}`, 'error');
    }
  },

  async runMonitor(projectId) {
    showToast('📊 Monitor Agent running...', 'info');
    try {
      const result = await api.runMonitorAgent(projectId);
      const msg = result.risks?.length ? `${result.risks.length} risks found` : 'All clear';
      showToast(`Monitor: ${msg}`, result.risks?.length ? 'warning' : 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Monitor error: ${err.message}`, 'error');
    }
  },

  async runAlert(projectId) {
    showToast('🔔 Alert Agent running...', 'info');
    try {
      const result = await api.runAlertAgent(projectId);
      showToast(`Alert: ${result.summary?.substring(0, 60) || 'check complete'}`, result.severity === 'critical' ? 'error' : 'info');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Alert error: ${err.message}`, 'error');
    }
  },

  async resolveAction(projectId, actionId) {
    try {
      await api.resolveAgentAction(projectId, actionId);
      showToast('Action resolved', 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  },

  // ── Task Editing (from kanban) ────────────────────
  async editTask(projectId, taskId) {
    const tasks = await api.listTasks(projectId);
    const task = tasks.find(t => t.id === taskId);
    if (!task) return;

    openModal(`Edit: ${esc(task.title)}`, `
      <div class="form-group">
        <label class="form-label">Status</label>
        <select class="form-select" id="modal-task-status">
          <option value="todo" ${task.status === 'todo' ? 'selected' : ''}>To Do</option>
          <option value="in_progress" ${task.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
          <option value="review" ${task.status === 'review' ? 'selected' : ''}>Review</option>
          <option value="done" ${task.status === 'done' ? 'selected' : ''}>Done</option>
          <option value="blocked" ${task.status === 'blocked' ? 'selected' : ''}>Blocked</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Assignee</label>
        <input class="form-input" id="modal-task-assignee" value="${esc(task.assignee)}" placeholder="Person or AI agent" />
      </div>
      <div class="form-group">
        <label class="form-label">Actual Hours</label>
        <input class="form-input" id="modal-task-hours" type="number" step="0.5" value="${task.actual_hours || ''}" placeholder="${task.estimated_hours}h estimated" />
      </div>
      <button class="btn btn-primary" onclick="ProjectsView._saveTask(${projectId}, ${taskId})">Save</button>
      <button class="btn btn-danger" style="float:right" onclick="ProjectsView._deleteTask(${projectId}, ${taskId})">🗑 Delete</button>
    `);
  },

  async _saveTask(projectId, taskId) {
    const data = {
      status: document.getElementById('modal-task-status').value,
      assignee: document.getElementById('modal-task-assignee').value.trim(),
      actual_hours: parseFloat(document.getElementById('modal-task-hours').value) || 0,
    };
    try {
      await api.updateTask(projectId, taskId, data);
      closeModal();
      showToast('Task updated', 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  },

  async _deleteTask(projectId, taskId) {
    if (!confirm('Delete this task?')) return;
    try {
      await api.deleteTask(projectId, taskId);
      closeModal();
      showToast('Task deleted', 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  },

  // ── Drop Task (kanban drag-drop) ──────────────────
  async dropTask(projectId, taskId, newStatus) {
    try {
      await api.updateTask(projectId, taskId, { status: newStatus });
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  },
};

// Helpers used across views
function esc(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

function statusClass(status) {
  const map = {
    planning: 'badge-muted', active: 'badge-success', paused: 'badge-warning',
    completed: 'badge-info', cancelled: 'badge-danger',
    todo: 'badge-muted', in_progress: 'badge-info', review: 'badge-warning',
    done: 'badge-success', blocked: 'badge-danger'
  };
  return map[status] || 'badge-muted';
}
