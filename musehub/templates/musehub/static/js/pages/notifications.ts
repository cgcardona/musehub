/**
 * notifications.ts — Notifications page module.
 *
 * Responsibilities:
 *  1. Auto-submit the filter form when any [data-autosubmit] control changes
 *     (replaces inline onchange="this.form.requestSubmit()" handlers).
 *
 * Registered as: window.MusePages['notifications']
 */

export function initNotifications(): void {
  document.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-autosubmit]').forEach(el => {
    el.addEventListener('change', () => {
      (el.closest('form') as HTMLFormElement | null)?.requestSubmit();
    });
  });
}
