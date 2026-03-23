/**
 * divergence.ts — Divergence visualization page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "divergence", repoId, base }
 */

type PageData = Record<string, unknown>;

const DIMENSIONS = ['melodic', 'harmonic', 'rhythmic', 'structural', 'dynamic'];
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

interface DivDim {
  dimension: string;
  level: string;
  score: number;
  description: string;
  branchACommits: number;
  branchBCommits: number;
}

function levelBadge(level: string): string {
  const color = LEVEL_COLOR[level] ?? '#8b949e';
  return `<span style="display:inline-block;padding:1px 7px;border-radius:10px;
    font-size:11px;font-weight:700;color:#fff;background:${color}">${level}</span>`;
}

function radarSvg(dims: DivDim[]): string {
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

const _expanded: Record<string, boolean> = {};
let _lastDims: DivDim[] = [];
let _divRepoId = '';
let _divBase = '';
let _branchA = '';
let _branchB = '';

function renderDims(dims: DivDim[]): void {
  _lastDims = dims;
  const panelsEl = document.getElementById('dim-panels');
  if (!panelsEl) return;
  panelsEl.innerHTML = dims.map(d => dimensionPanel(d, !!_expanded[d.dimension])).join('');
}

function dimensionPanel(d: DivDim, expanded: boolean): string {
  const bg = LEVEL_BG[d.level] ?? '#161b22';
  const detail = expanded ? `
    <div style="margin-top:10px;font-size:13px;color:#8b949e">
      <div>${window.escHtml(d.description)}</div>
      <div style="margin-top:6px;display:flex;gap:16px">
        <span>Branch A: <b style="color:#e6edf3">${d.branchACommits} commit(s)</b></span>
        <span>Branch B: <b style="color:#e6edf3">${d.branchBCommits} commit(s)</b></span>
      </div>
    </div>` : '';
  const pct = Math.round(d.score * 100);
  return `<div id="dim-${d.dimension}" class="card" style="background:${bg};cursor:pointer;margin-bottom:8px"
      onclick="window._divToggleDim('${d.dimension}')">
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:14px;color:#e6edf3;font-weight:600;min-width:90px">
        ${AXIS_LABELS[d.dimension] ?? d.dimension}</span>
      ${levelBadge(d.level)}
      <div style="flex:1;height:6px;background:#21262d;border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${LEVEL_COLOR[d.level] ?? '#58a6ff'};
          border-radius:3px;transition:width .3s"></div>
      </div>
      <span style="font-size:13px;color:#8b949e;white-space:nowrap">${pct}%</span>
    </div>
    ${detail}
  </div>`;
}

async function loadDivergence(bA: string, bB: string): Promise<void> {
  const radarEl   = document.getElementById('radar-area');
  const dimPanels = document.getElementById('dim-panels');
  const overallEl = document.getElementById('overall-area');

  if (!bA || !bB) {
    if (radarEl) radarEl.innerHTML = '<p class="loading">Select two branches to compare.</p>';
    if (dimPanels) dimPanels.innerHTML = '';
    if (overallEl) overallEl.innerHTML = '';
    return;
  }
  if (radarEl) radarEl.innerHTML = '<p class="loading">Computing&#8230;</p>';
  try {
    interface DivResp {
      overallScore: number;
      commonAncestor: string | null;
      dimensions: DivDim[];
    }
    const d = (await window.apiFetch(
      '/repos/' + _divRepoId + '/divergence?branch_a=' +
      encodeURIComponent(bA) + '&branch_b=' + encodeURIComponent(bB),
    )) as DivResp;
    const pct = Math.round((d.overallScore || 0) * 100);
    if (radarEl) radarEl.innerHTML = radarSvg(d.dimensions ?? []);
    if (overallEl) {
      overallEl.innerHTML = `
        <div style="text-align:center;margin:12px 0">
          <div style="font-size:32px;font-weight:700;color:#e6edf3">${pct}%</div>
          <div style="font-size:12px;color:#8b949e;margin-top:2px">overall divergence</div>
          ${d.commonAncestor ? `<div style="font-size:11px;color:#8b949e;margin-top:4px;font-family:monospace">
            base: ${d.commonAncestor.substring(0, 8)}</div>` : ''}
        </div>`;
    }
    renderDims(d.dimensions ?? []);
  } catch (e: unknown) {
    const err = e as { message?: string };
    if (err.message !== 'auth' && radarEl) {
      radarEl.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
    }
  }
}

export function initDivergence(data: PageData): void {
  _divRepoId = String(data['repoId'] ?? '');
  _divBase   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(_divRepoId);

  const params = new URLSearchParams(location.search);
  _branchA = params.get('branch_a') ?? '';
  _branchB = params.get('branch_b') ?? '';

  (window as unknown as Record<string, unknown>)['_divToggleDim'] = (dim: string) => {
    _expanded[dim] = !_expanded[dim];
    renderDims(_lastDims);
  };
  (window as unknown as Record<string, unknown>)['_divOnBranchChange'] = () => {
    _branchA = (document.getElementById('sel-a') as HTMLSelectElement | null)?.value ?? '';
    _branchB = (document.getElementById('sel-b') as HTMLSelectElement | null)?.value ?? '';
    const url = new URL(location.href);
    url.searchParams.set('branch_a', _branchA);
    url.searchParams.set('branch_b', _branchB);
    history.replaceState(null, '', url.toString());
    void loadDivergence(_branchA, _branchB);
  };

  void (async () => {
    let branches: string[] = [];
    try {
      interface BranchesResp { branches: Array<{ name: string }> }
      const resp = (await window.apiFetch('/repos/' + _divRepoId + '/branches')) as BranchesResp;
      branches = (resp.branches ?? []).map(b => b.name);
    } catch { /* fall through with empty branches */ }

    const opts = branches.map(b =>
      '<option value="' + window.escHtml(b) + '">' + window.escHtml(b) + '</option>',
    ).join('');

    const el = document.getElementById('content');
    if (!el) return;
    el.innerHTML = `
      <div style="margin-bottom:12px">
        <a href="${_divBase}">&larr; Back to repo</a>
      </div>
      <div class="card">
        <h1 style="margin-bottom:12px">Divergence Visualization</h1>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
          <div>
            <div class="meta-label" style="font-size:11px;color:#8b949e;margin-bottom:4px">BRANCH A</div>
            <select id="sel-a" onchange="window._divOnBranchChange()">
              <option value="">Select branch&#8230;</option>${opts}
            </select>
          </div>
          <div style="display:flex;align-items:flex-end;padding-bottom:4px;font-size:18px;color:#8b949e">vs</div>
          <div>
            <div class="meta-label" style="font-size:11px;color:#8b949e;margin-bottom:4px">BRANCH B</div>
            <select id="sel-b" onchange="window._divOnBranchChange()">
              <option value="">Select branch&#8230;</option>${opts}
            </select>
          </div>
        </div>
        <div id="radar-area"><p class="loading">Select two branches to compare.</p></div>
        <div id="overall-area"></div>
      </div>
      <div id="dim-panels"></div>`;

    const selA = document.getElementById('sel-a') as HTMLSelectElement | null;
    const selB = document.getElementById('sel-b') as HTMLSelectElement | null;
    if (selA && _branchA) selA.value = _branchA;
    if (selB && _branchB) selB.value = _branchB;
    if (_branchA && _branchB) void loadDivergence(_branchA, _branchB);
  })();
}
