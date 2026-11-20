/* Agentic PMO — Admin View (users + audit). Reachable only via the route guard
   and the data-requires nav item; the admin router refuses everyone else. */
const AdminView = {
  me: null,
  users: [],
  audit: [],

  async render() {
    const container = document.getElementById('main-content');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading admin...</div>';
    try {
      // Own record drives the "you" row (whose role select is disabled); users
      // and audit load in parallel. Every list comes fresh from the server.
      const [me, users, audit] = await Promise.all([
        api.me(),
        api.listUsers(),
        api.listAudit({ limit: 100 }),
      ]);
      this.me = me;
      this.users = users;
      this.audit = audit;
      container.innerHTML = this._html();
    } catch (err) {
      container.innerHTML = `<div class="empty-state"><p>Error loading admin: ${esc(err.message)}</p></div>`;
    }
  },

  _html() {
    return `
      <div class="page-header">
        <div>
          <h1 class="page-title">Users & Audit</h1>
          <p class="page-subtitle">Manage accounts and review the audit trail</p>
        </div>
      </div>
      ${this._usersSection()}
      ${this._auditSection()}
    `;
  },

  // ── Users ─────────────────────────────────────────
  _usersSection() {
    return `
      <div class="section-header">
        <h2 class="section-title">Users</h2>
        <button class="btn btn-primary btn-sm" onclick="AdminView._openNewUser()">New user</button>
      </div>
      <div class="card" style="padding:0;overflow:auto">
        <div id="admin-users-list">${this._usersTable(this.users)}</div>
      </div>
    `;
  },

  _usersTable(users) {
    return `
      <table class="admin-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Display name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Source</th>
            <th>Active</th>
            <th>Last sign-in</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${users.map(u => this._userRow(u)).join('')}
        </tbody>
      </table>
    `;
  },

  _userRow(u) {
    const isMe = !!(this.me && this.me.id === u.id);
    const roleSelect = `
      <select class="form-select admin-role-select"
              onchange="AdminView._changeRole(${u.id}, this.value)"
              ${isMe ? 'disabled' : ''}>
        ${['viewer', 'contributor', 'pmo_lead', 'admin'].map(r =>
          `<option value="${r}" ${u.role === r ? 'selected' : ''}>${r}</option>`).join('')}
      </select>`;
    // Deactivate is a DELETE (soft: is_active=false); activate is a PATCH. The
    // server refuses to remove the last active admin, and the toast shows why.
    const toggle = u.is_active
      ? `<button class="btn btn-secondary btn-sm" onclick="AdminView._deactivate(${u.id})">Deactivate</button>`
      : `<button class="btn btn-secondary btn-sm" onclick="AdminView._activate(${u.id})">Activate</button>`;
    return `
      <tr>
        <td style="color:var(--text-primary);font-weight:500">${esc(u.username)}${isMe ? ' <span class="badge badge-accent">you</span>' : ''}</td>
        <td>${esc(u.display_name)}</td>
        <td>${esc(u.email || '—')}</td>
        <td>${roleSelect}</td>
        <td><span class="badge ${u.source === 'oidc' ? 'badge-info' : 'badge-muted'}">${esc(u.source)}</span></td>
        <td><span class="badge ${u.is_active ? 'badge-success' : 'badge-danger'}">${u.is_active ? 'active' : 'inactive'}</span></td>
        <td>${u.last_login_at ? this._fmtTime(u.last_login_at) : 'never'}</td>
        <td style="white-space:nowrap">
          ${toggle}
          <button class="btn btn-ghost btn-sm" onclick="AdminView._openResetPassword(${u.id})">Reset password</button>
        </td>
      </tr>
    `;
  },

  // Every write re-reads the list from the server — the API is the truth, and a
  // last-admin refusal must leave the row exactly as it was, not as the client
  // optimistically painted it.
  async _refreshUsers() {
    try {
      this.users = await api.listUsers();
      const el = document.getElementById('admin-users-list');
      if (el) el.innerHTML = this._usersTable(this.users);
    } catch (err) {
      showToast(err.message, 'error');
    }
  },

  async _changeRole(id, role) {
    try {
      await api.updateUser(id, { role });
      showToast('Role updated', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
    await this._refreshUsers();
  },

  async _activate(id) {
    try {
      await api.updateUser(id, { is_active: true });
      showToast('User activated', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
    await this._refreshUsers();
  },

  async _deactivate(id) {
    try {
      await api.deactivateUser(id);
      showToast('User deactivated', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
    await this._refreshUsers();
  },

  async _createUser() {
    const username = document.getElementById('new-user-username').value.trim();
    const email = document.getElementById('new-user-email').value.trim();
    const display_name = document.getElementById('new-user-display').value.trim();
    const role = document.getElementById('new-user-role').value;
    const password = document.getElementById('new-user-password').value;

    if (!username || !email || !password) {
      showToast('Username, email and password are required', 'error');
      return;
    }

    try {
      await api.createUser({ username, email, display_name, role, password });
      closeModal();
      showToast(`User ${username} created`, 'success');
      await this._refreshUsers();
    } catch (err) {
      showToast(err.message, 'error');   // keep the modal open to correct the form
    }
  },

  async _resetPassword(id) {
    const password = document.getElementById('reset-password').value;
    const confirm = document.getElementById('reset-password-confirm').value;
    if (!password) { showToast('Password is required', 'error'); return; }
    if (password !== confirm) { showToast('Passwords do not match', 'error'); return; }

    try {
      await api.resetUserPassword(id, password);
      closeModal();
      showToast('Password reset', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  },

  _openNewUser() {
    openModal('New user', `
      <div class="form-group">
        <label class="form-label">Username *</label>
        <input class="form-input" id="new-user-username" placeholder="e.g. jsmith" autocomplete="off" />
      </div>
      <div class="form-group">
        <label class="form-label">Email *</label>
        <input class="form-input" id="new-user-email" placeholder="name@example.com" />
      </div>
      <div class="form-group">
        <label class="form-label">Display name</label>
        <input class="form-input" id="new-user-display" placeholder="e.g. Jane Smith" />
      </div>
      <div class="form-group">
        <label class="form-label">Role</label>
        <select class="form-select" id="new-user-role">
          ${['viewer', 'contributor', 'pmo_lead', 'admin'].map(r => `<option value="${r}">${r}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Password *</label>
        <input class="form-input" id="new-user-password" type="password" placeholder="At least 12 characters" />
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="AdminView._createUser()">Create user</button>
        <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      </div>
    `);
  },

  _openResetPassword(id) {
    const u = this.users.find(x => x.id === id);
    const title = u ? `Reset password — ${u.username}` : 'Reset password';
    openModal(title, `
      <div class="form-group">
        <label class="form-label">New password</label>
        <input class="form-input" id="reset-password" type="password" placeholder="At least 12 characters" />
      </div>
      <div class="form-group">
        <label class="form-label">Confirm password</label>
        <input class="form-input" id="reset-password-confirm" type="password" placeholder="Repeat the password" />
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="AdminView._resetPassword(${id})">Reset password</button>
        <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      </div>
    `);
  },

  // ── Audit ─────────────────────────────────────────
  _auditSection() {
    return `
      <div class="section-header" style="margin-top:32px">
        <h2 class="section-title">Audit log</h2>
      </div>
      <div class="card" style="padding:16px">
        <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
          <div style="flex:1;min-width:180px">
            <label class="form-label">Filter by action</label>
            <input class="form-input" id="audit-filter-action" placeholder="e.g. login_success" onchange="AdminView._applyAuditFilters()" />
          </div>
          <div style="flex:1;min-width:180px">
            <label class="form-label">Filter by actor</label>
            <input class="form-input" id="audit-filter-actor" placeholder="e.g. admin" onchange="AdminView._applyAuditFilters()" />
          </div>
        </div>
        <div id="admin-audit-list">${this._auditTable(this.audit)}</div>
      </div>
    `;
  },

  async _applyAuditFilters() {
    const action = document.getElementById('audit-filter-action')?.value.trim() || '';
    const actor = document.getElementById('audit-filter-actor')?.value.trim() || '';
    try {
      this.audit = await api.listAudit({ limit: 100, actor, action });
      const el = document.getElementById('admin-audit-list');
      if (el) el.innerHTML = this._auditTable(this.audit);
    } catch (err) {
      showToast(err.message, 'error');
    }
  },

  _auditTable(entries) {
    if (!entries.length) {
      return '<div style="color:var(--text-muted);font-size:13px;padding:16px">No audit entries match.</div>';
    }
    return `
      <table class="admin-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Actor</th>
            <th>Role</th>
            <th>Action</th>
            <th>Target</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          ${entries.map(e => this._auditRow(e)).join('')}
        </tbody>
      </table>
    `;
  },

  _auditRow(e) {
    const target = e.target_type
      ? `${esc(e.target_type)}${e.target_id != null ? ` #${esc(String(e.target_id))}` : ''}`
      : '—';
    return `
      <tr>
        <td style="white-space:nowrap">${this._fmtTime(e.at)}</td>
        <td style="color:var(--text-primary)">${esc(e.actor)}</td>
        <td>${e.actor_role ? `<span class="badge badge-muted">${esc(e.actor_role)}</span>` : ''}</td>
        <td>${esc(e.action)}</td>
        <td>${target}</td>
        <td style="color:var(--text-muted);font-size:12px">${this._detailSummary(e.detail)}</td>
      </tr>
    `;
  },

  // detail is a dict; render it as key=value pairs. Nested objects collapse to
  // a compact JSON value — the reader gets labels, not a raw JSON dump.
  _detailSummary(detail) {
    if (!detail || typeof detail !== 'object') return '';
    const entries = Object.entries(detail);
    if (!entries.length) return '';
    return entries.map(([k, v]) => `${esc(k)}=${this._detailValue(v)}`).join(', ');
  },

  _detailValue(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'object') return esc(JSON.stringify(v));
    return esc(String(v));
  },

  _fmtTime(s) {
    if (!s) return '—';
    const d = new Date(s);
    if (isNaN(d.getTime())) return esc(String(s));
    return d.toLocaleString();
  },
};
