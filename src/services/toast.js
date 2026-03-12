/**
 * Lightweight toast service stub for standalone onboarding app.
 * Shows native alerts as fallback — no external dependency needed.
 */
const toastService = {
  success(message) {
    console.log('[Toast Success]', message);
  },
  error(message) {
    console.error('[Toast Error]', message);
    alert(message);
  },
  warning(message) {
    console.warn('[Toast Warning]', message);
  },
  info(message) {
    console.log('[Toast Info]', message);
  },
};

export default toastService;
