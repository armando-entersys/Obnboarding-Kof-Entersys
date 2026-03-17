/**
 * Lightweight toast notification service.
 * Shows floating toast messages without external dependencies.
 */

let toastContainer = null;

function getContainer() {
  if (toastContainer && document.body.contains(toastContainer)) return toastContainer;
  toastContainer = document.createElement('div');
  toastContainer.id = 'toast-container';
  toastContainer.style.cssText =
    'position:fixed;top:20px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:10px;pointer-events:none;';
  document.body.appendChild(toastContainer);
  return toastContainer;
}

function showToast(message, type = 'info', duration = 4000) {
  const container = getContainer();

  const colors = {
    success: { bg: '#f0fdf4', border: '#16a34a', text: '#15803d', icon: '\u2713' },
    error:   { bg: '#fef2f2', border: '#dc2626', text: '#b91c1c', icon: '\u2717' },
    warning: { bg: '#fefce8', border: '#f59e0b', text: '#b45309', icon: '\u26A0' },
    info:    { bg: '#eff6ff', border: '#3b82f6', text: '#1d4ed8', icon: '\u2139' },
  };

  const c = colors[type] || colors.info;

  const toast = document.createElement('div');
  toast.style.cssText =
    `background:${c.bg};border:1px solid ${c.border};border-left:4px solid ${c.border};color:${c.text};` +
    'padding:14px 20px;border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;' +
    'font-size:14px;max-width:380px;box-shadow:0 4px 12px rgba(0,0,0,0.15);pointer-events:auto;' +
    'display:flex;align-items:center;gap:10px;opacity:0;transform:translateX(40px);transition:all 0.3s ease;';

  toast.innerHTML = `<span style="font-size:18px;flex-shrink:0">${c.icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(0)';
  });

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

const toastService = {
  success(message) { showToast(message, 'success'); },
  error(message) { showToast(message, 'error', 6000); },
  warning(message) { showToast(message, 'warning', 5000); },
  info(message) { showToast(message, 'info'); },
};

export default toastService;
