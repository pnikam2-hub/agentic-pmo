/* Agentic PMO — Domain Packs (curated domain intelligence + attach to a project) */
const PacksView = {
  packs: [],

  async render() {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading domain packs...</div>';
    try {
      this.packs = await api.listPacks();
      this._renderList(container);
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error loading packs: ${esc(err.message)}</p></div>`;
    }
  },

  _renderList(container) {
    const p = this.packs;
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Domain Packs</h1>
          <p class="page-subtitle">${p.length} packs — risk registers, KPIs and monitoring rules the agents use as domain knowledge</p>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px">
        ${p.map(x => this._card(x)).join('')}
      </div>
    `;
  },

  _card(x) {
    return `
      <div class="card" style="display:flex;flex-direction:column;gap:12px;padding:18px">
        <div style="font-size:16px;font-weight:700">${esc(x.name)}</div>
        <div style="font-size:13px;color:var(--text-secondary);line-height:1.5">${esc(x.description)}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;font-size:11px">
          <span class="badge badge-info">${x.risk_count} risks</span>
          <span class="badge badge-success">${x.kpi_count} KPIs</span>
          <span class="badge badge-warning">${x.rule_count} rules</span>
          <span class="badge badge-muted">${x.total_tasks} WBS tasks</span>
        </div>
        <div style="display:flex;gap:8px;margin-top:auto;padding-top:8px">
          <button class="btn btn-primary btn-sm" onclick="PacksView.attach('${esc(x.id)}')">Attach to project</button>
          <button class="btn btn-secondary btn-sm" onclick="PacksView.inspect('${esc(x.id)}')">Inspect</button>
        </div>
      </div>
    `;
  },

  async inspect(id) {
    try {
      const p = await api.getPack(id);
      const risks = (p.risks || []).slice(0, 8);
      const kpis = (p.kpis || []).slice(0, 10);
      const rules = (p.rules || []).slice(0, 6);

      openModal(`${p.name} — domain pack`, `
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:14px">${esc(p.description)}</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px;font-size:11px">
          <span class="badge badge-info">${p.risk_count} risks</span>
          <span class="badge badge-success">${p.kpi_count} KPIs</span>
          <span class="badge badge-warning">${p.rule_count} monitoring rules</span>
          <span class="badge badge-muted">${p.phase_count} phases · ${p.total_tasks} tasks · ${p.total_estimated_hours}h</span>
        </div>

        <div class="section-title" style="margin-bottom:8px">Top risks</div>
        ${risks.map(r => `
          <div style="border-left:2px solid var(--border);padding:6px 10px;margin-bottom:8px">
            <div style="font-size:13px;font-weight:600">${esc(r.title)}</div>
            <div style="font-size:11px;color:var(--text-muted)">${esc(r.category || '')} · ${esc(r.probability || '')} probability / ${esc(r.impact || '')} impact · owner: ${esc(r.owner_role || '—')}</div>
          </div>
        `).join('')}

        <div class="section-title" style="margin:18px 0 8px">KPIs</div>
        ${kpis.map(k => `<div style="font-size:12px;color:var(--text-secondary);padding:2px 0">• ${esc(k.name)} <span style="color:var(--text-muted)">— target ${esc(k.target || '')}</span></div>`).join('')}

        <div class="section-title" style="margin:18px 0 8px">Monitoring rules</div>
        ${rules.map(r => `<div style="font-size:12px;color:var(--text-secondary);padding:2px 0">• ${esc(r.trigger_condition)}</div>`).join('')}

        <div style="display:flex;gap:8px;margin-top:18px">
          <button class="btn btn-primary" onclick="closeModal(); PacksView.attach('${esc(p.id)}')">Attach to a project</button>
          <button class="btn btn-secondary" onclick="closeModal()">Close</button>
        </div>
      `);
    } catch (err) {
      showToast(`Error loading pack: ${err.message}`, 'error');
    }
  },

  async attach(id) {
    let projects = [];
    try { projects = await api.listProjects(); } catch (e) { /* ignore */ }

    openModal('Attach domain pack', `
      <div class="form-group">
        <label class="form-label">Project</label>
        <select class="form-select" id="pack-project">
          ${projects.map(p => `<option value="${p.id}">${esc(p.name)} — ${p.task_count} tasks</option>`).join('')}
          <option value="new">➕ New project from this pack</option>
        </select>
      </div>
      <div class="form-group" id="pack-newname-group" style="display:none">
        <label class="form-label">New project name</label>
        <input class="form-input" id="pack-newname" placeholder="e.g. SAF plant — Phase 1" />
      </div>
      <div class="form-group">
        <label class="form-label">Tasks</label>
        <select class="form-select" id="pack-tasks">
          <option value="seed">Create the pack's WBS as tasks</option>
          <option value="attach">Attach pack only — keep existing tasks</option>
          <option value="replace">Replace existing tasks with the pack's WBS</option>
        </select>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">
        Attaching gives the plan, monitor and alert agents this domain's risk register,
        KPIs and monitoring rules.
      </div>
      <button class="btn btn-primary" id="pack-apply" onclick="PacksView._apply('${esc(id)}')">Attach pack</button>
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
    `);

    const sel = document.getElementById('pack-project');
    sel.addEventListener('change', () => {
      document.getElementById('pack-newname-group').style.display =
        sel.value === 'new' ? 'block' : 'none';
    });
  },

  async _apply(packId) {
    const sel = document.getElementById('pack-project');
    const mode = document.getElementById('pack-tasks').value;
    const btn = document.getElementById('pack-apply');
    btn.disabled = true;
    btn.textContent = 'Attaching...';

    try {
      let projectId;
      if (sel.value === 'new') {
        const name = document.getElementById('pack-newname').value.trim();
        if (!name) { showToast('Project name is required', 'error'); btn.disabled = false; btn.textContent = 'Attach pack'; return; }
        const created = await api.createProject({ name, priority: 'medium' });
        projectId = created.id;
      } else {
        projectId = parseInt(sel.value, 10);
      }

      const res = await api.applyPack(packId, {
        project_id: projectId,
        create_tasks: mode !== 'attach',
        replace_tasks: mode === 'replace',
      });

      closeModal();
      showToast(`${res.pack} attached — ${res.tasks_created} tasks, ${res.risks} risks, ${res.kpis} KPIs`, 'success');
      App.navigate('project-detail', { id: projectId });
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Attach pack';
      showToast(`Error: ${err.message}`, 'error');
    }
  },
};
