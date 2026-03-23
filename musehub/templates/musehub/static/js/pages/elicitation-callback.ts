/**
 * elicitation-callback.ts — Auto-close countdown for MCP elicitation callback page.
 *
 * Registered as: window.MusePages['elicitation-callback']
 * No config needed from #page-data — reads the DOM directly.
 */

export function initElicitationCallback(_data?: Record<string, unknown>): void {
  const el = document.getElementById('countdown');
  if (!el) return;

  let n = 5;
  const t = setInterval(() => {
    n--;
    el.textContent = String(n);
    if (n <= 0) {
      clearInterval(t);
      window.close();
    }
  }, 1000);
}
