/**
 * tree.ts — File tree browser page module.
 *
 * Responsibilities:
 *  1. Fetch the file tree for the current ref/path and render it into #content.
 *  2. Populate the branch/tag selector and navigate on change.
 *  3. Map file extensions to emoji icons.
 *
 * Config is read from the page_json block (page: "tree").
 * Registered as: window.MusePages['tree']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface TreePageData {
  repo_id:   string;
  ref:       string;
  dir_path:  string;
  owner:     string;
  repo_slug: string;
  base:      string;
}

interface TreeEntry {
  type:       'dir' | 'file';
  name:       string;
  path:       string;
  sizeBytes?: number;
}

interface TreeData {
  entries?: TreeEntry[];
}

interface BranchData {
  branches?: Array<{ name: string }>;
}

declare global {
  interface Window {
    escHtml:  (s: unknown) => string;
    getToken: () => string;
  }
}

// ── Module state ──────────────────────────────────────────────────────────────

let _cfg: TreePageData;

// ── File-type icon ────────────────────────────────────────────────────────────

function fileIconHtml(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith('.mid') || lower.endsWith('.midi')) return '&#127929;';
  if (lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.endsWith('.ogg')) return '&#127925;';
  if (lower.endsWith('.json')) return '&#123;&#125;';
  if (lower.endsWith('.webp') || lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return '&#128444;';
  return '&#128196;';
}

// ── Human-readable file size ──────────────────────────────────────────────────

function fmtSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '';
  if (bytes < 1024) return bytes + '\u00a0B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + '\u00a0KB';
  return (bytes / 1048576).toFixed(1) + '\u00a0MB';
}

// ── URL builders ──────────────────────────────────────────────────────────────

function blobUrl(path: string): string {
  return _cfg.base + '/blob/' + encodeURIComponent(_cfg.ref) + '/' + path;
}

function treeUrl(path: string): string {
  return _cfg.base + '/tree/' + encodeURIComponent(_cfg.ref) + '/' + path;
}

// ── Fetch branch list ─────────────────────────────────────────────────────────

async function loadBranches(): Promise<void> {
  try {
    const tok     = window.getToken ? window.getToken() : (localStorage.getItem('muse_token') ?? '');
    const headers = tok ? { Authorization: 'Bearer ' + tok } : {} as Record<string, string>;
    const apiBase = '/api/v1/repos/' + _cfg.repo_id;
    const resp    = await fetch(apiBase + '/branches', { headers });
    if (!resp.ok) return;
    const data = (await resp.json()) as BranchData;
    const sel  = document.getElementById('branch-sel') as HTMLSelectElement | null;
    if (!sel) return;
    sel.innerHTML = '';
    const branches = data.branches ?? [];
    for (const b of branches) {
      const opt = document.createElement('option');
      opt.value       = b.name;
      opt.textContent = b.name;
      if (b.name === _cfg.ref) opt.selected = true;
      sel.appendChild(opt);
    }
    if (!branches.some(b => b.name === _cfg.ref)) {
      const opt = document.createElement('option');
      opt.value       = _cfg.ref;
      opt.textContent = _cfg.ref;
      opt.selected    = true;
      sel.prepend(opt);
    }
  } catch (_) { /* branch selector is non-critical */ }
}

// ── Render tree listing ───────────────────────────────────────────────────────

function renderTree(data: TreeData): void {
  const entries = data.entries ?? [];
  const esc     = window.escHtml;

  const headerHtml = '<div class="tree-header">'
    + '<div class="ref-selector">'
    + '<label>Branch&nbsp;/&nbsp;tag:</label>'
    + '<select id="branch-sel" data-ref-select>'
    + '<option value="' + esc(_cfg.ref) + '">' + esc(_cfg.ref) + '</option>'
    + '</select>'
    + '</div>'
    + '</div>';

  let bodyHtml: string;
  if (entries.length === 0) {
    bodyHtml = '<div class="tree-empty">This directory is empty.</div>';
  } else {
    let rows = '';
    for (const entry of entries) {
      if (entry.type === 'dir') {
        rows += '<tr>'
          + '<td><span class="tree-icon">&#128193;</span>'
          + '<a class="entry-link" href="' + treeUrl(entry.path) + '">' + esc(entry.name) + '</a></td>'
          + '<td class="tree-size"></td>'
          + '</tr>';
      } else {
        rows += '<tr>'
          + '<td><span class="tree-icon" title="' + esc(entry.name) + '">' + fileIconHtml(entry.name) + '</span>'
          + '<a class="entry-link" href="' + blobUrl(entry.path) + '">' + esc(entry.name) + '</a></td>'
          + '<td class="tree-size">' + fmtSize(entry.sizeBytes) + '</td>'
          + '</tr>';
      }
    }
    bodyHtml = '<table class="tree-table">'
      + '<thead><tr><th>Name</th><th style="text-align:right">Size</th></tr></thead>'
      + '<tbody>' + rows + '</tbody>'
      + '</table>';
  }

  const contentEl = document.getElementById('content');
  if (contentEl) contentEl.innerHTML = headerHtml + bodyHtml;

  void loadBranches();

  // Bind the branch selector after rendering
  const sel = document.getElementById('branch-sel') as HTMLSelectElement | null;
  sel?.addEventListener('change', () => {
    const newRef     = sel.value;
    const pathSuffix = _cfg.dir_path ? '/' + _cfg.dir_path : '';
    window.location.href = _cfg.base + '/tree/' + encodeURIComponent(newRef) + pathSuffix;
  });
}

// ── Load tree data ────────────────────────────────────────────────────────────

async function loadTree(): Promise<void> {
  const contentEl = document.getElementById('content');
  if (!contentEl) return;
  contentEl.innerHTML = '<div class="tree-loading">Loading tree\u2026</div>';

  try {
    const tok        = window.getToken ? window.getToken() : (localStorage.getItem('muse_token') ?? '');
    const headers    = tok ? { Authorization: 'Bearer ' + tok } : {} as Record<string, string>;
    const apiBase    = '/api/v1/repos/' + _cfg.repo_id;
    const pathSuffix = _cfg.dir_path ? '/' + encodeURIComponent(_cfg.dir_path) : '';
    const qs         = '?owner=' + encodeURIComponent(_cfg.owner)
                     + '&repo_slug=' + encodeURIComponent(_cfg.repo_slug);
    const url        = apiBase + '/tree/' + encodeURIComponent(_cfg.ref) + pathSuffix + qs;
    const resp       = await fetch(url, { headers });

    if (resp.status === 404) {
      contentEl.innerHTML = '<div class="tree-error">&#10060; Ref or path not found.</div>';
      return;
    }
    if (!resp.ok) {
      contentEl.innerHTML = `<div class="tree-error">&#10060; Failed to load tree (HTTP ${resp.status}).</div>`;
      return;
    }
    renderTree((await resp.json()) as TreeData);
  } catch (err) {
    contentEl.innerHTML = '<div class="tree-error">&#10060; ' + window.escHtml(String(err)) + '</div>';
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initTree(data: Record<string, unknown>): void {
  _cfg = {
    repo_id:   String(data.repo_id   ?? ''),
    ref:       String(data.ref       ?? ''),
    dir_path:  String(data.dir_path  ?? ''),
    owner:     String(data.owner     ?? ''),
    repo_slug: String(data.repo_slug ?? ''),
    base:      String(data.base      ?? ''),
  };
  void loadTree();
}
