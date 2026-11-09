/* Agentic PMO — Templates View (browse pre-built plans, create a project from one) */
const TemplatesView = {
  templates: [],

  async render() {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading templates...</div>';

    try {
      this.templates = await api.listTemplates();
      this._renderList(container);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error loading templates: ${esc(err.message)}</p></div>`;
    }
  },

  _renderList(container) {
    const t = this.templates;
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Templates</h1>
          <p class="page-subtitle">${t.length} pre-built project plan${t.length !== 1 ? 's' : ''} — phases, tasks and hour estimates are created for you</p>
        </div>
      </div>
      ${t.length === 0
        ? '<div class="empty-state"><div class="empty-state-icon">📦</div><div class="empty-state-title">No templates</div><div class="empty-state-text">No project templates are configured.</div></div>'
        : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px">
            ${t.map(x => this._card(x)).join('')}
          </div>`
      }
    `;
  },

  _card(x) {
    return `
      <div class="card" style="display:flex;flex-direction:column;gap:12px;padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <span class="badge badge-accent">${esc(x.category || 'template')}</span>
          <span style="font-size:11px;color:var(--text-muted)">${x.total_estimated_hours || 0}h</span>
        </div>
        <div>
          <div style="font-size:16px;font-weight:700;margin-bottom:6px">${esc(x.name)}</div>
          <div style="font-size:13px;color:var(--text-secondary);line-height:1.5">${esc(x.description)}</div>
        </div>
        <div style="font-size:12px;color:var(--text-muted)">
          ${x.phase_count} phases · ${x.total_tasks} tasks${x.estimated_duration ? ` · ${esc(x.estimated_duration)}` : ''}
        </div>
        ${x.tags?.length ? `<div style="display:flex;flex-wrap:wrap;gap:6px">${x.tags.map(tag => `<span class="tag">${esc(tag)}</span>`).join('')}</div>` : ''}
        <div style="display:flex;gap:8px;margin-top:auto;padding-top:8px">
          <button class="btn btn-primary btn-sm" onclick="TemplatesView.use('${esc(x.id)}')">Create project</button>
          <button class="btn btn-secondary btn-sm" onclick="TemplatesView.preview('${esc(x.id)}')">Preview</button>
        </div>
      </div>
    `;
  },

  async preview(id) {
    try {
      const t = await api.getTemplate(id);
      const phases = t.suggested_phases || [];
      openModal(t.name, `
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">${esc(t.description)}</p>
        <div style="margin-bottom:12px;font-size:12px;color:var(--text-muted)">
          ${phases.length} phases · ${phases.reduce((n, p) => n + p.tasks.length, 0)} tasks · ${t.estimated_duration || '—'}
        </div>
        ${phases.map(p => `
          <div style="margin-bottom:14px">
            <div style="font-size:13px;font-weight:600;margin-bottom:6px">${esc(p.name)}</div>
            <ul style="margin:0;padding-left:18px;font-size:13px;color:var(--text-secondary);line-height:1.7">
              ${p.tasks.map(task => `<li>${esc(task.title)} <span style="color:var(--text-muted)">· ${task.estimated_hours || 0}h</span></li>`).join('')}
            </ul>
          </div>
        `).join('')}
        <div style="display:flex;gap:8px;margin-top:16px">
          <button class="btn btn-primary" onclick="closeModal(); TemplatesView.use('${esc(t.id)}')">Create project from this template</button>
          <button class="btn btn-secondary" onclick="closeModal()">Close</button>
        </div>
      `);
    } catch (err) {
      showToast(`Error loading template: ${err.message}`, 'error');
    }
  },

  async use(id) {
    const t = this.templates.find(x => x.id === id) || await api.getTemplate(id);
    openModal('New project from template', `
      <div class="form-group">
        <label class="form-label">Template</label>
        <input class="form-input" value="${esc(t.name)}" disabled />
      </div>
      <div class="form-group">
        <label class="form-label">Project name *</label>
        <input class="form-input" id="tpl-name" value="${esc(t.name)}" />
      </div>
      <div class="form-group">
        <label class="form-label">Anything specific about your project?</label>
        <textarea class="form-textarea" id="tpl-desc" placeholder="Optional — site, client, capacity, constraints..."></textarea>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">
        This will create a project with ${t.phase_count} phases and ${t.total_tasks} tasks
        (${t.total_estimated_hours || 0}h estimated).
      </div>
      <button class="btn btn-primary" id="tpl-create" onclick="TemplatesView._create('${esc(t.id)}')">Create project</button>
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
    `);
  },

  async _create(id) {
    const name = document.getElementById('tpl-name').value.trim();
    const description = document.getElementById('tpl-desc').value.trim();
    if (!name) { showToast('Project name is required', 'error'); return; }

    const btn = document.getElementById('tpl-create');
    btn.disabled = true;
    btn.textContent = 'Creating...';

    try {
      const project = await api.createProject({ name, description, priority: 'medium' });
      const applied = await api.applyTemplate(id, project.id);
      closeModal();
      showToast(`Created "${applied.template}" with ${applied.tasks_created} tasks`, 'success');
      App.navigate('project-detail', { id: project.id });
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Create project';
      showToast(`Error: ${err.message}`, 'error');
    }
  },
};
