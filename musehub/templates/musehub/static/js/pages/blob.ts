/**
 * blob.ts — File blob viewer page module.
 *
 * Config is read from window.__blobCfg (set by the page_data block).
 * Registered as: window.MusePages['blob']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface BlobCfg {
  repoId: string;
  ref: string;
  filePath: string;
  filename: string;
  owner: string;
  repoSlug: string;
  base: string;
  ssrBlobRendered: boolean;
}

interface BlobData {
  rawUrl?: string;
  fileType?: string;
  filename?: string;
  sizeBytes?: number;
  sha?: string;
  createdAt?: string;
  contentText?: string;
}

declare global {
  interface Window { __blobCfg?: BlobCfg; }
}

// Globals injected from musehub.ts bundle
declare const escHtml: (s: unknown) => string;
declare const getToken: () => string;

// ── Utility ───────────────────────────────────────────────────────────────────

function fmtSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '';
  if (bytes < 1024) return bytes + '\u00a0B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + '\u00a0KB';
  return (bytes / 1048576).toFixed(1) + '\u00a0MB';
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch (_) { return iso; }
}

function shortSha(sha: string): string {
  const idx = sha.indexOf(':');
  const hex = idx >= 0 ? sha.slice(idx + 1) : sha;
  return hex.slice(0, 12);
}

// ── JSON syntax highlight (safe — operates on text, never eval) ───────────────

function highlightJson(text: string): string {
  const escaped = escHtml(text);
  return escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^"\\])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match: string) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) return '<span class="json-key">' + match + '</span>';
        return '<span class="json-str">' + match + '</span>';
      }
      if (/true|false/.test(match)) return '<span class="json-bool">' + match + '</span>';
      if (/null/.test(match))       return '<span class="json-null">' + match + '</span>';
      return '<span class="json-num">' + match + '</span>';
    },
  );
}

// ── Hex dump (first 512 bytes of a binary blob) ───────────────────────────────

function renderHexDump(arrayBuffer: ArrayBuffer): string {
  const bytes = new Uint8Array(arrayBuffer);
  const limit = Math.min(bytes.length, 512);
  let out = '';
  for (let i = 0; i < limit; i += 16) {
    const chunk = bytes.slice(i, i + 16);
    const offset = i.toString(16).padStart(8, '0');
    const hexPart = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ').padEnd(47, ' ');
    const asciiPart = Array.from(chunk).map(b => (b >= 32 && b < 127) ? String.fromCharCode(b) : '.').join('');
    out += '<span class="hex-offset">' + offset + '</span>'
         + '<span class="hex-bytes">' + escHtml(hexPart) + '</span>'
         + '<span class="hex-ascii">' + escHtml(asciiPart) + '</span>\n';
  }
  return out;
}

// ── Build action buttons ──────────────────────────────────────────────────────

function buildActions(cfg: BlobCfg, data: BlobData, rawUrl: string): string {
  const rollUrl   = cfg.base + '/piano-roll/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
  const listenUrl = cfg.base + '/listen/'     + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
  let actions = '<a class="btn-blob btn-blob-secondary" href="' + escHtml(rawUrl) + '" download>'
    + '&#11015;&#65039;&nbsp;Raw</a>';
  if (data.fileType === 'midi') {
    actions += '&nbsp;<a class="btn-blob btn-blob-primary" href="' + escHtml(rollUrl) + '">'
      + '&#127929;&nbsp;View in Piano Roll</a>';
  } else if (data.fileType === 'audio') {
    actions += '&nbsp;<a class="btn-blob btn-blob-primary" href="' + escHtml(listenUrl) + '">'
      + '&#127925;&nbsp;Listen</a>';
  }
  return actions;
}

// ── Render body by file type ──────────────────────────────────────────────────

function renderBlobBody(cfg: BlobCfg, data: BlobData, rawUrl: string): string | null {
  const rollUrl = cfg.base + '/piano-roll/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
  switch (data.fileType) {
    case 'midi':
      return '<div class="blob-midi-banner">'
        + '<span class="blob-midi-icon">&#127929;</span>'
        + '<div class="blob-midi-title">' + escHtml(data.filename ?? cfg.filename) + '</div>'
        + '<div class="blob-midi-sub">MIDI file \u2014 interactive piano roll coming in Phase 2</div>'
        + '<a class="btn-blob btn-blob-primary" href="' + escHtml(rollUrl) + '">&#127929;&nbsp;View in Piano Roll</a>'
        + '</div>';
    case 'audio':
      return '<div class="blob-audio-wrap">'
        + '<span class="blob-audio-icon">&#127925;</span>'
        + '<div class="blob-audio-name">' + escHtml(data.filename ?? cfg.filename) + '</div>'
        + '<audio class="blob-audio-player" controls preload="metadata" src="' + escHtml(rawUrl) + '">'
        + 'Your browser does not support audio playback. <a href="' + escHtml(rawUrl) + '">Download</a> instead.'
        + '</audio></div>';
    case 'json':
      if (data.contentText) {
        let pretty = data.contentText;
        try { pretty = JSON.stringify(JSON.parse(data.contentText), null, 2); } catch (_) { /* keep original */ }
        return '<div class="blob-code-wrap"><pre class="blob-code"><code>' + highlightJson(pretty) + '</code></pre></div>';
      }
      return '<div class="blob-binary-notice">File too large to display inline. '
        + '<a href="' + escHtml(rawUrl) + '">Download raw</a></div>';
    case 'xml':
      if (data.contentText) {
        return '<div class="blob-code-wrap"><pre class="blob-code"><code>' + escHtml(data.contentText) + '</code></pre></div>';
      }
      return '<div class="blob-binary-notice">File too large to display inline. '
        + '<a href="' + escHtml(rawUrl) + '">Download raw</a></div>';
    case 'image':
      return '<div class="blob-img-wrap">'
        + '<img class="blob-img" src="' + escHtml(rawUrl) + '" alt="' + escHtml(data.filename ?? cfg.filename) + '">'
        + '</div>';
    default:
      return null; // async hex-dump path
  }
}

// ── Hex preview for binary/unknown files (Range request for first 512 B) ──────

async function fetchHexPreview(rawUrl: string, bodyEl: HTMLElement, sizeBytes: number): Promise<void> {
  try {
    const resp = await fetch(rawUrl, { headers: { Range: 'bytes=0-511' } });
    if (resp.ok || resp.status === 206) {
      const buf = await resp.arrayBuffer();
      const hex = renderHexDump(buf);
      bodyEl.innerHTML =
        '<div class="blob-hex-wrap"><pre class="blob-hex">' + hex + '</pre></div>'
        + '<div class="blob-binary-notice">Showing first ' + Math.min(512, sizeBytes)
        + ' bytes of ' + fmtSize(sizeBytes) + '. '
        + '<a href="' + escHtml(rawUrl) + '" download>Download full file</a></div>';
    } else {
      bodyEl.innerHTML = '<div class="blob-binary-notice">Binary file \u2014 <a href="' + escHtml(rawUrl) + '" download>Download</a></div>';
    }
  } catch (_) {
    bodyEl.innerHTML = '<div class="blob-binary-notice">Binary file \u2014 <a href="' + escHtml(rawUrl) + '" download>Download</a></div>';
  }
}

// ── Render full page structure into #content ──────────────────────────────────

async function renderBlob(cfg: BlobCfg, data: BlobData): Promise<void> {
  const rawUrl = data.rawUrl ?? (cfg.base + '/raw/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath);

  const metaHtml =
    '<span title="Size">&#128196;&nbsp;' + fmtSize(data.sizeBytes) + '</span>'
    + '<span title="SHA">&#128273;&nbsp;' + escHtml(shortSha(data.sha ?? '')) + '</span>'
    + '<span title="Last pushed">&#128197;&nbsp;' + escHtml(fmtDate(data.createdAt)) + '</span>';

  const headerHtml =
    '<div class="blob-header">'
    + '<div class="blob-filename">&#128196;&nbsp;' + escHtml(data.filename ?? cfg.filename) + '</div>'
    + '<div class="blob-meta">' + metaHtml + '</div>'
    + '<div class="blob-actions">' + buildActions(cfg, data, rawUrl) + '</div>'
    + '</div>';

  const syncBody = renderBlobBody(cfg, data, rawUrl);
  const bodyPlaceholder = '<div class="blob-body" id="blob-body-inner">'
    + (syncBody !== null ? syncBody : '<div class="blob-loading">Rendering\u2026</div>')
    + '</div>';

  const contentEl = document.getElementById('content');
  if (contentEl) contentEl.innerHTML = headerHtml + bodyPlaceholder;

  if (syncBody === null) {
    const bodyEl = document.getElementById('blob-body-inner');
    if (bodyEl) await fetchHexPreview(rawUrl, bodyEl, data.sizeBytes ?? 0);
  }
}

// ── Load blob metadata from JSON API ─────────────────────────────────────────

async function loadBlob(cfg: BlobCfg): Promise<void> {
  // Skip the API fetch if the server already rendered the blob (SSR guard).
  if (cfg.ssrBlobRendered && document.getElementById('blob-ssr-content')) {
    return;
  }
  const contentEl = document.getElementById('content');
  if (!contentEl) return;
  contentEl.innerHTML = '<div class="blob-loading">Loading\u2026</div>';
  try {
    const tok = getToken();
    const headers: Record<string, string> = tok ? { Authorization: 'Bearer ' + tok } : {};
    const apiBase = '/api/v1/repos/' + cfg.repoId;
    const url = apiBase + '/blob/' + encodeURIComponent(cfg.ref) + '/' + cfg.filePath;
    const resp = await fetch(url, { headers });
    if (resp.status === 404) {
      contentEl.innerHTML = '<div class="blob-error">&#10060; File not found: <code>' + escHtml(cfg.filePath) + '</code></div>';
      return;
    }
    if (resp.status === 401) {
      contentEl.innerHTML = '<div class="blob-error">&#128274; Private repo \u2014 sign in to view this file.</div>';
      return;
    }
    if (!resp.ok) {
      contentEl.innerHTML = '<div class="blob-error">&#10060; Failed to load file (HTTP ' + resp.status + ').</div>';
      return;
    }
    const data = await resp.json() as BlobData;
    await renderBlob(cfg, data);
  } catch (err) {
    const contentEl2 = document.getElementById('content');
    if (contentEl2) contentEl2.innerHTML = '<div class="blob-error">&#10060; ' + escHtml(String(err)) + '</div>';
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initBlob(): void {
  const cfg = window.__blobCfg;
  if (!cfg) return;
  void loadBlob(cfg);
}
