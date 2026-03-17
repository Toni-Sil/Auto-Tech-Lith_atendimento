/**
 * sidebar.js — Collapsible sidebar manager
 * Handles collapse/expand, mobile overlay, and active link detection.
 */

(function () {
  window.ATL = window.ATL || {};

  const STORAGE_KEY = 'atl-sidebar-collapsed';

  function init() {
    const sidebar  = document.getElementById('sidebar');
    const topbar   = document.getElementById('topbar');
    const content  = document.getElementById('main-content');
    const toggleBtn = document.getElementById('sidebar-toggle');

    if (!sidebar) return;

    // Restore state
    const isCollapsed = localStorage.getItem(STORAGE_KEY) === 'true';
    if (isCollapsed) collapse(sidebar, topbar, content);

    toggleBtn?.addEventListener('click', () => {
      const collapsed = sidebar.classList.contains('collapsed');
      if (collapsed) {
        expand(sidebar, topbar, content);
      } else {
        collapse(sidebar, topbar, content);
      }
    });

    // Mark active item
    const currentPath = window.location.pathname;
    document.querySelectorAll('.sidebar-item').forEach(item => {
      const href = item.getAttribute('href') || item.dataset.section;
      if (href && currentPath.includes(href)) {
        item.classList.add('active');
      }
    });

    // Mobile: close sidebar on overlay click
    document.getElementById('sidebar-overlay')?.addEventListener('click', () => {
      sidebar.classList.add('-translate-x-full');
    });
  }

  function collapse(sidebar, topbar, content) {
    sidebar?.classList.add('collapsed');
    topbar?.classList.add('sidebar-collapsed');
    content?.classList.add('sidebar-collapsed');
    localStorage.setItem(STORAGE_KEY, 'true');
  }

  function expand(sidebar, topbar, content) {
    sidebar?.classList.remove('collapsed');
    topbar?.classList.remove('sidebar-collapsed');
    content?.classList.remove('sidebar-collapsed');
    localStorage.setItem(STORAGE_KEY, 'false');
  }

  document.addEventListener('DOMContentLoaded', init);

  window.ATL.sidebar = { init, collapse, expand };
})();
