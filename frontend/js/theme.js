/**
 * theme.js — Dark/Light mode manager
 * Lê preferência do sistema e do localStorage.
 * Exporta toggleTheme() para uso nos HTMLs.
 */

(function () {
  const STORAGE_KEY = 'atl-theme';
  const ROOT = document.documentElement;

  function applyTheme(theme) {
    if (theme === 'dark') {
      ROOT.classList.add('dark');
    } else {
      ROOT.classList.remove('dark');
    }
    localStorage.setItem(STORAGE_KEY, theme);
  }

  function detectTheme() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  // Apply on load (before paint to avoid flash)
  applyTheme(detectTheme());

  // Listen for system preference change
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      applyTheme(e.matches ? 'dark' : 'light');
    }
  });

  // Public API
  window.ATL = window.ATL || {};
  window.ATL.toggleTheme = function () {
    const current = ROOT.classList.contains('dark') ? 'dark' : 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  };

  window.ATL.getCurrentTheme = function () {
    return ROOT.classList.contains('dark') ? 'dark' : 'light';
  };
})();
