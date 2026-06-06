/* Agentic PMO — Main App: router, navigation, modal, toast */
const App = {
  dragData: null,

  init() {
    // Handle hash-based routing
    window.addEventListener('hashchange', () => this.route());
    this.route();

    // Check API health
    this._checkHealth();
  },

  async _checkHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        document.querySelector('.status-dot').style.background = 'var(--green)';
      }
    } catch (e) {
      document.querySelector('.status-dot').style.background = 'var(--red)';
    }
  },

  route() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    const parts = hash.split('/');
    const view = parts[0];
    const params = {};

    if (parts[1] === 'new') params.action = 'new';
    else if (parts[1]) params.id = parseInt(parts[1]);
    if (parts[2] === 'edit') params.action = 'edit';

    this._activateNav(view);

    switch (view) {
      case 'dashboard':
        DashboardView.render();
        break;
      case 'projects':
        ProjectsView.render(parts[1] ? params : {});
        break;
      case 'project-detail':
        params.id = parseInt(parts[1]);
        ProjectsView.render(params);
        break;
      case 'agents':
        AgentsView.render();
        break;
      default:
        DashboardView.render();
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
