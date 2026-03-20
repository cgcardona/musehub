/**
 * blob.ts — File blob viewer with syntax highlighting.
 *
 * Two rendering paths:
 *  1. SSR path: server renders line-numbered table; we post-process with hljs.
 *  2. Client path: we fetch via API and render with hljs ourselves.
 *
 * highlight.js is imported à la carte (same set as diff.ts) to keep the
 * bundle lean — no auto-detection, language resolved from file extension.
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
import haskell    from 'highlight.js/lib/languages/haskell';
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

interface BlobCfg {
  repoId:          string;
  ref:             string;
  filePath:        string;
  filename:        string;
  owner:           string;
  repoSlug:        string;
  base:            string;
  ssrBlobRendered: boolean;
}

interface BlobData {
  rawUrl?:      string;
  fileType?:    string;
  filename?:    string;
  sizeBytes?:   number;
  sha?:         string;
  createdAt?:   string;
  contentText?: string;
}

declare global {
  interface Window { __blobCfg?: BlobCfg; }
}

declare const escHtml: (s: unknown) => string;
declare const getToken: () => string;

// ── Extension → language map (mirrors diff.ts exactly) ───────────────────────

function extToLang(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    py: 'python', pyw: 'python',
    ts: 'typescript', tsx: 'typescript',
    js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
    rs: 'rust',
    go: 'go',
    swift: 'swift',
    kt: 'kotlin', kts: 'kotlin',
    java: 'java',
    rb: 'ruby', rake: 'ruby',
    cpp: 'cpp', cc: 'cpp', cxx: 'cpp', c: 'cpp', h: 'cpp', hpp: 'cpp',
    hs: 'haskell',
    json: 'json', jsonc: 'json',
    yaml: 'yaml', yml: 'yaml',
    toml: 'toml',
    sh: 'bash', bash: 'bash', zsh: 'bash',
    html: 'xml', htm: 'xml', xml: 'xml', svg: 'xml',
    css: 'css', scss: 'css', sass: 'css',
    sql: 'sql',
    md: 'markdown', mdx: 'markdown',
    txt: 'plaintext',
  };
  return map[ext] ?? 'plaintext';
}

// ── Core highlighter ──────────────────────────────────────────────────────────

/**
 * Highlight `code` with hljs and return an array of HTML strings, one per
 * line. We highlight the whole file at once so multi-line tokens (strings,
 * comments, template literals) are coloured correctly, then split on newlines.
 */
function highlightLines(code: string, lang: string): string[] {
  let highlighted: string;
  try {
    highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    highlighted = escHtml(code);
  }
  const lines = highlighted.split('\n');
  // hljs adds a trailing \n which produces a spurious empty last element
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines;
}

// ── SSR post-process — apply hljs to the server-rendered table ────────────────

/**
 * The SSR blob template renders each line as a plain `<td class="blob-code">`.
 * We re-collect all plain-text lines, highlight the full source, then inject
 * the coloured HTML back cell by cell.  This preserves the SSR line-number
 * anchors (`id="L1"` etc.) while adding colour.
 */
function applySsrHighlighting(filename: string): void {
  // Support both old class names (blob-*) and new blob2-* names
  const cells = Array.from(
    document.querySelectorAll<HTMLTableCellElement>(
      '.blob2-line-table td.blob2-code, .blob-line-table td.blob-code',
    ),
  );
  if (cells.length === 0) return;

  const lang = extToLang(filename);
  if (lang === 'plaintext') return; // nothing useful to highlight

  // Re-collect raw text: textContent strips any existing spans safely
  const rawLines = cells.map(td => td.textContent ?? '');
  const fullSrc  = rawLines.join('\n');

  const coloredLines = highlightLines(fullSrc, lang);

  cells.forEach((td, i) => {
    // Use innerHTML — the hljs output is safe HTML with <span> tokens only
    td.innerHTML = coloredLines[i] ?? td.innerHTML;
    td.classList.add('hljs');
  });

  // Mark the table so CSS can apply the hljs theme background
  (document.querySelector('.blob2-line-table') ?? document.querySelector('.blob-line-table'))
    ?.classList.add('hljs');
}

// ── Utility helpers ───────────────────────────────────────────────────────────

function fmtSize(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  if (bytes < 1024)    return bytes + '\u00a0B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + '\u00a0KB';
  return (bytes / 1048576).toFixed(1) + '\u00a0MB';
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch { return iso; }
}

function shortSha(sha: string): string {
  const idx = sha.indexOf(':');
  const hex = idx >= 0 ? sha.slice(idx + 1) : sha;
  return hex.slice(0, 12);
}

// ── Hex dump ──────────────────────────────────────────────────────────────────

function renderHexDump(arrayBuffer: ArrayBuffer): string {
  const bytes = new Uint8Array(arrayBuffer);
  const limit = Math.min(bytes.length, 512);
  let out = '';
  for (let i = 0; i < limit; i += 16) {
    const chunk    = bytes.slice(i, i + 16);
    const offset   = i.toString(16).padStart(8, '0');
    const hexPart  = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ').padEnd(47, ' ');
    const asciiPart = Array.from(chunk).map(b => (b >= 32 && b < 127) ? String.fromCharCode(b) : '.').join('');
    out += '<span class="hex-offset">' + offset + '</span>'
         + '<span class="hex-bytes">' + escHtml(hexPart) + '</span>'
         + '<span class="hex-ascii">' + escHtml(asciiPart) + '</span>\n';
  }
  return out;
}

// ── Action buttons ────────────────────────────────────────────────────────────

function buildActions(cfg: BlobCfg, data: BlobData, rawUrl: string): string {
  let actions = '<a class="btn-blob btn-blob-secondary" href="' + escHtml(rawUrl) + '" download>'
    + '⬇&#65039;&nbsp;Raw</a>';
  if (data.fileType === 'midi') {
    const rollUrl = cfg.base + '/piano-roll/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
    actions += '&nbsp;<a class="btn-blob btn-blob-primary" href="' + escHtml(rollUrl) + '">'
      + '🎹&nbsp;View in Piano Roll</a>';
  } else if (data.fileType === 'audio') {
    const listenUrl = cfg.base + '/listen/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
    actions += '&nbsp;<a class="btn-blob btn-blob-primary" href="' + escHtml(listenUrl) + '">'
      + '🎵&nbsp;Listen</a>';
  }
  return actions;
}

// ── Render highlighted code table (client-side path) ─────────────────────────

function buildCodeTable(code: string, lang: string): string {
  const lines = highlightLines(code, lang);
  const rows  = lines.map((html, i) =>
    `<tr id="L${i + 1}" class="blob-line">`
    + `<td class="blob-ln"><a href="#L${i + 1}">${i + 1}</a></td>`
    + `<td class="blob-code hljs">${html}</td>`
    + `</tr>`,
  ).join('');
  return `<div class="blob-viewer"><table class="blob-line-table hljs"><tbody>${rows}</tbody></table></div>`;
}

// ── Body renderer (client-side fetch path) ────────────────────────────────────

function renderBlobBody(cfg: BlobCfg, data: BlobData, rawUrl: string): string | null {
  const rollUrl = cfg.base + '/piano-roll/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;

  switch (data.fileType) {
    case 'midi':
      return '<div class="blob-midi-banner">'
        + '<span class="blob-midi-icon">🎹</span>'
        + '<div class="blob-midi-title">' + escHtml(data.filename ?? cfg.filename) + '</div>'
        + '<div class="blob-midi-sub">MIDI file</div>'
        + '<a class="btn-blob btn-blob-primary" href="' + escHtml(rollUrl) + '">🎹&nbsp;View in Piano Roll</a>'
        + '</div>';
    case 'audio':
      return '<div class="blob-audio-wrap">'
        + '<span class="blob-audio-icon">🎵</span>'
        + '<div class="blob-audio-name">' + escHtml(data.filename ?? cfg.filename) + '</div>'
        + '<audio class="blob-audio-player" controls preload="metadata" src="' + escHtml(rawUrl) + '">'
        + 'Your browser does not support audio. <a href="' + escHtml(rawUrl) + '">Download</a></audio></div>';
    case 'image':
      return '<div class="blob-img-wrap">'
        + '<img class="blob-img" src="' + escHtml(rawUrl) + '" alt="' + escHtml(data.filename ?? cfg.filename) + '">'
        + '</div>';
    default:
      if (data.contentText != null) {
        const lang  = extToLang(cfg.filename);
        return buildCodeTable(data.contentText, lang);
      }
      return null; // binary → async hex dump
  }
}

// ── Hex preview for binary/unknown files ──────────────────────────────────────

async function fetchHexPreview(rawUrl: string, bodyEl: HTMLElement, sizeBytes: number): Promise<void> {
  try {
    const resp = await fetch(rawUrl, { headers: { Range: 'bytes=0-511' } });
    if (resp.ok || resp.status === 206) {
      const buf = await resp.arrayBuffer();
      bodyEl.innerHTML =
        '<div class="blob-hex-wrap"><pre class="blob-hex">' + renderHexDump(buf) + '</pre></div>'
        + '<div class="blob-binary-notice">Showing first ' + Math.min(512, sizeBytes)
        + ' bytes of ' + fmtSize(sizeBytes) + '. '
        + '<a href="' + escHtml(rawUrl) + '" download>Download full file</a></div>';
    } else {
      bodyEl.innerHTML = '<div class="blob-binary-notice">Binary file — <a href="' + escHtml(rawUrl) + '" download>Download</a></div>';
    }
  } catch {
    bodyEl.innerHTML = '<div class="blob-binary-notice">Binary file — <a href="' + escHtml(rawUrl) + '" download>Download</a></div>';
  }
}

// ── Full client-side render ───────────────────────────────────────────────────

async function renderBlob(cfg: BlobCfg, data: BlobData): Promise<void> {
  const rawUrl = data.rawUrl ?? (cfg.base + '/raw/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath);
  const lang   = extToLang(cfg.filename);

  const metaHtml =
    (data.sizeBytes != null ? '<span title="Size">📄&nbsp;' + fmtSize(data.sizeBytes) + '</span>' : '')
    + (data.sha     ? '<span title="SHA">🔑&nbsp;'          + escHtml(shortSha(data.sha))        + '</span>' : '')
    + (data.createdAt ? '<span title="Last pushed">📅&nbsp;' + escHtml(fmtDate(data.createdAt))  + '</span>' : '')
    + (lang !== 'plaintext' ? '<span class="blob-lang-badge">' + escHtml(lang) + '</span>' : '');

  const headerHtml =
    '<div class="blob-header">'
    + '<div class="blob-filename">📄&nbsp;<code>' + escHtml(data.filename ?? cfg.filename) + '</code></div>'
    + '<div class="blob-meta">' + metaHtml + '</div>'
    + '<div class="blob-actions">' + buildActions(cfg, data, rawUrl) + '</div>'
    + '</div>';

  const syncBody = renderBlobBody(cfg, data, rawUrl);
  const bodyHtml = '<div class="blob-body" id="blob-body-inner">'
    + (syncBody !== null ? syncBody : '<div class="blob-loading">Rendering…</div>')
    + '</div>';

  const contentEl = document.getElementById('content');
  if (contentEl) contentEl.innerHTML = headerHtml + bodyHtml;

  if (syncBody === null) {
    const bodyEl = document.getElementById('blob-body-inner');
    if (bodyEl) await fetchHexPreview(rawUrl, bodyEl, data.sizeBytes ?? 0);
  }
}

// ── Load metadata from API (client path) ─────────────────────────────────────

async function loadBlob(cfg: BlobCfg): Promise<void> {
  // SSR path: server already rendered the blob — just add highlighting.
  if (cfg.ssrBlobRendered && document.getElementById('blob-ssr-content')) {
    applySsrHighlighting(cfg.filename);
    return;
  }

  // Client path: fetch metadata, then render.
  const contentEl = document.getElementById('content');
  if (!contentEl) return;
  contentEl.innerHTML = '<div class="blob-loading">Loading…</div>';

  try {
    const tok     = getToken();
    const headers: Record<string, string> = tok ? { Authorization: 'Bearer ' + tok } : {};
    const url     = '/api/v1/repos/' + cfg.repoId + '/blob/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
    const resp    = await fetch(url, { headers });

    if (resp.status === 404) {
      contentEl.innerHTML = '<div class="blob-error">❌ File not found: <code>' + escHtml(cfg.filePath) + '</code></div>';
      return;
    }
    if (resp.status === 401) {
      contentEl.innerHTML = '<div class="blob-error">🔒 Private repo — sign in to view this file.</div>';
      return;
    }
    if (!resp.ok) {
      contentEl.innerHTML = '<div class="blob-error">❌ Failed to load file (HTTP ' + resp.status + ').</div>';
      return;
    }

    const data = await resp.json() as BlobData;
    await renderBlob(cfg, data);
  } catch (err) {
    const el = document.getElementById('content');
    if (el) el.innerHTML = '<div class="blob-error">❌ ' + escHtml(String(err)) + '</div>';
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initBlob(): void {
  const cfg = window.__blobCfg;
  if (!cfg) return;
  void loadBlob(cfg);
}
