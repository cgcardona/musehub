/**
 * repo-page.ts — universal initialiser for every repo-scoped page.
 *
 * Pages that only need repo-nav hydration register `{ "page": "repo" }` (or
 * include `"repo_id"` in their page_json block).  More complex pages extend
 * this and register their own key in MusePages.
 *
 * Registered as: window.MusePages['repo']
 */

export interface RepoPageData {
  page?: string;
  repo_id?: string;
  clone_musehub?: string;
  clone_https?: string;
  clone_ssh?: string;
  [key: string]: unknown;
}

function initCloneTabs(urls: Record<string, string>): void {
  const input = document.getElementById('clone-input') as HTMLInputElement | null;
  document.querySelectorAll<HTMLElement>('[data-clone-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-clone-tab]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      if (input) input.value = urls[btn.dataset.cloneTab!] ?? '';
    });
  });
}

function initCopyClone(): void {
  const btn   = document.getElementById('clone-copy-btn') as HTMLButtonElement | null;
  const input = document.getElementById('clone-input') as HTMLInputElement | null;
  if (!btn || !input) return;
  btn.addEventListener('click', () => {
    navigator.clipboard.writeText(input.value).then(() => {
      const orig = btn.innerHTML;
      btn.innerHTML = '✓ Copied!';
      btn.classList.add('clone-copy-flash');
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('clone-copy-flash'); }, 1800);
    });
  });
}

function initStarToggle(): void {
  const starBtn  = document.getElementById('nav-star-btn');
  const statCard = document.getElementById('stat-stars');
  [starBtn, statCard].forEach((el) => {
    el?.addEventListener('click', (e) => {
      e.preventDefault();
      const w = window as unknown as Record<string, unknown>;
      if (typeof w.toggleStar === 'function') {
        (w.toggleStar as () => void)();
      }
    });
  });
}

export function initRepoPage(data: RepoPageData): void {
  const repoId = data.repo_id;
  if (repoId && typeof window.initRepoNav === 'function') {
    window.initRepoNav(String(repoId));
  }
  if (data.clone_musehub !== undefined) {
    initCloneTabs({
      musehub: data.clone_musehub ?? '',
      https:   data.clone_https   ?? '',
      ssh:     data.clone_ssh     ?? '',
    });
    initCopyClone();
  }
  initStarToggle();
}
