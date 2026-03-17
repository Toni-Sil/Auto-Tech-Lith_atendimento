/**
 * toast.js — Notification toast system
 * Usage: ATL.toast.success('Salvo!') | ATL.toast.error('Erro') | ATL.toast.info('Info')
 */

(function () {
  window.ATL = window.ATL || {};

  function createToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container') || createContainer();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    toast.innerHTML = `
      <span class="text-base">${icons[type] || 'ℹ️'}</span>
      <span class="flex-1">${message}</span>
      <button onclick="this.parentElement.remove()" class="text-lg leading-none opacity-60 hover:opacity-100">&times;</button>
    `;

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
      }, duration);
    }

    return toast;
  }

  function createContainer() {
    const el = document.createElement('div');
    el.id = 'toast-container';
    el.className = 'fixed bottom-6 right-6 z-50 flex flex-col gap-2';
    document.body.appendChild(el);
    return el;
  }

  window.ATL.toast = {
    success: (msg, d) => createToast(msg, 'success', d),
    error:   (msg, d) => createToast(msg, 'error', d),
    info:    (msg, d) => createToast(msg, 'info', d),
    warning: (msg, d) => createToast(msg, 'warning', d),
  };
})();
