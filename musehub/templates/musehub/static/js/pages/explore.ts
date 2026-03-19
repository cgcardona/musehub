/**
 * explore.ts — MuseHub explore page module.
 * Handles language/instrument/license chip toggles and filter auto-submit.
 *
 * Data expected in #page-data:
 *   { "page": "explore" }
 *
 * Registered as: window.MusePages['explore']
 */

export function initExplore(): void {
  // Strip empty fields before GET form submits so URLs stay clean
  const filterForm = document.getElementById('filter-form') as HTMLFormElement | null;
  if (filterForm) {
    filterForm.addEventListener('submit', function () {
      Array.from(this.elements).forEach((el) => {
        const input = el as HTMLInputElement | HTMLSelectElement;
        if ((input.tagName === 'SELECT' || input.tagName === 'INPUT') && input.value === '') {
          input.disabled = true;
        }
      });
    });
  }

  // Auto-submit selects and radios on change
  document.querySelectorAll<HTMLElement>('[data-autosubmit]').forEach((el) => {
    el.addEventListener('change', () => (el.closest('form') as HTMLFormElement)?.requestSubmit());
  });

  // Chip toggle — reads/writes URL directly so multi-select accumulates correctly.
  // Each click pushes history first, so the next chip always sees the full filter state.
  document.querySelectorAll<HTMLAnchorElement>('[data-filter][data-value]').forEach((chip) => {
    chip.addEventListener('click', (evt) => {
      evt.preventDefault();

      const filterName = chip.dataset.filter ?? '';
      const value = chip.dataset.value ?? '';

      const params = new URLSearchParams(window.location.search);
      const current = params.getAll(filterName);

      if (current.indexOf(value) !== -1) {
        // Deselect: rebuild the list without this value
        params.delete(filterName);
        current.filter((v) => v !== value).forEach((v) => params.append(filterName, v));
        chip.classList.remove('active');
      } else {
        // Select: add this value
        params.append(filterName, value);
        chip.classList.add('active');
      }

      const url = '/explore?' + params.toString();

      // Push URL first so subsequent chip clicks read the correct accumulated state
      history.pushState({}, '', url);

      // Fetch only the repo grid fragment via HTMX
      const htmxGlobal = (window as unknown as Record<string, unknown>).htmx as
        | { ajax: (method: string, url: string, opts: Record<string, unknown>) => void }
        | undefined;
      htmxGlobal?.ajax('GET', url, { target: '#repo-grid', swap: 'innerHTML' });
    });
  });

  // Mobile sidebar toggle
  document.querySelectorAll<HTMLElement>('[data-action="toggle-sidebar"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelector('.explore-sidebar')?.classList.toggle('open');
    });
  });
}
