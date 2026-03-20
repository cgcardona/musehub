/**
 * domains.ts — Domains listing page behaviour.
 *
 * Wires the global navbar search bar to the hero search input so that
 * clicking / focusing the navbar field redirects focus to the hero input,
 * exactly as the explore page does with its own hero search.
 */

export function initDomains(): void {
  wireNavbarSearch();
}

// ── Wire navbar search → hero search on domains page ─────────────────────────

function wireNavbarSearch(): void {
  const navForm   = document.querySelector<HTMLFormElement>('.navbar-search-form');
  const navInput  = document.querySelector<HTMLInputElement>('.navbar-search-input');
  const heroInput = document.getElementById('dm-search-input') as HTMLInputElement | null;

  if (!navForm || !navInput || !heroInput) return;

  // Intercept navbar form submit: push value into hero input and trigger HTMX
  navForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = navInput.value.trim();
    if (q) heroInput.value = q;
    heroInput.focus();
    heroInput.dispatchEvent(new Event('input', { bubbles: true }));
    navInput.value = '';
  });

  // Redirect focus from navbar input straight to the hero input
  navInput.addEventListener('focus', () => {
    heroInput.focus();
    navInput.blur();
  });
}
