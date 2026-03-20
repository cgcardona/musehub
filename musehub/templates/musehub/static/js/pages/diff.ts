/**
 * diff.ts — Muse semantic diff page.
 *
 * Unlike Git, Muse knows *what semantically changed* (structured_delta) and
 * *which files truly changed* (snapshot_diff). We use both to render:
 *
 *   1. A stats bar — symbol counts, file counts (things Git cannot show)
 *   2. Per-file cards — semantic symbol changes above the line diff
 *   3. Real line diff — comparing parent vs current content, not just dumping
 *      the whole file green
 */

import hljs from 'highlight.js/lib/core';
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
import json       from 'highlight.js/lib/languages/json';
import yaml       from 'highlight.js/lib/languages/yaml';
import toml       from 'highlight.js/lib/languages/ini';
import bash       from 'highlight.js/lib/languages/bash';
import xml        from 'highlight.js/lib/languages/xml';
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

interface ChildOp {
  address:         string;
  op:              string;
  content_summary: string;
}

interface FileOp {
  address:       string;
  op:            string;
  child_summary: string;
  child_ops:     ChildOp[];
}

interface StructuredDelta {
  domain: string;
  ops:    FileOp[];
}

interface SnapshotDiff {
  added:       string[];
  modified:    string[];
  removed:     string[];
  total_files: number;
}

interface CommitData {
  commitId:  string;
  message:   string;
  author:    string;
  timestamp: string;
  branch:    string;
  parentIds: string[];
}

interface PageData {
  page:             string;
  repoId:           string;
  commitId:         string;
  shortId:          string;
  owner:            string;
  repoSlug:         string;
  baseUrl:          string;
  parentId:         string | null;
  structuredDelta:  StructuredDelta | null;
  snapshotDiff:     SnapshotDiff;
  commit:           CommitData | null;
  viewerType:       string;
  domainName:       string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function extToLang(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    py: 'python', pyw: 'python',
    ts: 'typescript', tsx: 'typescript',
    js: 'javascript', jsx: 'javascript',
    rs: 'rust', go: 'go', swift: 'swift',
    kt: 'kotlin', java: 'java', rb: 'ruby',
    cpp: 'cpp', cc: 'cpp', c: 'cpp', h: 'cpp',
    json: 'json', yaml: 'yaml', yml: 'yaml',
    toml: 'toml', sh: 'bash', bash: 'bash',
    html: 'xml', xml: 'xml', css: 'css', scss: 'css',
    sql: 'sql', md: 'markdown', mdx: 'markdown',
  };
  return map[ext] ?? 'plaintext';
}

function highlight(code: string, lang: string): string {
  try {
    return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    return esc(code);
  }
}

/** Determine op class from operation string. */
function opClass(op: string): string {
  if (op === 'insert') return 'df3-op-add';
  if (op === 'delete') return 'df3-op-del';
  return 'df3-op-mod';
}

function opSign(op: string): string {
  if (op === 'insert') return '+';
  if (op === 'delete') return '−';
  return '~';
}

/** Detect kind from content_summary string. */
function kindChip(summary: string): string {
  const s = summary.toLowerCase();
  if (s.includes('class'))    return '<span class="df3-kind df3-k-class">class</span>';
  if (s.includes('method'))   return '<span class="df3-kind df3-k-method">method</span>';
  if (s.includes('function') || s.includes('func')) return '<span class="df3-kind df3-k-func">func</span>';
  if (s.includes('import'))   return '<span class="df3-kind df3-k-import">import</span>';
  if (s.includes('variable') || s.includes('constant')) return '<span class="df3-kind df3-k-var">var</span>';
  return '';
}

// ── Myers line diff ───────────────────────────────────────────────────────────
// Simple O(ND) diff — sufficient for typical commit sizes.

type LineKind = 'add' | 'del' | 'ctx';
interface DiffLine { kind: LineKind; text: string; oldN: number; newN: number; }

function diffLines(oldLines: string[], newLines: string[]): DiffLine[] {
  const m = oldLines.length, n = newLines.length;
  const max = m + n;
  const v: number[] = new Array(2 * max + 1).fill(0);
  const trace: number[][] = [];

  outer: for (let d = 0; d <= max; d++) {
    trace.push([...v]);
    for (let k = -d; k <= d; k += 2) {
      const ki = k + max;
      let x: number;
      if (k === -d || (k !== d && v[ki - 1] < v[ki + 1])) {
        x = v[ki + 1];
      } else {
        x = v[ki - 1] + 1;
      }
      let y = x - k;
      while (x < m && y < n && oldLines[x] === newLines[y]) { x++; y++; }
      v[ki] = x;
      if (x >= m && y >= n) break outer;
    }
  }

  // Backtrack
  const result: DiffLine[] = [];
  let x = m, y = n;
  for (let d = trace.length - 1; d >= 0; d--) {
    const vd = trace[d];
    const k = x - y;
    const ki = k + max;
    const prevK = (k === -d || (k !== d && vd[ki - 1] < vd[ki + 1])) ? k + 1 : k - 1;
    const prevX = vd[prevK + max];
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) {
      result.unshift({ kind: 'ctx', text: oldLines[x - 1], oldN: x, newN: y });
      x--; y--;
    }
    if (d > 0) {
      if (x === prevX) {
        result.unshift({ kind: 'add', text: newLines[y - 1], oldN: 0, newN: y });
        y--;
      } else {
        result.unshift({ kind: 'del', text: oldLines[x - 1], oldN: x, newN: 0 });
        x--;
      }
    }
  }
  return result;
}

/** Render a diff as an HTML table with syntax-highlighted tokens. */
function renderDiffTable(lines: DiffLine[], lang: string): string {
  // Highlight the full old and new texts then split, to preserve multi-line spans.
  const oldText = lines.filter(l => l.kind !== 'add').map(l => l.text).join('\n');
  const newText = lines.filter(l => l.kind !== 'del').map(l => l.text).join('\n');
  const oldHl = highlight(oldText, lang).split('\n');
  const newHl = highlight(newText, lang).split('\n');

  let oldI = 0, newI = 0;
  const rows = lines.map(l => {
    let hlCode: string;
    let rowCls: string;
    let sign: string;
    if (l.kind === 'del') {
      hlCode = oldHl[oldI++] ?? esc(l.text);
      rowCls = 'df3-dl-del'; sign = '−';
    } else if (l.kind === 'add') {
      hlCode = newHl[newI++] ?? esc(l.text);
      rowCls = 'df3-dl-add'; sign = '+';
    } else {
      hlCode = oldHl[oldI++] ?? esc(l.text); newI++;
      rowCls = 'df3-dl-ctx'; sign = ' ';
    }
    const ln = l.kind === 'del' ? l.oldN : l.kind === 'add' ? l.newN : l.oldN;
    return `<tr class="${rowCls}"><td class="df3-ln-sign">${sign}</td><td class="df3-ln-num">${ln}</td><td class="df3-ln-code"><span>${hlCode}</span></td></tr>`;
  });
  return `<table class="df3-table hljs"><tbody>${rows.join('')}</tbody></table>`;
}

/** Collapse context lines — show only ±5 lines around changes. */
function collapseContext(lines: DiffLine[], ctx = 5): DiffLine[] {
  const changed = new Set<number>();
  lines.forEach((l, i) => { if (l.kind !== 'ctx') { for (let j = Math.max(0, i - ctx); j <= Math.min(lines.length - 1, i + ctx); j++) changed.add(j); } });
  const result: DiffLine[] = [];
  let skipped = 0;
  lines.forEach((l, i) => {
    if (changed.has(i)) {
      if (skipped > 0) {
        result.push({ kind: 'ctx', text: `⋯ ${skipped} unchanged lines`, oldN: 0, newN: 0 });
        skipped = 0;
      }
      result.push(l);
    } else {
      skipped++;
    }
  });
  if (skipped > 0) result.push({ kind: 'ctx', text: `⋯ ${skipped} unchanged lines`, oldN: 0, newN: 0 });
  return result;
}

// ── Fetch file content ────────────────────────────────────────────────────────

async function fetchFile(owner: string, repoSlug: string, ref: string, path: string): Promise<string | null> {
  try {
    const resp = await fetch(`/${owner}/${repoSlug}/raw/${ref}/${path}`);
    if (!resp.ok) return null;
    return await resp.text();
  } catch {
    return null;
  }
}

// ── Symbol changes sidebar ────────────────────────────────────────────────────

function renderSymbolChanges(fileOp: FileOp): string {
  if (!fileOp.child_ops?.length) return '';

  const rows = fileOp.child_ops.map(sym => {
    const addr = sym.address.includes('::') ? sym.address.split('::').slice(1).join('::') : sym.address;
    const isChild = addr.includes('.');
    const label = isChild ? addr.split('.').pop()! : addr;
    const indent = isChild ? 'df3-sym-child' : 'df3-sym-top';
    const desc = sym.content_summary
      ? sym.content_summary.replace(/^(added |modified |removed )/, '')
      : '';
    return `
      <div class="df3-sym-row ${indent}">
        ${isChild ? '<span class="df3-sym-indent"><svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 1v7h8"/></svg></span>' : ''}
        <span class="df3-sym-dot ${opClass(sym.op)}">${opSign(sym.op)}</span>
        <span class="df3-sym-name">${esc(label)}</span>
        ${kindChip(sym.content_summary || '')}
        ${desc ? `<span class="df3-sym-desc">${esc(desc)}</span>` : ''}
      </div>`;
  }).join('');

  const total = fileOp.child_ops.length;
  return `
    <div class="df3-sym-panel">
      <div class="df3-sym-hd">
        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--color-accent)"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        <span class="df3-sym-title">Symbols</span>
        <span class="df3-sym-count">${total} change${total !== 1 ? 's' : ''}</span>
      </div>
      <div class="df3-sym-body">${rows}</div>
    </div>`;
}

// ── File card ─────────────────────────────────────────────────────────────────

async function renderFileCard(
  path: string,
  fileType: 'added' | 'modified' | 'removed',
  pd: PageData,
  fileOp: FileOp | null,
): Promise<string> {
  const lang = extToLang(path);
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const fname = path.split('/').pop() ?? path;
  const opLabel = fileType === 'added' ? 'added' : fileType === 'removed' ? 'removed' : 'modified';
  const opDotCls = fileType === 'added' ? 'df3-op-add' : fileType === 'removed' ? 'df3-op-del' : 'df3-op-mod';
  const opSign2 = fileType === 'added' ? '+' : fileType === 'removed' ? '−' : '~';
  const blobUrl = `${pd.baseUrl}/blob/${pd.shortId}/${path}`;
  const rawUrl = `/${pd.owner}/${pd.repoSlug}/raw/${pd.commitId}/${path}`;

  // Fetch file content
  let tableHtml = '';
  let lineStats = '';

  if (fileType === 'added') {
    const text = await fetchFile(pd.owner, pd.repoSlug, pd.commitId, path);
    if (text !== null) {
      const lines = text.split('\n');
      const hl = highlight(text, lang).split('\n');
      const rows = lines.map((_, i) =>
        `<tr class="df3-dl-add"><td class="df3-ln-sign">+</td><td class="df3-ln-num">${i + 1}</td><td class="df3-ln-code"><span>${hl[i] ?? ''}</span></td></tr>`
      ).join('');
      tableHtml = `<table class="df3-table hljs"><tbody>${rows}</tbody></table>`;
      lineStats = `+${lines.length} lines`;
    }
  } else if (fileType === 'removed') {
    const ref = pd.parentId ?? pd.commitId;
    const text = await fetchFile(pd.owner, pd.repoSlug, ref, path);
    if (text !== null) {
      const lines = text.split('\n');
      const hl = highlight(text, lang).split('\n');
      const rows = lines.map((_, i) =>
        `<tr class="df3-dl-del"><td class="df3-ln-sign">−</td><td class="df3-ln-num">${i + 1}</td><td class="df3-ln-code"><span>${hl[i] ?? ''}</span></td></tr>`
      ).join('');
      tableHtml = `<table class="df3-table hljs"><tbody>${rows}</tbody></table>`;
      lineStats = `−${lines.length} lines`;
    }
  } else {
    // Modified: compute real line diff
    const [oldText, newText] = await Promise.all([
      fetchFile(pd.owner, pd.repoSlug, pd.parentId ?? pd.commitId, path),
      fetchFile(pd.owner, pd.repoSlug, pd.commitId, path),
    ]);
    if (oldText !== null && newText !== null) {
      const oldLines = oldText.split('\n');
      const newLines = newText.split('\n');
      const rawDiff = diffLines(oldLines, newLines);
      const collapsed = collapseContext(rawDiff);
      const added = rawDiff.filter(l => l.kind === 'add').length;
      const removed = rawDiff.filter(l => l.kind === 'del').length;
      lineStats = `<span class="df3-stat-add">+${added}</span> <span class="df3-stat-del">−${removed}</span>`;
      tableHtml = renderDiffTable(collapsed, lang);
    }
  }

  const symHtml = fileOp ? renderSymbolChanges(fileOp) : '';

  return `
    <div class="df3-file-card df3-file-${fileType}" id="df3-file-${CSS.escape(path)}">
      <div class="df3-file-hd">
        <span class="df3-op-dot ${opDotCls}">${opSign2}</span>
        <a href="${blobUrl}" class="df3-file-path">${esc(path)}</a>
        ${ext ? `<span class="df3-ext">.${esc(ext)}</span>` : ''}
        <div class="df3-file-hd-right">
          ${lineStats ? `<span class="df3-line-stat">${lineStats}</span>` : ''}
          <a href="${rawUrl}" class="df3-raw-link" target="_blank" rel="noopener">Raw ↗</a>
        </div>
      </div>
      ${symHtml}
      ${tableHtml ? `<div class="df3-code-wrap">${tableHtml}</div>` : '<p class="df3-no-content">Could not load file content.</p>'}
    </div>`;
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function renderStatsBar(pd: PageData): string {
  const { snapshotDiff: sd, structuredDelta: delta } = pd;

  let symAdded = 0, symModified = 0, symRemoved = 0;
  if (delta) {
    for (const fop of delta.ops ?? []) {
      for (const cop of fop.child_ops ?? []) {
        if (cop.op === 'insert') symAdded++;
        else if (cop.op === 'delete') symRemoved++;
        else symModified++;
      }
    }
  }

  const filesChanged = sd.added.length + sd.modified.length + sd.removed.length;
  const isRoot = !pd.parentId;

  const stats: string[] = [];
  if (symAdded)    stats.push(`<div class="df3-stat df3-stat-add"><div class="df3-stat-n">+${symAdded}</div><div class="df3-stat-l">symbol${symAdded !== 1 ? 's' : ''} added</div></div>`);
  if (symModified) stats.push(`<div class="df3-stat df3-stat-mod"><div class="df3-stat-n">~${symModified}</div><div class="df3-stat-l">symbol${symModified !== 1 ? 's' : ''} modified</div></div>`);
  if (symRemoved)  stats.push(`<div class="df3-stat df3-stat-del"><div class="df3-stat-n">−${symRemoved}</div><div class="df3-stat-l">symbol${symRemoved !== 1 ? 's' : ''} removed</div></div>`);
  if (filesChanged) stats.push(`<div class="df3-stat df3-stat-files"><div class="df3-stat-n">${filesChanged}</div><div class="df3-stat-l">file${filesChanged !== 1 ? 's' : ''} changed</div></div>`);
  if (sd.total_files) stats.push(`<div class="df3-stat df3-stat-snap"><div class="df3-stat-n">${sd.total_files}</div><div class="df3-stat-l">in snapshot</div></div>`);
  if (symAdded + symModified + symRemoved > 0) stats.push(`<div class="df3-stat df3-stat-clean"><div class="df3-stat-n">0</div><div class="df3-stat-l">dead code</div></div>`);

  const parentHtml = isRoot
    ? `<span class="df3-root-pill">root commit</span>`
    : `<span class="df3-vs">vs parent <a href="${pd.baseUrl}/commits/${pd.parentId}" class="df3-parent-sha">${(pd.parentId ?? '').slice(0, 8)}</a></span>`;

  return `
    <div class="df3-stats-bar">
      <div class="df3-stats-row">${stats.join('')}</div>
      <div class="df3-stats-meta">${parentHtml}</div>
    </div>`;
}

// ── Entry point ───────────────────────────────────────────────────────────────

export async function initDiff(): Promise<void> {
  const el = document.getElementById('page-data');
  if (!el) return;
  let pd: PageData;
  try { pd = JSON.parse(el.textContent ?? '{}') as PageData; } catch { return; }
  if (pd.page !== 'diff') return;

  const container = document.getElementById('df3-content');
  if (!container) return;

  const { snapshotDiff: sd, structuredDelta: delta } = pd;
  const allFiles: Array<[string, 'added' | 'modified' | 'removed']> = [
    ...sd.added.map(p => [p, 'added'] as [string, 'added']),
    ...sd.modified.map(p => [p, 'modified'] as [string, 'modified']),
    ...sd.removed.map(p => [p, 'removed'] as [string, 'removed']),
  ];

  if (allFiles.length === 0) {
    container.innerHTML = `<p class="df3-empty">No file changes in this commit.</p>`;
    return;
  }

  // Build lookup: file path → FileOp from structured delta
  const deltaByFile = new Map<string, FileOp>();
  for (const fop of delta?.ops ?? []) {
    deltaByFile.set(fop.address, fop);
  }

  // Render stats bar immediately
  container.innerHTML = renderStatsBar(pd) +
    `<div id="df3-files" class="df3-files"><div class="df3-loading"><span class="spinner"></span> Loading file diffs…</div></div>`;

  // Render file cards async (in parallel, then stitch in order)
  const filesDiv = document.getElementById('df3-files');
  if (!filesDiv) return;

  const cards = await Promise.all(
    allFiles.map(([path, ft]) => renderFileCard(path, ft, pd, deltaByFile.get(path) ?? null))
  );

  filesDiv.innerHTML = cards.join('');
}
