/**
 * explore.ts — MuseHub explore page.
 *
 * Two modes:
 *   browse  — filter sidebar + SSR repo grid (HTMX fragments, unchanged)
 *   search  — live semantic/text search via /api/v1/search/repos and
 *             /api/v1/search?q=...&mode=keyword for commits
 *
 * The search bar is the focal point.  Typing anything ≥ 2 chars triggers a
 * debounced fetch; clearing returns to browse mode.
 */

declare global {
  interface Window {
    escHtml:  (s: string) => string;
    apiFetch: (path: string, init?: RequestInit) => Promise<unknown>;
    fmtDate:  (d: string) => string;
  }
}

// ── Repo result shape from /api/v1/search/repos ──────────────────────────────

interface RepoResult {
  repo_id:      string;
  name:         string | null;
  owner:        string;
  slug:         string;
  description:  string | null;
  tags:         string[];
  star_count:   number;
  commit_count: number;
  key_signature?: string | null;
  tempo_bpm?:   number | null;
}

interface SearchReposResponse {
  query:    string;
  semantic: boolean;
  repos:    RepoResult[];
}

// Commit group from /api/v1/search (global cross-repo commit search)
interface CommitMatch {
  commit_id: string;
  message:   string;
  author:    string;
  branch:    string;
}
interface CommitGroup {
  repo_id:   string;
  repo_name: string;
  owner:     string;
  matches:   CommitMatch[];
}
interface CommitSearchResponse {
  groups:      CommitGroup[];
  total_repos: number;
}

// ── SVG helpers ──────────────────────────────────────────────────────────────

const SVG_STAR   = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
const SVG_COMMIT = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><line x1="3" y1="12" x2="9" y2="12"/><line x1="15" y1="12" x2="21" y2="12"/></svg>`;

// ── Entry point ───────────────────────────────────────────────────────────────

export function initExplore(): void {
  setupBrowseMode();
  setupSemanticSearch();
  wireNavbarSearch();
}

// ── Wire navbar search → hero search on explore page ─────────────────────────

function wireNavbarSearch(): void {
  const navForm  = document.querySelector<HTMLFormElement>('.navbar-search-form');
  const navInput = document.querySelector<HTMLInputElement>('.navbar-search-input');
  const heroInput = document.getElementById('ex-search-input') as HTMLInputElement | null;
  if (!navForm || !navInput || !heroInput) return;

  // Prevent the navbar form from navigating away
  navForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = navInput.value.trim();
    if (q) heroInput.value = q;
    heroInput.focus();
    heroInput.dispatchEvent(new Event('input', { bubbles: true }));
    navInput.value = '';
  });

  navInput.addEventListener('focus', () => {
    heroInput.focus();
    navInput.blur();
  });
}

// ── Browse mode (existing HTMX chip/filter behaviour) ────────────────────────

function setupBrowseMode(): void {
  const filterForm = document.getElementById('filter-form') as HTMLFormElement | null;
  filterForm?.addEventListener('submit', function () {
    Array.from(this.elements).forEach((el) => {
      const input = el as HTMLInputElement | HTMLSelectElement;
      if ((input.tagName === 'SELECT' || input.tagName === 'INPUT') && input.value === '') {
        input.disabled = true;
      }
    });
  });

  document.querySelectorAll<HTMLElement>('[data-autosubmit]').forEach((el) => {
    el.addEventListener('change', () => (el.closest('form') as HTMLFormElement)?.requestSubmit());
  });

  document.querySelectorAll<HTMLAnchorElement>('[data-filter][data-value]').forEach((chip) => {
    chip.addEventListener('click', (evt) => {
      evt.preventDefault();
      const filterName = chip.dataset.filter ?? '';
      const value      = chip.dataset.value ?? '';
      const params     = new URLSearchParams(window.location.search);
      const current    = params.getAll(filterName);

      if (current.includes(value)) {
        params.delete(filterName);
        current.filter((v) => v !== value).forEach((v) => params.append(filterName, v));
        chip.classList.remove('active');
      } else {
        params.append(filterName, value);
        chip.classList.add('active');
      }

      const url = '/explore?' + params.toString();
      history.pushState({}, '', url);

      const htmx = (window as unknown as Record<string, unknown>).htmx as
        | { ajax: (m: string, u: string, o: Record<string, unknown>) => void }
        | undefined;
      htmx?.ajax('GET', url, { target: '#repo-grid', swap: 'innerHTML' });
    });
  });

  document.querySelectorAll<HTMLElement>('[data-action="toggle-sidebar"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelector('.explore-sidebar')?.classList.toggle('open');
    });
  });
}

// ── Semantic search mode ──────────────────────────────────────────────────────

function setupSemanticSearch(): void {
  const searchInput     = document.getElementById('ex-search-input') as HTMLInputElement | null;
  const searchClear     = document.getElementById('ex-search-clear') as HTMLButtonElement | null;
  const searchSpinner   = document.getElementById('ex-search-spinner') as HTMLElement | null;
  const searchField     = document.getElementById('ex-search-field') as HTMLElement | null;
  const semanticResults = document.getElementById('ex-semantic-results') as HTMLElement | null;
  const browseLayout    = document.getElementById('ex-browse-layout') as HTMLElement | null;
  const typeBar         = document.getElementById('ex-type-bar') as HTMLElement | null;
  const semanticDot     = document.getElementById('ex-semantic-indicator') as HTMLElement | null;

  if (!searchInput || !semanticResults) return;

  let debounceTimer:   ReturnType<typeof setTimeout> | null = null;
  let currentQuery   = '';
  let currentType    = 'repos';
  let pendingAbort: AbortController | null = null;

  // ── Example query chips ──────────────────────────────────────────────────
  document.querySelectorAll<HTMLButtonElement>('[data-query]').forEach((chip) => {
    chip.addEventListener('click', () => {
      searchInput.value = chip.dataset.query ?? '';
      searchInput.dispatchEvent(new Event('input'));
      searchInput.focus();
    });
  });

  // ── Search type toggle ───────────────────────────────────────────────────
  document.querySelectorAll<HTMLButtonElement>('[data-search-type]').forEach((pill) => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('[data-search-type]').forEach((p) =>
        p.classList.remove('ex-type-pill--active'),
      );
      pill.classList.add('ex-type-pill--active');
      currentType = pill.dataset.searchType ?? 'repos';
      if (currentQuery.length >= 2) scheduleSearch(currentQuery);
    });
  });

  // ── Clear button ─────────────────────────────────────────────────────────
  searchClear?.addEventListener('click', () => {
    searchInput.value = '';
    clearSearch();
  });

  // ── Input → debounce ─────────────────────────────────────────────────────
  searchInput.addEventListener('input', () => {
    currentQuery = searchInput.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);

    if (!currentQuery) { clearSearch(); return; }
    if (searchClear) searchClear.style.display = 'flex';
    if (typeBar)     typeBar.style.display = 'flex';
    scheduleSearch(currentQuery);
  });

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { searchInput.value = ''; clearSearch(); }
  });

  function scheduleSearch(q: string): void {
    debounceTimer = setTimeout(() => performSearch(q, currentType), 300);
  }

  function clearSearch(): void {
    if (pendingAbort) { pendingAbort.abort(); pendingAbort = null; }
    currentQuery = '';
    if (searchClear)     searchClear.style.display = 'none';
    if (typeBar)         typeBar.style.display = 'none';
    if (semanticDot)     semanticDot.style.display = 'none';
    if (semanticResults) semanticResults.style.display = 'none';
    if (browseLayout)    browseLayout.style.display = '';
    if (searchField)     searchField.classList.remove('ex-search-field--active');
  }

  // ── Main search fetch ─────────────────────────────────────────────────────
  async function performSearch(q: string, type: string): Promise<void> {
    if (pendingAbort) pendingAbort.abort();
    pendingAbort = new AbortController();

    setLoading(true);
    if (searchField) searchField.classList.add('ex-search-field--active');

    try {
      let data: unknown;
      if (type === 'repos') {
        data = await window.apiFetch(
          `/search/repos?q=${encodeURIComponent(q)}&limit=20`,
        );
      } else {
        // Commits: use global search endpoint (keyword mode)
        data = await window.apiFetch(
          `/search?q=${encodeURIComponent(q)}&mode=keyword&page_size=10`,
        );
      }
      renderResults(data, q, type);
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      renderError(err as Error);
    } finally {
      setLoading(false);
      pendingAbort = null;
    }
  }

  function setLoading(on: boolean): void {
    if (searchSpinner) searchSpinner.style.display = on ? 'flex' : 'none';
    if (browseLayout && on) browseLayout.style.opacity = '0.3';
    if (browseLayout && !on) browseLayout.style.opacity = '';
  }

  // ── Result rendering ──────────────────────────────────────────────────────
  function renderResults(data: unknown, q: string, type: string): void {
    if (!semanticResults) return;

    if (browseLayout) { browseLayout.style.display = 'none'; browseLayout.style.opacity = ''; }
    semanticResults.style.display = 'block';

    const html = type === 'repos'
      ? renderRepoResults(data as SearchReposResponse, q)
      : renderCommitResults(data as CommitSearchResponse, q);

    semanticResults.innerHTML = html;
  }

  function renderRepoResults(data: SearchReposResponse, q: string): string {
    const repos     = data.repos ?? [];
    const isSem     = Boolean(data.semantic);

    if (semanticDot) semanticDot.style.display = isSem ? 'flex' : 'none';

    const methodBadge = isSem
      ? `<span class="ex-sr-method ex-sr-method--semantic">vector search · ℝ¹⁵³⁶</span>`
      : `<span class="ex-sr-method ex-sr-method--text">text search</span>`;

    if (!repos.length) {
      return `<div class="ex-sr-empty">
        <div class="ex-sr-empty-icon">⌖</div>
        <p class="ex-sr-empty-title">No repos found for <em>"${window.escHtml(q)}"</em></p>
        <p class="ex-sr-empty-sub">Try different terms — or <a href="/explore">browse all repositories</a></p>
      </div>`;
    }

    const header = `<div class="ex-sr-header">
      <span class="ex-sr-count">${repos.length} result${repos.length !== 1 ? 's' : ''}</span>
      ${methodBadge}
      <span class="ex-sr-query">"${window.escHtml(q)}"</span>
    </div>`;

    const cards = repos.map((repo, idx) => {
      const href  = `/${window.escHtml(repo.owner)}/${window.escHtml(repo.slug)}`;
      const name  = repo.name || repo.slug;
      const desc  = repo.description || '';
      const tags  = repo.tags ?? [];
      // Visual rank: first result gets full bar, last ~25%
      const total = Math.max(repos.length - 1, 1);
      const rankPct = isSem ? Math.round(100 - (idx / total) * 75) : 0;

      const tagHtml = tags.slice(0, 4)
        .map((t) => `<span class="tag-pill">${window.escHtml(String(t))}</span>`)
        .join('');

      const musePips = [
        repo.key_signature ? `<span class="ex-sr-pip ex-sr-pip--key">♩ ${window.escHtml(repo.key_signature)}</span>` : '',
        repo.tempo_bpm     ? `<span class="ex-sr-pip ex-sr-pip--tempo">♩ ${repo.tempo_bpm} bpm</span>` : '',
      ].filter(Boolean).join('');

      return `<a href="${href}" class="repo-card">
        <div class="repo-card-header">
          <span class="repo-card-name">${window.escHtml(repo.owner)}<span class="repo-card-sep">/</span>${window.escHtml(repo.slug)}</span>
          ${isSem ? `<span class="ex-sr-score">${rankPct}%</span>` : ''}
        </div>
        ${desc ? `<p class="repo-card-desc">${window.escHtml(desc.length > 120 ? desc.slice(0, 117) + '…' : desc)}</p>` : ''}
        ${tagHtml ? `<div class="repo-card-pills">${tagHtml}</div>` : ''}
        <div class="repo-card-footer">
          <span class="repo-card-stat">${SVG_STAR} ${repo.star_count}</span>
          <span class="repo-card-stat">${SVG_COMMIT} ${repo.commit_count} commits</span>
          ${isSem ? `<span class="ex-sr-method ex-sr-method--semantic" style="margin-left:auto">vector</span>` : ''}
        </div>
      </a>`;
    }).join('');

    return header + `<div class="ex-sr-list">${cards}</div>`;
  }

  function renderCommitResults(data: CommitSearchResponse, q: string): string {
    if (semanticDot) semanticDot.style.display = 'none';

    const groups = data.groups ?? [];
    if (!groups.length) {
      return `<div class="ex-sr-empty">
        <div class="ex-sr-empty-icon">⌖</div>
        <p class="ex-sr-empty-title">No commits found for <em>"${window.escHtml(q)}"</em></p>
        <p class="ex-sr-empty-sub">Try different terms or switch to <strong>Repos</strong> search above</p>
      </div>`;
    }

    const totalMatches = groups.reduce((s, g) => s + g.matches.length, 0);
    const header = `<div class="ex-sr-header">
      <span class="ex-sr-count">${totalMatches} commit match${totalMatches !== 1 ? 'es' : ''} across ${groups.length} repo${groups.length !== 1 ? 's' : ''}</span>
      <span class="ex-sr-method ex-sr-method--text">keyword search</span>
      <span class="ex-sr-query">"${window.escHtml(q)}"</span>
    </div>`;

    const items = groups.map((group) => {
      const repoHref = `/${window.escHtml(group.owner)}/${window.escHtml(group.repo_name)}`;
      const matchRows = group.matches.slice(0, 5).map((m) => {
        const cHref = `${repoHref}/commits/${window.escHtml(m.commit_id)}`;
        // Extract conventional commit prefix for coloring
        const ct    = (m.message || '').match(/^(\w+)[\(!:]/)?.[1]?.toLowerCase() ?? '';
        const ctCol: Record<string, string> = {
          feat:'#3fb950', fix:'#f85149', refactor:'#bc8cff',
          docs:'#6e96c9', chore:'#6e7681', perf:'#f0883e',
        };
        const ctStyle = ct && ctCol[ct] ? `color:${ctCol[ct]}` : '';
        return `<a href="${cHref}" class="ex-sr-commit">
          <code class="ex-sr-commit-sha">${window.escHtml(m.commit_id.slice(0, 8))}</code>
          <span class="ex-sr-commit-msg" style="${ctStyle}">${window.escHtml(m.message.length > 90 ? m.message.slice(0, 87) + '…' : m.message)}</span>
          <span class="ex-sr-commit-author">${window.escHtml(m.author)}</span>
        </a>`;
      }).join('');

      return `<div class="ex-sr-commit-group">
        <a href="${repoHref}" class="ex-sr-commit-group-repo">${window.escHtml(group.owner)}/${window.escHtml(group.repo_name)}</a>
        <div class="ex-sr-commit-rows">${matchRows}</div>
      </div>`;
    }).join('');

    return header + `<div class="ex-sr-commit-list">${items}</div>`;
  }

  function renderError(err: Error): void {
    if (!semanticResults) return;
    if (browseLayout) { browseLayout.style.display = ''; browseLayout.style.opacity = ''; }
    semanticResults.innerHTML = `<div class="ex-sr-empty">
      <div class="ex-sr-empty-icon">⚠</div>
      <p class="ex-sr-empty-title">Search unavailable</p>
      <p class="ex-sr-empty-sub">${window.escHtml(err.message)}</p>
    </div>`;
    semanticResults.style.display = 'block';
  }
}
