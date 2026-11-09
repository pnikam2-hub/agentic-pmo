/* Agentic PMO — Main App: router, navigation, modal, toast, login */
const App = {
  dragData: null,

  init() {
    window.addEventListener('hashchange', () => this.route());
    // Show login if no token, otherwise route normally
    if (!isLoggedIn() && window.location.hash !== '#login') {
      window.location.hash = 'login';
    }
    this.route();
    this._checkHealth();
  },

  async _checkHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const dot = document.querySelector('.status-dot');
        if (dot) dot.style.background = 'var(--green)';
      }
    } catch (e) { /* ignore */ }
  },

  route() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    const parts = hash.split('/');
    const view = parts[0];
    const params = {};
    if (parts[1] === 'new') params.action = 'new';
    else if (parts[1]) params.id = parseInt(parts[1]);
    if (parts[2] === 'edit') params.action = 'edit';

    // Login page — no auth needed
    if (view === 'login') {
      document.getElementById('sidebar').style.display = 'none';
      this._renderLogin();
      return;
    }

    // All other views require auth
    if (!isLoggedIn()) {
      window.location.hash = 'login';
      return;
    }

    document.getElementById('sidebar').style.display = 'flex';
    this._activateNav(view);

    switch (view) {
      case 'dashboard': DashboardView.render(); break;
      case 'projects': ProjectsView.render(parts[1] ? params : {}); break;
      case 'templates': TemplatesView.render(); break;
      case 'packs': PacksView.render(); break;
      case 'project-detail': ProjectsView.render({ id: parseInt(parts[1]) }); break;
      case 'agents': AgentsView.render(); break;
      default: DashboardView.render();
    }
  },

  navigate(view, params = {}) {
    let hash = view;
    if (params.id) hash += `/${params.id}`;
    if (params.action === 'edit') hash += '/edit';
    if (params.action === 'new' && view === 'projects') hash += '/new';
    window.location.hash = hash;
  },

  _activateNav(view) {
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.view === view ||
        (view === 'project-detail' && el.dataset.view === 'projects'));
    });
  },

  _renderLogin() {
    const container = document.getElementById('main-content');
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px">
        <div class="card" style="max-width:380px;width:100%;padding:32px">
          <div style="text-align:center;margin-bottom:24px">
            <div style="font-size:36px;color:var(--accent);margin-bottom:8px">◆</div>
            <h2 style="font-size:20px;font-weight:700">Agentic PMO</h2>
            <p style="font-size:13px;color:var(--text-muted);margin-top:4px">Sign in to continue</p>
          </div>
          <div id="login-error" style="color:var(--red);font-size:13px;margin-bottom:12px;display:none"></div>
          <div class="form-group">
            <label class="form-label">Username</label>
            <input class="form-input" id="login-username" placeholder="admin" autocomplete="username" autofocus />
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input class="form-input" id="login-password" type="password" placeholder="••••••••" autocomplete="current-password" />
          </div>
          <button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px" onclick="App._doLogin()">Sign In</button>
        </div>
      </div>
    `;
    // Enter key submits
    document.getElementById('login-password').addEventListener('keydown', e => {
      if (e.key === 'Enter') App._doLogin();
    });
  },

  async _doLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    errorEl.style.display = 'none';

    if (!username || !password) {
      errorEl.textContent = 'Please enter username and password.';
      errorEl.style.display = 'block';
      return;
    }

    try {
      const data = await loginRequest(username, password);
      setToken(data.token);
      document.getElementById('sidebar').style.display = 'flex';
      window.location.hash = 'dashboard';
    } catch (err) {
      errorEl.textContent = 'Invalid credentials. Please try again.';
      errorEl.style.display = 'block';
    }
  },

  logout() {
    clearToken();
    window.location.hash = 'login';
  },
};

// Global helpers
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3500);
}

function openModal(title, bodyHTML) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHTML;
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
