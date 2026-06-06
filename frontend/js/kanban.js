/* Agentic PMO — Kanban drag-and-drop support */

// Attach drop handlers to kanban columns
document.addEventListener('DOMContentLoaded', () => {
  document.addEventListener('dragstart', (e) => {
    const card = e.target.closest('.kanban-card');
    if (card) {
      // drag data is set in the ondragstart attribute on the card
    }
  });

  document.addEventListener('dragover', (e) => {
    const col = e.target.closest('.kanban-column');
    if (col && App.dragData) {
      e.preventDefault();
      col.style.borderColor = 'var(--accent)';
    }
  });

  document.addEventListener('dragleave', (e) => {
    const col = e.target.closest('.kanban-column');
    if (col) {
      col.style.borderColor = '';
    }
  });

  document.addEventListener('drop', (e) => {
    const col = e.target.closest('.kanban-column');
    if (col && App.dragData) {
      e.preventDefault();
      col.style.borderColor = '';

      const header = col.querySelector('.kanban-column-title');
      const statusMap = {
        '📋': 'todo', '🔄': 'in_progress', '🔍': 'review', '✅': 'done', '🚫': 'blocked'
      };
      let newStatus = 'todo';
      for (const [icon, status] of Object.entries(statusMap)) {
        if (header?.textContent.includes(icon)) { newStatus = status; break; }
      }

      const { taskId, projectId } = App.dragData;
      if (taskId && projectId) {
        ProjectsView.dropTask(projectId, taskId, newStatus);
      }
      App.dragData = null;
    }
  });
});
