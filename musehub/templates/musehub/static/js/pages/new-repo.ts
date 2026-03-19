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

async function submitWizard(e: Event): Promise<void> {
  e.preventDefault();
  const btn     = document.getElementById('submit-btn') as HTMLButtonElement | null;
  const errorEl = document.getElementById('submit-error') as HTMLElement | null;
  if (errorEl) errorEl.style.display = 'none';

  const owner   = (document.getElementById('f-owner')       as HTMLInputElement).value.trim();
  const name    = (document.getElementById('f-name')        as HTMLInputElement).value.trim();
  const desc    = (document.getElementById('f-description') as HTMLTextAreaElement).value.trim();
  const license = (document.getElementById('f-license')     as HTMLSelectElement).value || null;
  const branchEl = document.getElementById('f-branch') as HTMLInputElement | null;
  const branch  = branchEl ? (branchEl.value.trim() || 'main') : 'main';
  const init    = (document.getElementById('f-initialize')  as HTMLInputElement).checked;
  const visEl   = document.querySelector<HTMLInputElement>('input[name="visibility"]:checked');
  const vis     = visEl ? visEl.value : 'private';

  // Collect topics from Alpine.js data
  const alpineRoot = document.querySelector('.wizard-layout') as (Element & { _x_dataStack?: Array<{ topics: string[] }> }) | null;
  const topics: string[] = (alpineRoot?._x_dataStack?.[0])
    ? [...alpineRoot._x_dataStack[0].topics]
    : [];

  if (btn) { btn.disabled = true; btn.textContent = 'Creating…'; }
  try {
    const w = window as Record<string, unknown>;
    const token = typeof w.getToken === 'function' ? (w.getToken as () => string)() : '';
    if (!token) {
      if (typeof w.showTokenForm === 'function') (w.showTokenForm as (msg: string) => void)('Sign in to create a repository.');
      return;
    }
    const res = await fetch('/new', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, name, description: desc, visibility: vis, license,
                             topics, tags: [], initialize: init, defaultBranch: branch }),
    });
    if (res.status === 401 || res.status === 403) {
      if (typeof w.showTokenForm === 'function') (w.showTokenForm as (msg: string) => void)('Session expired — re-enter your JWT.');
      return;
    }
    const data = await res.json() as { redirect?: string; detail?: string };
    if (res.status === 201) {
      window.location.href = data.redirect!;
      return;
    }
    if (errorEl) { errorEl.textContent = '❌ ' + (data.detail || 'Failed to create repository.'); errorEl.style.display = ''; }
  } catch (ex) {
    if (errorEl) { errorEl.textContent = '❌ ' + (ex instanceof Error ? ex.message : String(ex)); errorEl.style.display = ''; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Create repository'; }
  }
}

export function initNewRepo(_data: NewRepoData): void {
  initTagInput('tag-input-container', 'tags-hidden');
  initVisibilityCards();
  const form = document.getElementById('wizard-form') as HTMLFormElement | null;
  form?.addEventListener('submit', (e) => void submitWizard(e));
}
