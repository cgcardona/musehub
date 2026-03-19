/**
 * context.ts — Musical context viewer page module.
 *
 * Responsibilities:
 *  1. Fetch /repos/{repoId}/context/{ref} and render all context cards.
 *  2. Collapsible section toggles (Musical State, Missing Elements, etc.).
 *  3. Suggestions with "Implement" buttons that open the compose modal.
 *  4. Compose modal — streaming SSE via POST /api/v1/muse/stream.
 *  5. Raw JSON copy-to-clipboard.
 *
 * Registered as: window.MusePages['context']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface ContextPageData {
  repo_id: string;
  ref:     string;
  base:    string;
}

declare global {
  interface Window {
    escHtml:      (s: unknown) => string;
    apiFetch:     (path: string, init?: RequestInit) => Promise<unknown>;
    authHeaders:  () => Record<string, string>;
    fmtDate:      (iso: string | null | undefined) => string;
    shortSha:     (sha: string | null | undefined) => string;
    initRepoNav?: (repoId: string) => void;
  }
}

// ── Role → colour mapping ─────────────────────────────────────────────────────

interface RoleColors { bg: string; border: string; text: string; }

const ROLE_COLORS: Record<string, RoleColors> = {
  bass:       { bg: '#0d2848', border: '#1f6feb', text: '#79c0ff' },
  keys:       { bg: '#1e1040', border: '#8957e5', text: '#d2a8ff' },
  piano:      { bg: '#1e1040', border: '#8957e5', text: '#d2a8ff' },
  keyboard:   { bg: '#1e1040', border: '#8957e5', text: '#d2a8ff' },
  synth:      { bg: '#1e1040', border: '#8957e5', text: '#d2a8ff' },
  drums:      { bg: '#3d0a0a', border: '#f85149', text: '#ff7b72' },
  percussion: { bg: '#3d0a0a', border: '#f85149', text: '#ff7b72' },
  guitar:     { bg: '#1a2a00', border: '#56d364', text: '#56d364' },
  strings:    { bg: '#2a1800', border: '#e3b341', text: '#e3b341' },
  brass:      { bg: '#2a1800', border: '#e3b341', text: '#e3b341' },
  winds:      { bg: '#002a2a', border: '#39d353', text: '#39d353' },
  woodwinds:  { bg: '#002a2a', border: '#39d353', text: '#39d353' },
  vocals:     { bg: '#2a002a', border: '#f778ba', text: '#f778ba' },
  voice:      { bg: '#2a002a', border: '#f778ba', text: '#f778ba' },
};

function roleColor(trackName: string): RoleColors {
  const lower = (trackName || '').toLowerCase();
  for (const [role, colors] of Object.entries(ROLE_COLORS)) {
    if (lower.includes(role)) return colors;
  }
  return { bg: '#161b22', border: '#30363d', text: '#8b949e' };
}

function trackPill(name: string): string {
  const c = roleColor(name);
  return `<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500;`
    + `background:${c.bg};border:1px solid ${c.border};color:${c.text};margin:2px 3px 2px 0">`
    + window.escHtml(name) + `</span>`;
}

function statBadge(icon: string, label: string, value: unknown): string {
  if (value === null || value === undefined) return '';
  return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;`
    + `padding:10px 18px;background:#161b22;border:1px solid #30363d;border-radius:8px;min-width:90px">`
    + `<span style="font-size:18px;margin-bottom:4px">${icon}</span>`
    + `<span style="font-size:18px;font-weight:700;color:#e6edf3;line-height:1.1">${window.escHtml(String(value))}</span>`
    + `<span style="font-size:11px;color:#8b949e;margin-top:2px">${label}</span>`
    + `</div>`;
}

// ── Section toggles ───────────────────────────────────────────────────────────

function toggleSection(id: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? '' : 'none';
  const btn = document.querySelector<HTMLElement>(`[data-action="toggle-section"][data-target="${id}"]`);
  if (btn) btn.textContent = el.style.display === 'none' ? '▶ Show' : '▼ Hide';
}

// ── Copy JSON ─────────────────────────────────────────────────────────────────

function copyJson(): void {
  const text = document.getElementById('raw-json')?.textContent ?? '';
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copy-btn');
    if (!btn) return;
    btn.textContent = 'Copied!';
    setTimeout(() => { if (btn) btn.textContent = 'Copy JSON'; }, 2000);
  });
}

// ── Suggestion texts (index-based to avoid attribute injection) ───────────────

const _suggestionTexts: string[] = [];

// ── Compose modal ─────────────────────────────────────────────────────────────

let _composePreset = '';
let _cfg: ContextPageData;

function openCompose(presetText: string): void {
  _composePreset = presetText || '';
  const modal = document.getElementById('compose-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  const textarea = document.getElementById('compose-prompt') as HTMLTextAreaElement | null;
  if (textarea) textarea.value = _composePreset;
  const output = document.getElementById('compose-output');
  const stream = document.getElementById('compose-stream');
  if (output) output.style.display = 'none';
  if (stream) stream.textContent = '';
}

function closeCompose(): void {
  const modal = document.getElementById('compose-modal');
  if (modal) modal.style.display = 'none';
}

async function sendCompose(): Promise<void> {
  const textarea = document.getElementById('compose-prompt') as HTMLTextAreaElement | null;
  const prompt   = textarea?.value.trim() ?? '';
  if (!prompt) return;

  const btn    = document.getElementById('compose-send-btn') as HTMLButtonElement | null;
  const output = document.getElementById('compose-output');
  const stream = document.getElementById('compose-stream');
  if (!btn || !output || !stream) return;

  btn.disabled    = true;
  btn.textContent = '⏳ Generating…';
  output.style.display = '';
  stream.textContent   = '';

  try {
    const res = await fetch('/api/v1/muse/stream', {
      method:  'POST',
      headers: { ...window.authHeaders(), 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: prompt, mode: 'compose', repo_id: _cfg.repo_id, commit_id: _cfg.ref }),
    });
    if (!res.ok) {
      stream.textContent = '❌ Error: ' + res.status + ' ' + res.statusText;
      return;
    }
    const reader = res.body!.getReader();
    const dec    = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const line of dec.decode(value, { stream: true }).split('\n')) {
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') break;
        try {
          const ev = JSON.parse(data) as Record<string, string>;
          stream.textContent += ev.delta ?? ev.text ?? ev.content ?? '';
          stream.scrollTop = stream.scrollHeight;
        } catch (_) { /* non-JSON SSE lines are ignored */ }
      }
    }
  } catch (err) {
    stream.textContent = '❌ ' + ((err as Error).message || String(err));
  } finally {
    btn.disabled    = false;
    btn.textContent = '🎵 Generate';
  }
}

// ── Main load ─────────────────────────────────────────────────────────────────

async function load(): Promise<void> {
  if (window.initRepoNav) window.initRepoNav(_cfg.repo_id);

  const contentEl = document.getElementById('content');
  if (!contentEl) return;

  try {
    const ctx = (await window.apiFetch('/repos/' + _cfg.repo_id + '/context/' + _cfg.ref)) as {
      musicalState: {
        activeTracks?:  string[];
        key?:           unknown;
        mode?:          unknown;
        tempoBpm?:      unknown;
        timeSignature?: unknown;
        form?:          unknown;
        emotion?:       unknown;
      };
      missingElements?: string[];
      suggestions?:     Record<string, string>;
      history?:         Array<{ commitId: string; message: string; author: string; timestamp: string }>;
      headCommit:       { commitId: string; message: string; author: string; timestamp: string };
      currentBranch:    string;
    };

    // ── Musical State ─────────────────────────────────────────────────────────
    const tracks = ctx.musicalState.activeTracks ?? [];
    const trackPills = tracks.length > 0
      ? tracks.map(trackPill).join('')
      : '<em style="color:#8b949e;font-size:13px">No music files found in repo yet.</em>';

    const badges = [
      statBadge('♭',  'Key',      ctx.musicalState.key),
      statBadge('♩',  'Mode',     ctx.musicalState.mode),
      statBadge('♩',  'BPM',      ctx.musicalState.tempoBpm),
      statBadge('𝄴',  'Time Sig', ctx.musicalState.timeSignature),
      statBadge('🎼', 'Form',     ctx.musicalState.form),
      statBadge('🎭', 'Emotion',  ctx.musicalState.emotion),
    ].filter(Boolean).join('');

    const badgesHtml = badges
      ? `<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">${badges}</div>`
      : `<p style="font-size:13px;color:#8b949e;margin-top:12px">Musical dimensions (key, tempo, etc.) require MIDI analysis — not yet available.</p>`;

    // ── Missing Elements ──────────────────────────────────────────────────────
    const missing = ctx.missingElements ?? [];
    const missingHtml = missing.length > 0
      ? missing.map(m =>
          `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;`
          + `border-bottom:1px solid #21262d;font-size:14px">`
          + `<span style="color:#f85149;flex-shrink:0;margin-top:1px">☐</span>`
          + `<span style="color:#e6edf3">${window.escHtml(m)}</span>`
          + `</div>`
        ).join('')
      : `<div style="display:flex;align-items:center;gap:8px;font-size:14px;color:#3fb950">`
        + `<span>✅</span><span>All musical dimensions are present.</span></div>`;

    const missingBorderColor = missing.length > 0 ? '#f85149' : '#238636';

    // ── Suggestions ───────────────────────────────────────────────────────────
    _suggestionTexts.length = 0;
    const suggestions = ctx.suggestions ?? {};
    const suggKeys    = Object.keys(suggestions);
    const suggHtml    = suggKeys.length > 0
      ? suggKeys.map(k => {
          const text = suggestions[k];
          const idx  = _suggestionTexts.push(k + ': ' + text) - 1;
          return `<div style="display:flex;align-items:flex-start;justify-content:space-between;`
            + `gap:12px;padding:12px 0;border-bottom:1px solid #21262d">`
            + `<div style="font-size:14px;color:#e6edf3;flex:1">`
            + `<strong style="color:#79c0ff">${window.escHtml(k)}</strong>: ${window.escHtml(text)}`
            + `</div>`
            + `<button class="btn btn-primary btn-sm" style="flex-shrink:0;white-space:nowrap"`
            + ` data-action="open-compose" data-suggestion-idx="${idx}">⚡ Implement</button>`
            + `</div>`;
        }).join('')
      : `<p style="font-size:14px;color:#8b949e">No suggestions available.</p>`;

    // ── History ───────────────────────────────────────────────────────────────
    const histEntries = ctx.history ?? [];
    const histRows    = histEntries.length > 0
      ? histEntries.map(h => `
          <div class="commit-row">
            <a class="commit-sha" href="${window.escHtml(_cfg.base)}/commits/${h.commitId}">${window.shortSha(h.commitId)}</a>
            <span class="commit-msg">${window.escHtml(h.message)}</span>
            <span class="commit-meta">${window.escHtml(h.author)} &bull; ${window.fmtDate(h.timestamp)}</span>
          </div>`).join('')
      : '<p class="loading">No ancestor commits.</p>';

    // ── Raw JSON ──────────────────────────────────────────────────────────────
    const rawJson = JSON.stringify(ctx, null, 2);

    contentEl.innerHTML = `
      <div style="margin-bottom:12px">
        <a href="${window.escHtml(_cfg.base)}">&larr; Back to repo</a>
      </div>

      <!-- ── Header ── -->
      <div class="card" style="border-color:#1f6feb">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <span style="font-size:20px">🎵</span>
          <h1 style="margin:0;font-size:18px">What the Agent Sees</h1>
        </div>
        <p style="font-size:14px;color:#8b949e;margin-bottom:0">
          Musical context the AI agent receives when generating music at commit
          <code style="font-size:12px;background:#0d1117;padding:2px 6px;border-radius:4px">${window.shortSha(_cfg.ref)}</code>.
        </p>
      </div>

      <!-- ── Musical State ── -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">🎵 Musical State</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="musical-state-body">▼ Hide</button>
        </div>
        <div id="musical-state-body">
          <div style="margin-bottom:8px">
            <span class="meta-label" style="font-size:11px;text-transform:uppercase;letter-spacing:.05em">Active Tracks</span>
            <div style="margin-top:6px">${trackPills}</div>
          </div>
          ${badgesHtml}
        </div>
      </div>

      <!-- ── Missing Elements ── -->
      <div class="card" style="border-color:${missingBorderColor}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">⚠️ Missing Elements</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="missing-body">▼ Hide</button>
        </div>
        <div id="missing-body">${missingHtml}</div>
      </div>

      <!-- ── Suggestions ── -->
      <div class="card" style="border-color:#238636">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">✨ Suggestions</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="suggestions-body">▼ Hide</button>
        </div>
        <div id="suggestions-body">${suggHtml}</div>
      </div>

      <!-- ── History Summary ── -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">🕐 History Summary</h2>
          <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="history-body">▼ Hide</button>
        </div>
        <div id="history-body">
          <div class="meta-row" style="margin-bottom:12px">
            <div class="meta-item">
              <span class="meta-label">Commit</span>
              <span class="meta-value" style="font-family:monospace">${window.shortSha(ctx.headCommit.commitId)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Branch</span>
              <span class="meta-value">${window.escHtml(ctx.currentBranch)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Author</span>
              <span class="meta-value">${window.escHtml(ctx.headCommit.author)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Date</span>
              <span class="meta-value">${window.fmtDate(ctx.headCommit.timestamp)}</span>
            </div>
          </div>
          <pre style="margin-bottom:12px">${window.escHtml(ctx.headCommit.message)}</pre>
          <h2 style="font-size:14px;margin-bottom:8px">Ancestors (${histEntries.length})</h2>
          ${histRows}
        </div>
      </div>

      <!-- ── Raw JSON ── -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="margin:0">📄 Raw JSON</h2>
          <div style="display:flex;gap:8px">
            <button id="copy-btn" class="btn btn-secondary btn-sm" data-action="copy-json">Copy JSON</button>
            <button class="btn btn-secondary btn-sm" data-action="toggle-section" data-target="raw-json-body">▼ Hide</button>
          </div>
        </div>
        <div id="raw-json-body">
          <pre id="raw-json">${window.escHtml(rawJson)}</pre>
        </div>
      </div>`;

  } catch (e) {
    if ((e as Error).message !== 'auth' && contentEl) {
      contentEl.innerHTML = '<p class="error">✗ ' + window.escHtml((e as Error).message) + '</p>';
    }
  }
}

// ── Event delegation ──────────────────────────────────────────────────────────

function bindActions(): void {
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!el) return;
    const action = el.dataset.action;

    if (action === 'toggle-section') {
      const target = el.dataset.target;
      if (target) toggleSection(target);
    } else if (action === 'copy-json') {
      copyJson();
    } else if (action === 'open-compose') {
      const idx = parseInt(el.dataset.suggestionIdx ?? '', 10);
      openCompose(_suggestionTexts[idx] ?? '');
    } else if (action === 'close-compose') {
      closeCompose();
    } else if (action === 'close-compose-backdrop') {
      if (e.target === el) closeCompose();
    } else if (action === 'send-compose') {
      void sendCompose();
    }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initContext(data: Record<string, unknown>): void {
  _cfg = {
    repo_id: String(data.repo_id ?? ''),
    ref:     String(data.ref     ?? ''),
    base:    String(data.base    ?? ''),
  };
  bindActions();
  void load();
}
