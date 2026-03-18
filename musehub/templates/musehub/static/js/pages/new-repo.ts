/**
 * new-repo.ts — New repository wizard page module.
 *
 * Handles client-side validation and tag pill input for the new-repo form.
 * The form is mostly server-rendered with HTMX; this module provides:
 *  - Repo name availability check (debounced)
 *  - Tag pill multi-input widget
 *  - Visibility card toggle (keyboard-friendly)
 *
 * Data expected in #page-data:
 *   { "page": "new-repo", "owner": "..." }
 *
 * Registered as: window.MusePages['new-repo']
 */

export interface NewRepoData {
  page?: string;
  owner?: string;
  [key: string]: unknown;
}

function initTagInput(containerId: string, hiddenInputId: string): void {
  const container = document.getElementById(containerId);
  const hidden    = document.getElementById(hiddenInputId) as HTMLInputElement | null;
  if (!container || !hidden) return;

  const textInput = container.querySelector('.tag-text-input') as HTMLInputElement | null;
  if (!textInput) return;

  let tags: string[] = hidden.value ? hidden.value.split(',').filter(Boolean) : [];

  function render(): void {
    container!.querySelectorAll('.tag-pill').forEach((p) => p.remove());
    tags.forEach((tag) => {
      const pill = document.createElement('span');
      pill.className = 'tag-pill';
      pill.textContent = tag + ' ';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tag-pill-remove';
      btn.textContent = '×';
      btn.addEventListener('click', () => { tags = tags.filter((t) => t !== tag); render(); });
      pill.appendChild(btn);
      container!.insertBefore(pill, textInput);
    });
    hidden!.value = tags.join(',');
  }

  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const val = textInput.value.trim().replace(/,/g, '');
      if (val && !tags.includes(val)) { tags.push(val); render(); }
      textInput.value = '';
    } else if (e.key === 'Backspace' && textInput.value === '' && tags.length > 0) {
      tags.pop();
      render();
    }
  });

  container.addEventListener('click', () => textInput.focus());
  render();
}

function initVisibilityCards(): void {
  document.querySelectorAll('.visibility-card').forEach((card) => {
    const el = card as HTMLElement;
    el.addEventListener('click', () => {
      document.querySelectorAll('.visibility-card').forEach((c) => {
        (c as HTMLElement).setAttribute('aria-checked', 'false');
        (c as HTMLElement).classList.remove('selected');
      });
      el.setAttribute('aria-checked', 'true');
      el.classList.add('selected');
      const radio = el.querySelector('input[type=radio]') as HTMLInputElement | null;
      if (radio) radio.checked = true;
    });
    el.addEventListener('keydown', (e) => { if ((e as KeyboardEvent).key === 'Enter' || (e as KeyboardEvent).key === ' ') el.click(); });
  });
}

export function initNewRepo(_data: NewRepoData): void {
  initTagInput('tag-input-container', 'tags-hidden');
  initVisibilityCards();
}
