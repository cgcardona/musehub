/**
 * compare.ts — Branch comparison page module.
 *
 * Responsibilities:
 *  1. Fetch musical diff between two refs and render the compare view.
 *  2. Render radar SVG, piano roll, emotion diff bars, dimension panels.
 *  3. Handle audio A/B toggle and expandable dimension panels.
 *
 * Config is read from window.__compareCfg (set by the page_data block).
 * Registered as: window.MusePages['compare']
 */

// ── Config ────────────────────────────────────────────────────────────────────

interface CompareCfg {
  repoId:  string;
  baseRef: string;
  headRef: string;
  uiBase:  string;
}

declare global {
  interface Window {
    __compareCfg?: CompareCfg;
    escHtml:       (s: unknown) => string;
    apiFetch:      (path: string, init?: RequestInit) => Promise<unknown>;
    initRepoNav?:  (repoId: string) => void;
  }
}

// ── Design constants ──────────────────────────────────────────────────────────

const DIMENSIONS  = ['melodic', 'harmonic', 'rhythmic', 'structural', 'dynamic'];
const LEVEL_COLOR: Record<string, string> = {
  NONE: '#1f6feb', LOW: '#388bfd', MED: '#f0883e', HIGH: '#f85149',
};
const LEVEL_BG: Record<string, string> = {
  NONE: '#0d2942', LOW: '#102a4c', MED: '#341a00', HIGH: '#3d0000',
};
const AXIS_LABELS: Record<string, string> = {
  melodic: 'Melodic', harmonic: 'Harmonic', rhythmic: 'Rhythmic',
  structural: 'Structural', dynamic: 'Dynamic',
};
const EMOTION_COLOR: Record<string, string> = {
  energy: '#f0883e', valence: '#3fb950', tension: '#f85149', darkness: '#bc8cff',
};

// ── State ─────────────────────────────────────────────────────────────────────

const _expanded: Record<string, boolean> = {};
let   _lastDims: DimData[] = [];
let   _audioSide = 'base';
let   _cfg: CompareCfg;

// ── Types ─────────────────────────────────────────────────────────────────────

interface DimData {
  dimension:      string;
  level:          string;
  score:          number;
  description?:   string;
  branchACommits?: number;
  branchBCommits?: number;
}

interface CommitData {
  commitId?:  string;
  message?:   string;
  author?:    string;
  timestamp?: string;
}

interface EmotionDiff {
  energyDelta?:   number; baseEnergy?:   number; headEnergy?:   number;
  valenceDelta?:  number; baseValence?:  number; headValence?:  number;
  tensionDelta?:  number; baseTension?:  number; headTension?:  number;
  darknessDelta?: number; baseDarkness?: number; headDarkness?: number;
}

interface CompareData {
  overallScore?:  number;
  commonAncestor?: string;
  dimensions?:   DimData[];
  commits?:      CommitData[];
  emotionDiff?:  EmotionDiff;
  createPrUrl?:  string;
}

// ── Radar SVG ─────────────────────────────────────────────────────────────────

function radarSvg(dims: DimData[]): string {
  const cx = 180, cy = 180, r = 140;
  const n = dims.length;
  const pts = dims.map((d, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const sr = d.score * r;
    return { x: cx + sr * Math.cos(angle), y: cy + sr * Math.sin(angle) };
  });
  const bgPts = DIMENSIONS.map((_, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
  }).join(' ');
  const scorePoly = pts.map(p => `${p.x},${p.y}`).join(' ');
  const axisLines = DIMENSIONS.map((_, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const ex = cx + r * Math.cos(angle), ey = cy + r * Math.sin(angle);
    return `<line x1="${cx}" y1="${cy}" x2="${ex}" y2="${ey}" stroke="#30363d" stroke-width="1"/>`;
  }).join('');
  const gridLines = [0.25, 0.5, 0.75, 1.0].map(frac => {
    const gPts = DIMENSIONS.map((_, i) => {
      const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
      return `${cx + frac * r * Math.cos(angle)},${cy + frac * r * Math.sin(angle)}`;
    }).join(' ');
    return `<polygon points="${gPts}" fill="none" stroke="#21262d" stroke-width="1"/>`;
  }).join('');
  const labels = dims.map((d, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const lx = cx + (r + 22) * Math.cos(angle);
    const ly = cy + (r + 22) * Math.sin(angle);
    const color = LEVEL_COLOR[d.level] ?? '#8b949e';
    return `<text x="${lx}" y="${ly + 4}" text-anchor="middle"
      font-size="12" fill="${color}" font-family="system-ui">${AXIS_LABELS[d.dimension] ?? d.dimension}</text>`;
  }).join('');
  const dots = pts.map((p, i) => {
    const color = LEVEL_COLOR[dims[i].level] ?? '#58a6ff';
    return `<circle cx="${p.x}" cy="${p.y}" r="4" fill="${color}" stroke="#0d1117" stroke-width="2"/>`;
  }).join('');
  return `<svg viewBox="0 0 360 360" xmlns="http://www.w3.org/2000/svg"
      style="width:100%;max-width:360px;display:block;margin:0 auto">
    ${gridLines}${axisLines}
    <polygon points="${bgPts}" fill="rgba(88,166,255,0.04)" stroke="#30363d" stroke-width="1"/>
    <polygon points="${scorePoly}" fill="rgba(248,81,73,0.18)" stroke="#f85149" stroke-width="2"/>
    ${labels}${dots}
  </svg>`;
}

// ── Level badge ───────────────────────────────────────────────────────────────

function levelBadge(level: string): string {
  const color = LEVEL_COLOR[level] ?? '#8b949e';
  return `<span style="display:inline-block;padding:1px 7px;border-radius:10px;
    font-size:11px;font-weight:700;color:#fff;background:${color}">${level}</span>`;
}

// ── Dimension panel ───────────────────────────────────────────────────────────

function dimensionPanel(d: DimData, expanded: boolean): string {
  const bg  = LEVEL_BG[d.level] ?? '#161b22';
  const id  = 'dim-' + d.dimension;
  const pct = Math.round(d.score * 100);
  const detail = expanded ? `
    <div style="margin-top:10px;font-size:13px;color:#8b949e">
      <div>${window.escHtml(d.description ?? '')}</div>
      <div style="margin-top:6px;display:flex;gap:16px">
        <span>Base commits: <b style="color:#e6edf3">${d.branchACommits ?? 0}</b></span>
        <span>Head commits: <b style="color:#e6edf3">${d.branchBCommits ?? 0}</b></span>
      </div>
    </div>` : '';
  return `<div id="${id}" class="card" style="background:${bg};cursor:pointer;margin-bottom:8px"
      data-action="toggle-dim" data-dim="${window.escHtml(d.dimension)}">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:14px;color:#e6edf3;font-weight:600;min-width:90px">
        ${AXIS_LABELS[d.dimension] ?? d.dimension}</span>
      ${levelBadge(d.level)}
      <div style="flex:1;height:6px;background:#21262d;border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${LEVEL_COLOR[d.level] ?? '#58a6ff'};
          border-radius:3px;transition:width .3s"></div>
      </div>
      <span style="font-size:13px;color:#8b949e;white-space:nowrap">${pct}% diverged</span>
    </div>
    ${detail}
  </div>`;
}

function renderDims(dims: DimData[]): void {
  _lastDims = dims;
  const el = document.getElementById('dim-panels');
  if (el) el.innerHTML = dims.map(d => dimensionPanel(d, !!_expanded[d.dimension])).join('');
}

// ── Emotion diff bar ──────────────────────────────────────────────────────────

function emotionDiffBar(axis: string, delta: number, baseVal: number, headVal: number): string {
  const color    = EMOTION_COLOR[axis] ?? '#58a6ff';
  const sign     = delta >= 0 ? '+' : '';
  const pctBase  = Math.round(baseVal * 100);
  const pctHead  = Math.round(headVal * 100);
  const pctDelta = Math.round(delta * 100);
  return `
    <div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
        <span style="font-size:13px;color:#e6edf3;text-transform:capitalize">${axis}</span>
        <span style="font-size:12px;color:${delta >= 0 ? '#3fb950' : '#f85149'};font-weight:700">
          ${sign}${pctDelta}%
        </span>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span style="font-size:11px;color:#8b949e;min-width:32px">base</span>
        <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${pctBase}%;background:${color};opacity:0.5;border-radius:4px"></div>
        </div>
        <span style="font-size:11px;color:#8b949e;min-width:28px">${pctBase}%</span>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-top:4px">
        <span style="font-size:11px;color:#8b949e;min-width:32px">head</span>
        <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${pctHead}%;background:${color};border-radius:4px"></div>
        </div>
        <span style="font-size:11px;color:#8b949e;min-width:28px">${pctHead}%</span>
      </div>
    </div>`;
}

// ── Piano roll ────────────────────────────────────────────────────────────────

function pianoRollSvg(baseRef: string, headRef: string): string {
  const PITCHES = 24, STEPS = 32;
  const W = 480, H = 120;
  const sw = W / STEPS, sh = H / PITCHES;

  function refSeed(s: string): number {
    let h = 0;
    for (let i = 0; i < s.length; i++) { h = Math.imul(31, h) + s.charCodeAt(i) | 0; }
    return h >>> 0;
  }
  function noteGrid(seed: number): Set<number> {
    let x = seed;
    const grid = new Set<number>();
    for (let i = 0; i < STEPS * PITCHES; i++) {
      x = (x * 1103515245 + 12345) & 0x7fffffff;
      if ((x % 100) < 22) grid.add(i);
    }
    return grid;
  }

  const baseGrid = noteGrid(refSeed(baseRef));
  const headGrid = noteGrid(refSeed(headRef));

  let rects = '';
  for (let p = 0; p < PITCHES; p++) {
    for (let s = 0; s < STEPS; s++) {
      const idx    = p * STEPS + s;
      const inBase = baseGrid.has(idx);
      const inHead = headGrid.has(idx);
      if (!inBase && !inHead) continue;
      let fill: string;
      if (inBase && inHead) fill = '#30363d';
      else if (inHead)      fill = '#3fb95088';
      else                  fill = '#f8514988';
      rects += `<rect x="${s * sw + 1}" y="${(PITCHES - 1 - p) * sh + 1}"
        width="${sw - 2}" height="${sh - 1}" fill="${fill}" rx="1"/>`;
    }
  }

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"
      style="width:100%;max-width:${W}px;border-radius:6px;background:#0d1117;display:block">
    ${rects}
  </svg>
  <div style="display:flex;gap:16px;margin-top:6px;font-size:11px;color:#8b949e">
    <span><span style="display:inline-block;width:10px;height:10px;background:#3fb950;border-radius:2px;margin-right:4px"></span>Added in head</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#f85149;border-radius:2px;margin-right:4px"></span>Removed in head</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#30363d;border-radius:2px;margin-right:4px"></span>Unchanged</span>
  </div>`;
}

// ── Audio A/B toggle ──────────────────────────────────────────────────────────

function toggleAudio(side: string): void {
  _audioSide = side;
  (['btn-audio-base', 'btn-audio-head'] as const).forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.background = '#21262d'; el.style.color = '#8b949e'; }
  });
  const active = document.getElementById('btn-audio-' + side);
  if (active) { active.style.background = '#1f6feb'; active.style.color = '#fff'; }
  const label = document.getElementById('audio-label');
  if (label) label.textContent = side === 'base' ? _cfg.baseRef : _cfg.headRef;
}

// ── Commit list row ───────────────────────────────────────────────────────────

function commitRow(c: CommitData): string {
  const sha = (c.commitId ?? '').substring(0, 8);
  const ts  = c.timestamp ? new Date(c.timestamp).toLocaleString() : '';
  return `<div class="card" style="margin-bottom:8px;padding:var(--space-2) var(--space-3)">
    <div style="display:flex;align-items:center;gap:12px">
      <a href="${window.escHtml(_cfg.uiBase)}/commits/${window.escHtml(c.commitId ?? '')}" class="text-mono"
         style="font-size:13px;color:#58a6ff;text-decoration:none">${window.escHtml(sha)}</a>
      <span style="font-size:13px;color:#e6edf3;flex:1">${window.escHtml(c.message ?? '')}</span>
      <span style="font-size:12px;color:#8b949e;white-space:nowrap">${window.escHtml(c.author ?? '')}</span>
      <span style="font-size:11px;color:#8b949e;white-space:nowrap">${window.escHtml(ts)}</span>
    </div>
  </div>`;
}

// ── Main loader ───────────────────────────────────────────────────────────────

async function load(): Promise<void> {
  if (window.initRepoNav) window.initRepoNav(_cfg.repoId);

  const params = `base=${encodeURIComponent(_cfg.baseRef)}&head=${encodeURIComponent(_cfg.headRef)}`;
  const contentEl = document.getElementById('content');
  if (!contentEl) return;
  contentEl.innerHTML = '<p class="loading">Computing musical diff&#8230;</p>';

  try {
    const d = (await window.apiFetch(`/repos/${_cfg.repoId}/compare?${params}`)) as CompareData;

    const pct         = Math.round((d.overallScore ?? 0) * 100);
    const ancestor    = d.commonAncestor ? d.commonAncestor.substring(0, 8) : null;
    const dims        = d.dimensions ?? [];
    const commits     = d.commits ?? [];
    const emotion     = d.emotionDiff ?? {} as EmotionDiff;
    const createPrUrl = d.createPrUrl ??
      `${_cfg.uiBase}/pulls/new?base=${encodeURIComponent(_cfg.baseRef)}&head=${encodeURIComponent(_cfg.headRef)}`;

    contentEl.innerHTML = `
      <!-- ── Header ── -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:12px">
        <div>
          <h1 style="margin:0;font-size:20px;color:#e6edf3">
            Comparing <code style="font-size:16px">${window.escHtml(_cfg.baseRef)}</code>
            &hellip;
            <code style="font-size:16px">${window.escHtml(_cfg.headRef)}</code>
          </h1>
          ${ancestor
            ? `<div style="font-size:12px;color:#8b949e;margin-top:4px">Common ancestor: <span class="text-mono">${window.escHtml(ancestor)}</span></div>`
            : '<div style="font-size:12px;color:#f0883e;margin-top:4px">No common ancestor — diverged histories</div>'}
        </div>
        <a href="${window.escHtml(createPrUrl)}" class="btn btn-primary">&#10133; Create Pull Request</a>
      </div>

      <!-- ── Overall score + Radar ── -->
      <div style="display:grid;grid-template-columns:1fr auto;gap:24px;align-items:start;margin-bottom:24px;flex-wrap:wrap">
        <div>
          <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Musical Divergence</h2>
          <div style="text-align:center;margin-bottom:16px">
            <div style="font-size:40px;font-weight:700;color:#e6edf3">${pct}%</div>
            <div style="font-size:12px;color:#8b949e">overall musical divergence</div>
          </div>
          <div id="dim-panels"></div>
        </div>
        <div style="flex-shrink:0">
          <div style="width:280px">${radarSvg(dims)}</div>
        </div>
      </div>

      <!-- ── Piano roll ── -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Piano Roll Comparison</h2>
        <div style="font-size:12px;color:#8b949e;margin-bottom:12px">
          Deterministic note representation from commit SHA hashes — green = added, red = removed.
        </div>
        ${pianoRollSvg(_cfg.baseRef, _cfg.headRef)}
      </div>

      <!-- ── Audio A/B toggle ── -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">Audio A/B Comparison</h2>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <button id="btn-audio-base" data-action="toggle-audio" data-side="base"
            style="padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;background:#1f6feb;color:#fff">
            &#9654; Base: ${window.escHtml(_cfg.baseRef)}
          </button>
          <button id="btn-audio-head" data-action="toggle-audio" data-side="head"
            style="padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;background:#21262d;color:#8b949e">
            &#9654; Head: ${window.escHtml(_cfg.headRef)}
          </button>
        </div>
        <div style="font-size:12px;color:#8b949e">
          Listening to: <span id="audio-label" style="color:#e6edf3">${window.escHtml(_cfg.baseRef)}</span>
        </div>
        <div style="margin-top:8px;font-size:12px;color:#484f58">
          Audio render requires snapshot objects. Toggle queues the correct ref in the player.
        </div>
      </div>

      <!-- ── Emotion diff ── -->
      <div class="card" style="margin-bottom:24px">
        <h2 style="margin:0 0 16px;font-size:16px;color:#e6edf3">Emotion Diff</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          ${emotionDiffBar('energy',   emotion.energyDelta   ?? 0, emotion.baseEnergy   ?? 0.5, emotion.headEnergy   ?? 0.5)}
          ${emotionDiffBar('valence',  emotion.valenceDelta  ?? 0, emotion.baseValence  ?? 0.5, emotion.headValence  ?? 0.5)}
          ${emotionDiffBar('tension',  emotion.tensionDelta  ?? 0, emotion.baseTension  ?? 0.5, emotion.headTension  ?? 0.5)}
          ${emotionDiffBar('darkness', emotion.darknessDelta ?? 0, emotion.baseDarkness ?? 0.5, emotion.headDarkness ?? 0.5)}
        </div>
      </div>

      <!-- ── Commit list ── -->
      <div style="margin-bottom:24px">
        <h2 style="margin:0 0 12px;font-size:16px;color:#e6edf3">
          Commits in <code>${window.escHtml(_cfg.headRef)}</code> not in <code>${window.escHtml(_cfg.baseRef)}</code>
          <span style="font-size:13px;font-weight:400;color:#8b949e;margin-left:8px">
            ${commits.length} commit${commits.length !== 1 ? 's' : ''}
          </span>
        </h2>
        ${commits.length === 0
          ? '<p class="text-muted text-sm">No commits unique to head — refs are identical or head is behind base.</p>'
          : commits.map(commitRow).join('')}
      </div>

      <!-- ── Create PR CTA ── -->
      <div class="card" style="text-align:center;padding:var(--space-5)">
        <div style="font-size:15px;color:#e6edf3;margin-bottom:12px">
          Ready to merge <code>${window.escHtml(_cfg.headRef)}</code> into <code>${window.escHtml(_cfg.baseRef)}</code>?
        </div>
        <a href="${window.escHtml(createPrUrl)}" class="btn btn-primary" style="font-size:14px;padding:10px 24px">
          Open a Pull Request
        </a>
      </div>`;

    renderDims(dims);

  } catch (e) {
    if ((e as Error).message !== 'auth' && contentEl) {
      contentEl.innerHTML = '<p class="error">&#10005; ' + window.escHtml((e as Error).message) + '</p>';
    }
  }
}

// ── Event delegation ──────────────────────────────────────────────────────────

function bindActions(): void {
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!el) return;
    if (el.dataset.action === 'toggle-dim') {
      const dim = el.dataset.dim;
      if (dim) { _expanded[dim] = !_expanded[dim]; renderDims(_lastDims); }
    } else if (el.dataset.action === 'toggle-audio') {
      const side = el.dataset.side;
      if (side) toggleAudio(side);
    }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initCompare(): void {
  _cfg = window.__compareCfg ?? { repoId: '', baseRef: '', headRef: '', uiBase: '' };
  if (!_cfg.repoId) return;
  bindActions();
  void load();
}
