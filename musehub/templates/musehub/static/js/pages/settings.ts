/**
 * settings.ts — Repository settings page.
 *
 * Handles topic tag input, collaborator invite, and delete confirmation guard.
 * Config is read from the #page-data JSON element.
 * Registered as: window.MusePages['settings']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface SettingsCfg {
  repoId:   string;
  owner:    string;
  repoSlug: string;
  base:     string;
  fullName: string;
}

declare global {
  interface Window {
    getToken?: () => string | null;
    htmx?: { trigger(el: Element | string, event: string): void };
  }
}

// ── Topic tag input ───────────────────────────────────────────────────────────

function addTopic(val: string, input: HTMLInputElement): void {
  const cleaned   = val.trim().toLowerCase().replace(/[^a-z0-9-]/g, '-');
  const container = document.getElementById('topics-container');
  if (!cleaned || !container) return;

  const pill = document.createElement('span');
  pill.className   = 'tag-pill';
  const removeBtn  = document.createElement('button');
  removeBtn.type        = 'button';
  removeBtn.className   = 'tag-pill-remove';
  removeBtn.dataset.action = 'remove-pill';
  removeBtn.textContent = '×';
  pill.textContent = cleaned;
  pill.appendChild(removeBtn);
  container.insertBefore(pill, input);
  input.value = '';
}

function setupTopicInput(): void {
  const input = document.getElementById('topic-input') as HTMLInputElement | null;
  if (!input) return;

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTopic(input.value, input);
    } else if (e.key === 'Backspace' && input.value === '') {
      const container = document.getElementById('topics-container');
      const pills     = container ? container.querySelectorAll('.tag-pill') : [];
      if (pills.length > 0) pills[pills.length - 1].remove();
    }
  });
}

// ── Collaborator invite ───────────────────────────────────────────────────────

async function inviteCollaborator(repoId: string): Promise<void> {
  const usernameEl = document.getElementById('invite-username') as HTMLInputElement | null;
  const roleEl     = document.getElementById('invite-role')    as HTMLSelectElement | null;
  const msgEl      = document.getElementById('invite-msg')     as HTMLElement | null;
  if (!usernameEl || !roleEl || !msgEl) return;

  const username = usernameEl.value.trim();
  const role     = roleEl.value;
  if (!username) return;

  try {
    const token   = typeof window.getToken === 'function' ? window.getToken() : null;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;

    const resp = await fetch('/api/v1/repos/' + repoId + '/collaborators', {
      method: 'POST',
      headers,
      body:   JSON.stringify({ username, role }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText })) as { detail?: string };
      msgEl.textContent  = '❌ ' + (err.detail || 'Invite failed.');
      msgEl.style.color  = '#f85149';
    } else {
      usernameEl.value   = '';
      msgEl.textContent  = '✅ Invited ' + username;
      msgEl.style.color  = '#3fb950';
      const listEl       = document.getElementById('collaborators-list');
      if (listEl && window.htmx) window.htmx.trigger(listEl, 'load');
    }
    msgEl.style.display = 'block';
    setTimeout(() => { msgEl.style.display = 'none'; }, 5000);
  } catch(e) {
    msgEl.textContent  = '❌ ' + (e as Error).message;
    msgEl.style.color  = '#f85149';
    msgEl.style.display = 'block';
  }
}

// ── Delete confirmation guard ─────────────────────────────────────────────────

function setupDeleteGuard(fullName: string): void {
  const form = document.getElementById('delete-repo-form');
  if (!form) return;

  form.addEventListener('htmx:before-request', (e) => {
    const val      = (document.getElementById('confirm-delete-name') as HTMLInputElement | null)?.value.trim();
    const errorEl  = document.getElementById('delete-name-error') as HTMLElement | null;
    if (val !== fullName) {
      if (errorEl) errorEl.style.display = 'block';
      (e as CustomEvent).preventDefault();
    }
  });
}

// ── Event delegation ──────────────────────────────────────────────────────────

function setupEventDelegation(cfg: SettingsCfg): void {
  document.addEventListener('click', (e) => {
    const target = (e.target as Element).closest<HTMLElement>('[data-action]');
    if (!target) return;
    switch (target.dataset.action) {
      case 'remove-pill':
        target.parentElement?.remove();
        break;
      case 'invite-collaborator':
        void inviteCollaborator(cfg.repoId);
        break;
    }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initSettings(data: Record<string, unknown> = {}): void {
  const cfg: SettingsCfg = {
    repoId:   String(data['repoId']   ?? ''),
    owner:    String(data['owner']    ?? ''),
    repoSlug: String(data['repoSlug'] ?? ''),
    base:     String(data['base']     ?? ''),
    fullName: String(data['fullName'] ?? ''),
  };
  if (!cfg.repoId) return;
  setupTopicInput();
  setupEventDelegation(cfg);
  setupDeleteGuard(cfg.fullName);
}
