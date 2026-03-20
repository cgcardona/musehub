/**
 * diff.ts — Domain-aware diff page.
 *
 * Code repos  → syntax-highlighted file browser + unified diff view.
 * MIDI repos  → musical property deltas + artifact comparison.
 *
 * Config from window.__diffCfg (set by the page_data block).
 * Registered as: window.MusePages['diff']
 */

import hljs from 'highlight.js/lib/core';

// Register only the languages we support — keeps bundle small.
import python     from 'highlight.js/lib/languages/python';
import typescript from 'highlight.js/lib/languages/typescript';
import javascript from 'highlight.js/lib/languages/javascript';
import rust       from 'highlight.js/lib/languages/rust';
import go         from 'highlight.js/lib/languages/go';
import swift      from 'highlight.js/lib/languages/swift';
import kotlin     from 'highlight.js/lib/languages/kotlin';
import java       from 'highlight.js/lib/languages/java';
import ruby       from 'highlight.js/lib/languages/ruby';
import cpp        from 'highlight.js/lib/languages/cpp';
import haskell    from 'highlight.js/lib/languages/haskell';
import json       from 'highlight.js/lib/languages/json';
import yaml       from 'highlight.js/lib/languages/yaml';
import toml       from 'highlight.js/lib/languages/ini';  // TOML ≈ INI
import bash       from 'highlight.js/lib/languages/bash';
import xml        from 'highlight.js/lib/languages/xml';  // HTML/XML
import css        from 'highlight.js/lib/languages/css';
import sql        from 'highlight.js/lib/languages/sql';
import markdown   from 'highlight.js/lib/languages/markdown';
import plaintext  from 'highlight.js/lib/languages/plaintext';

hljs.registerLanguage('python',     python);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('rust',       rust);
hljs.registerLanguage('go',         go);
hljs.registerLanguage('swift',      swift);
hljs.registerLanguage('kotlin',     kotlin);
hljs.registerLanguage('java',       java);
hljs.registerLanguage('ruby',       ruby);
hljs.registerLanguage('cpp',        cpp);
hljs.registerLanguage('haskell',    haskell);
hljs.registerLanguage('json',       json);
hljs.registerLanguage('yaml',       yaml);
hljs.registerLanguage('toml',       toml);
hljs.registerLanguage('bash',       bash);
hljs.registerLanguage('xml',        xml);
hljs.registerLanguage('css',        css);
hljs.registerLanguage('sql',        sql);
hljs.registerLanguage('markdown',   markdown);
hljs.registerLanguage('plaintext',  plaintext);

// ── Types ─────────────────────────────────────────────────────────────────────

interface DiffCfg {
  repoId:     string;
  commitId:   string;
  base:       string;
  viewerType: string;   // 'piano_roll' | 'symbol_graph' | 'generic'
  domainName: string;
  commit:     CommitData | null;
}

interface CommitData {
  commitId:   string;
  message:    string;
  author:     string;
  timestamp:  string;
  branch:     string;
  parentIds?: string[];
}

interface TreeEntry {
  name:    string;
  path:    string;
  type:    string;   // 'file' | 'dir'
  size?:   number;
}

declare global {
  interface Window {
    __diffCfg?:          DiffCfg;
    escHtml:             (s: string) => string;
    apiFetch:            (path: string, init?: RequestInit) => Promise<unknown>;
    parseCommitMessage:  (msg: string) => { type: string; scope: string; subject: string };
    parseCommitMeta:     (msg: string) => Record<string, string>;
    initRepoNav?:        (repoId: string) => void;
    queueAudio?:         (url: string, name: string, repo: string) => void;
    shortSha?:           (sha: string) => string;
    MusePages:           Record<string, () => void>;
  }
}

// ── Global state ──────────────────────────────────────────────────────────────

let _cfg: DiffCfg;

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s: string): string { return window.escHtml(s); }
function apiFetch(path: string): Promise<unknown> { return window.apiFetch(path); }

function shortSha(sha: string): string {
  return typeof window.shortSha === 'function' ? window.shortSha(sha) : sha.slice(0, 8);
}

/** Map a file extension to a highlight.js language name. */
function extToLang(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    py: 'python', pyw: 'python',
    ts: 'typescript', tsx: 'typescript',
    js: 'javascript', jsx: 'javascript', mjs: 'javascript',
    rs: 'rust',
    go: 'go',
    swift: 'swift',
    kt: 'kotlin', kts: 'kotlin',
    java: 'java',
    rb: 'ruby',
    cpp: 'cpp', cc: 'cpp', cxx: 'cpp', c: 'cpp', h: 'cpp', hpp: 'cpp',
    hs: 'haskell',
    json: 'json',
    yaml: 'yaml', yml: 'yaml',
    toml: 'toml',
    sh: 'bash', bash: 'bash', zsh: 'bash',
    html: 'xml', htm: 'xml', xml: 'xml', svg: 'xml',
    css: 'css', scss: 'css', sass: 'css',
    sql: 'sql',
    md: 'markdown', mdx: 'markdown',
  };
  return map[ext] ?? 'plaintext';
}

/** Format bytes as human-readable string. */
function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Highlight source code and return an HTML table of line-numbered rows. */
function buildHighlightedLines(code: string, lang: string, isNew: boolean): string {
  let highlighted: string;
  try {
    highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    highlighted = esc(code);
  }

  const lines = highlighted.split('\n');
  // Remove trailing empty line from the split
  if (lines.length && lines[lines.length - 1] === '') lines.pop();

  const sign    = isNew ? '+' : ' ';
  const rowCls  = isNew ? 'diff-line-add' : 'diff-line-ctx';

  const rows = lines.map((html, i) =>
    `<tr class="${rowCls}">` +
    `<td class="diff-ln-sign">${sign}</td>` +
    `<td class="diff-ln-num">${i + 1}</td>` +
    `<td class="diff-ln-code"><span>${html}</span></td>` +
    `</tr>`
  ).join('');

  return `<table class="diff-table hljs"><tbody>${rows}</tbody></table>`;
}

// ── Code diff rendering ───────────────────────────────────────────────────────

async function renderCodeDiff(): Promise<void> {
  const container = document.getElementById('diff-content');
  if (!container) return;

  container.innerHTML = `<div class="diff-loading"><span class="spinner"></span> Loading file tree…</div>`;

  // Fetch tree at HEAD
  let entries: TreeEntry[] = [];
  try {
    const data = await apiFetch(`/repos/${_cfg.repoId}/tree/HEAD`) as { entries?: TreeEntry[] };
    entries = (data.entries ?? []).filter(e => e.type === 'file');
  } catch {
    container.innerHTML = `<p class="diff-error">⚠ Could not load file tree.</p>`;
    return;
  }

  if (entries.length === 0) {
    container.innerHTML = `<p class="diff-empty">No files in this repository yet.</p>`;
    return;
  }

  // Sort: dirs first (by depth proxy: more slashes = deeper), then alpha
  entries.sort((a, b) => a.path.localeCompare(b.path));

  const commit   = _cfg.commit;
  const parentId = commit?.parentIds?.[0] ?? null;
  const isRoot   = !parentId;
  const parsed   = commit ? window.parseCommitMessage(commit.message) : null;

  // Render the two-panel layout
  container.innerHTML = `
    <div class="diff-layout">
      <aside class="diff-file-tree" id="diff-tree">
        <div class="diff-tree-header">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          <span>${entries.length} file${entries.length !== 1 ? 's' : ''}</span>
        </div>
        <ul class="diff-file-list" id="diff-file-list">
          ${entries.map((e, idx) => `
          <li class="diff-file-item${idx === 0 ? ' active' : ''}"
              data-idx="${idx}" data-path="${esc(e.path)}"
              title="${esc(e.path)}">
            <span class="diff-file-sign diff-sign-add">+</span>
            <span class="diff-file-icon">${fileIcon(e.path)}</span>
            <span class="diff-file-name">${esc(e.path.split('/').pop() ?? e.path)}</span>
            ${e.size != null ? `<span class="diff-file-size">${fmtBytes(e.size)}</span>` : ''}
          </li>`).join('')}
        </ul>
      </aside>

      <div class="diff-viewer" id="diff-viewer">
        <div class="diff-viewer-header" id="diff-viewer-header">
          <div class="diff-file-path-bar">
            <span class="diff-file-path-label" id="diff-current-path">${esc(entries[0]?.path ?? '')}</span>
            <a class="btn btn-ghost btn-xs" id="diff-raw-link"
               href="/repos/${_cfg.repoId}/raw/HEAD/${esc(entries[0]?.path ?? '')}"
               target="_blank">Raw ↗</a>
          </div>
          ${isRoot
            ? `<span class="diff-root-badge">✦ Root commit — all files new</span>`
            : `<span class="diff-parent-badge">vs parent <a href="${_cfg.base}/commits/${parentId}" class="diff-parent-sha">${shortSha(parentId!)}</a></span>`}
        </div>
        <div id="diff-code-panel" class="diff-code-panel">
          <div class="diff-loading"><span class="spinner"></span> Loading…</div>
        </div>
      </div>
    </div>`;

  // Load the first file immediately
  if (entries[0]) await loadFile(entries[0].path, 0);

  // Click delegation on file list
  const fileList = document.getElementById('diff-file-list');
  if (fileList) {
    fileList.addEventListener('click', async e => {
      const li = (e.target as Element).closest<HTMLElement>('.diff-file-item');
      if (!li) return;
      const path = li.dataset.path ?? '';
      const idx  = Number(li.dataset.idx ?? 0);

      fileList.querySelectorAll('.diff-file-item').forEach(el => el.classList.remove('active'));
      li.classList.add('active');

      const pathLabel = document.getElementById('diff-current-path');
      const rawLink   = document.getElementById('diff-raw-link') as HTMLAnchorElement | null;
      if (pathLabel) pathLabel.textContent = path;
      if (rawLink)   rawLink.href = `/repos/${_cfg.repoId}/raw/HEAD/${path}`;

      await loadFile(path, idx);
    });
  }
}

function fileIcon(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const icons: Record<string, string> = {
    py: '🐍', ts: '📘', js: '📙', rs: '🦀', go: '🐹',
    swift: '🍎', kt: '🟣', java: '☕', rb: '💎', cpp: '⚙️',
    c: '⚙️', h: '⚙️', hs: '𝛌', md: '📝', json: '🗂️',
    yaml: '⚡', yml: '⚡', toml: '🔧', sh: '🔲', bash: '🔲',
    css: '🎨', scss: '🎨', html: '🌐', xml: '🌐', sql: '🗄️',
    txt: '📄', lock: '🔒', gitignore: '🚫',
  };
  return icons[ext] ?? '📄';
}

async function loadFile(path: string, _idx: number): Promise<void> {
  const panel = document.getElementById('diff-code-panel');
  if (!panel) return;
  panel.innerHTML = `<div class="diff-loading"><span class="spinner"></span> Loading ${esc(path)}…</div>`;

  try {
    // Fetch raw text content
    const resp = await fetch(`/repos/${_cfg.repoId}/raw/HEAD/${path}`);
    if (!resp.ok) {
      panel.innerHTML = `<p class="diff-error">⚠ ${resp.status}: Could not load file.</p>`;
      return;
    }
    const text = await resp.text();
    const lang  = extToLang(path);
    const table = buildHighlightedLines(text, lang, true);

    panel.innerHTML = `
      <div class="diff-hunk-header">
        <span class="diff-hunk-info">
          <span class="diff-lang-badge">${esc(lang)}</span>
          ${text.split('\n').length} lines
        </span>
      </div>
      <div class="diff-code-scroll">${table}</div>`;
  } catch (err) {
    panel.innerHTML = `<p class="diff-error">⚠ ${esc((err as Error).message)}</p>`;
  }
}

// ── MIDI diff rendering (legacy, cleaned up) ──────────────────────────────────

function metaDiff(a: string | null | undefined, b: string | null | undefined, label: string, icon: string): string {
  if (!a && !b) return '';
  if (a === b) return `
    <div class="meta-item">
      <span class="meta-label">${icon} ${label}</span>
      <span class="meta-value text-sm">${esc(a!)}</span>
    </div>`;
  return `
    <div class="meta-item">
      <span class="meta-label">${icon} ${label}</span>
      <span class="meta-value text-sm">
        ${a ? `<span style="text-decoration:line-through;color:var(--color-danger)">${esc(a)}</span> ` : ''}
        ${b ? `<span style="color:var(--color-success)">${esc(b)}</span>` : ''}
      </span>
    </div>`;
}

function seededWave(seed: number, color: string): string {
  let x = seed;
  const bars = Array.from({ length: 64 }, () => {
    x = (x * 1103515245 + 12345) & 0x7fffffff;
    const h = 10 + (x % 80);
    return `<div style="flex:1;background:${color};opacity:0.7;border-radius:1px 1px 0 0;min-height:4px;height:${h}%"></div>`;
  }).join('');
  return `<div style="display:flex;align-items:flex-end;gap:2px;height:80px;background:var(--bg-base);border-radius:var(--radius-sm);padding:var(--space-2)">${bars}</div>`;
}

async function renderMidiDiff(): Promise<void> {
  const container = document.getElementById('diff-content');
  if (!container) return;

  try {
    const commitsData = await apiFetch(`/repos/${_cfg.repoId}/commits?limit=200`) as { commits?: CommitData[] };
    const commits = commitsData.commits ?? [];
    const commit  = _cfg.commit ?? commits.find(c => c.commitId === _cfg.commitId);
    if (!commit) {
      container.innerHTML = '<p class="diff-error">Commit not found.</p>';
      return;
    }

    const parentId = (commit.parentIds ?? [])[0];
    const parent   = parentId ? commits.find(c => c.commitId === parentId) : null;
    const parsedChild  = window.parseCommitMessage(commit.message);
    const parsedParent = parent ? window.parseCommitMessage(parent.message) : null;
    const metaChild    = window.parseCommitMeta(commit.message);
    const metaParent   = parent ? window.parseCommitMeta(parent.message) : {} as Record<string, string>;

    const seed1 = parseInt(parentId ? parentId.slice(0, 8) : '0', 16) || 12345;
    const seed2 = parseInt(_cfg.commitId.slice(0, 8), 16) || 54321;

    container.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)">
          <a href="${_cfg.base}/commits/${_cfg.commitId}" class="btn btn-ghost btn-sm">← Back to commit</a>
          <h2 style="margin:0">State Diff</h2>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:var(--space-4);align-items:start;margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            ${parent
              ? `<a href="${_cfg.base}/commits/${parentId}" class="text-mono text-sm">${shortSha(parentId!)}</a>
                 <div class="text-sm text-muted" style="margin-top:4px">${esc(parsedParent!.subject || parent.message)}</div>`
              : '<span class="text-muted text-sm">Root commit — no parent</span>'}
          </div>
          <div style="font-size:24px;color:var(--text-muted);align-self:center">→</div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <a href="${_cfg.base}/commits/${_cfg.commitId}" class="text-mono text-sm">${shortSha(_cfg.commitId)}</a>
            <div class="text-sm text-muted" style="margin-top:4px">${esc(parsedChild.subject || commit.message)}</div>
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">State Properties</h3>
        <div class="meta-row" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));margin-bottom:var(--space-4)">
          ${metaDiff(metaParent['key'],                                metaChild['key'],                                'Key',    '♭')}
          ${metaDiff(metaParent['tempo'] || metaParent['bpm'],         metaChild['tempo'] || metaChild['bpm'],          'BPM',    '⏱')}
          ${metaDiff(metaParent['section'],                            metaChild['section'],                            'Section','♪')}
          ${metaDiff(parent ? parent.branch : null,                    commit.branch,                                   'Branch', '⑂')}
        </div>

        <h3 style="margin-bottom:var(--space-3)">Audio Waveform Comparison</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent ${parent ? shortSha(parentId!) : '—'}</div>
            ${seededWave(seed1, 'var(--color-accent)')}
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit ${shortSha(_cfg.commitId)}</div>
            ${seededWave(seed2, 'var(--color-success)')}
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">Commit Messages</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            <pre style="font-size:12px">${parent ? esc(parent.message) : 'None'}</pre>
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <pre style="font-size:12px">${esc(commit.message)}</pre>
          </div>
        </div>
      </div>`;
  } catch (e) {
    container.innerHTML = `<p class="diff-error">⚠ ${esc((e as Error).message)}</p>`;
  }
}

// ── Commit header (shared) ─────────────────────────────────────────────────────

function renderCommitHeader(commit: CommitData | null): void {
  const header = document.getElementById('diff-commit-header');
  if (!header || !commit) return;
  const parsed   = window.parseCommitMessage(commit.message);
  const parentId = (commit.parentIds ?? [])[0] ?? null;

  header.innerHTML = `
    <div class="diff-commit-meta">
      <a href="${_cfg.base}/commits/${commit.commitId}" class="btn btn-ghost btn-xs">← Commit</a>
      <span class="diff-commit-sha">${shortSha(commit.commitId)}</span>
      <span class="diff-commit-branch">⑂ ${esc(commit.branch ?? '—')}</span>
      <span class="diff-commit-author">${esc(commit.author ?? '')}</span>
    </div>
    <div class="diff-commit-msg">${esc(parsed.subject || commit.message)}</div>
    ${parentId
      ? `<div class="diff-commit-parent">
           <span class="text-muted text-xs">parent</span>
           <a href="${_cfg.base}/commits/${parentId}" class="text-mono text-xs">${shortSha(parentId)}</a>
         </div>`
      : `<span class="diff-root-pill">root commit</span>`}`;
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initDiff(): void {
  const cfg = window.__diffCfg;
  if (!cfg) return;
  _cfg = cfg;

  if (typeof window.initRepoNav === 'function') window.initRepoNav(_cfg.repoId);

  renderCommitHeader(_cfg.commit);

  if (_cfg.viewerType === 'piano_roll') {
    void renderMidiDiff();
  } else {
    void renderCodeDiff();
  }
}
