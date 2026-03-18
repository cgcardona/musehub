/**
 * pages/analysis.ts
 *
 * Interactive branch divergence for the Musical Analysis page.
 * Handles:
 *   - Branch A / B selector changes → fetch divergence → re-render radar + cards
 *   - Radar SVG generation (pentagon, grid rings, score polygon, level-coloured dots)
 *   - Dimension card rendering with level badges and bar charts
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface AnalysisCfg {
  repoId: string;
  baseUrl: string;
  defaultBranch: string;
}

interface DivergenceDim {
  dimension: string;
  level: 'NONE' | 'LOW' | 'MED' | 'HIGH';
  score: number;
  description: string;
  branchACommits: number;
  branchBCommits: number;
}

interface DivergenceData {
  repoId: string;
  branchA: string;
  branchB: string;
  commonAncestor: string | null;
  dimensions: DivergenceDim[];
  overallScore: number;
}

// ---------------------------------------------------------------------------
// Globals from musehub.ts bundle
// ---------------------------------------------------------------------------
declare const apiFetch: (path: string) => Promise<unknown>;
declare const escHtml: (s: string) => string;
declare const initRepoNav: (id: string) => void;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const LEVEL_COLOR: Record<string, string> = {
  NONE: '#6e7681',
  LOW:  '#58a6ff',
  MED:  '#e3b341',
  HIGH: '#f85149',
};

const DIM_ORDER = ['melodic', 'harmonic', 'rhythmic', 'structural', 'dynamic'];

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let cfg: AnalysisCfg;

// ---------------------------------------------------------------------------
// Radar SVG builder
// ---------------------------------------------------------------------------
function buildRadarSvg(dims: DivergenceDim[], size = 260): string {
  const cx  = size / 2;
  const cy  = size / 2;
  const r   = size * 0.36;
  const n   = dims.length;
  const angles = Array.from({ length: n }, (_, i) => -Math.PI / 2 + (2 * Math.PI / n) * i);

  const pt = (score: number, i: number) => ({
    x: cx + score * r * Math.cos(angles[i]),
    y: cy + score * r * Math.sin(angles[i]),
  });

  const ringPts = (pct: number) =>
    angles.map(a => `${(cx + r * pct * Math.cos(a)).toFixed(1)},${(cy + r * pct * Math.sin(a)).toFixed(1)}`).join(' ');

  // Score polygon points
  const scorePts = dims.map((d, i) => {
    const { x, y } = pt(d.score, i);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  let svg = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<rect width="${size}" height="${size}" fill="#0d1117" rx="10"/>`;

  // Grid rings
  for (const pct of [0.25, 0.5, 0.75, 1.0]) {
    const sw = pct === 1.0 ? 1.5 : 1;
    svg += `<polygon points="${ringPts(pct)}" fill="none" stroke="#21262d" stroke-width="${sw}"/>`;
  }
  // % labels on 50% ring
  angles.forEach(a => {
    svg += `<line x1="${cx.toFixed(1)}" y1="${cy.toFixed(1)}" x2="${(cx + r * Math.cos(a)).toFixed(1)}" y2="${(cy + r * Math.sin(a)).toFixed(1)}" stroke="#21262d" stroke-width="1"/>`;
  });

  // Score area fill + stroke
  svg += `<polygon points="${scorePts}" fill="rgba(88,166,255,0.10)" stroke="#388bfd" stroke-width="2" stroke-linejoin="round"/>`;

  // Dots at each vertex, coloured by level
  dims.forEach((d, i) => {
    const { x, y } = pt(d.score, i);
    const col = LEVEL_COLOR[d.level] ?? '#6e7681';
    svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${col}" stroke="#0d1117" stroke-width="1.5"/>`;
  });

  // Dimension labels
  const LABELS = ['Melodic', 'Harmonic', 'Rhythmic', 'Structural', 'Dynamic'];
  angles.forEach((a, i) => {
    const lx = (cx + r * 1.28 * Math.cos(a)).toFixed(1);
    const ly = (cy + r * 1.28 * Math.sin(a) + 4).toFixed(1);
    const anchor = Math.abs(Math.cos(a)) < 0.2 ? 'middle' : Math.cos(a) < 0 ? 'end' : 'start';
    svg += `<text x="${lx}" y="${ly}" text-anchor="${anchor}" font-size="10" fill="#8b949e" font-family="system-ui,sans-serif">${escHtml(LABELS[i] ?? DIM_ORDER[i] ?? '')}</text>`;
  });

  svg += '</svg>';
  return svg;
}

// ---------------------------------------------------------------------------
// Dimension cards
// ---------------------------------------------------------------------------
function buildDimCards(dims: DivergenceDim[]): string {
  // Sort in DIM_ORDER
  const sorted = [...dims].sort((a, b) => {
    const ai = DIM_ORDER.indexOf(a.dimension.toLowerCase());
    const bi = DIM_ORDER.indexOf(b.dimension.toLowerCase());
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return sorted.map(d => {
    const pct   = Math.round(d.score * 100);
    const color = LEVEL_COLOR[d.level] ?? '#6e7681';
    return `
      <div class="an-dim-card">
        <div class="an-dim-header">
          <span class="an-dim-name">${escHtml(d.dimension)}</span>
          <span class="an-dim-level an-level-${d.level.toLowerCase()}">${d.level}</span>
          <span class="an-dim-pct">${pct}%</span>
        </div>
        <div class="an-dim-bar-track">
          <div class="an-dim-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <p class="an-dim-desc">${escHtml(d.description)}</p>
        <div class="an-dim-commits">
          <span class="an-dim-commit-pill">Branch A · ${d.branchACommits} commits</span>
          <span class="an-dim-commit-pill">Branch B · ${d.branchBCommits} commits</span>
        </div>
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Gauge update
// ---------------------------------------------------------------------------
function updateGauge(pct: number): void {
  const gauge = document.getElementById('an-gauge-circle');
  if (!gauge) return;
  const color = pct >= 75 ? '#f85149' : pct >= 50 ? '#e3b341' : pct >= 20 ? '#388bfd' : '#3fb950';
  (gauge as HTMLElement).style.background =
    `conic-gradient(${color} ${pct}%, #21262d 0)`;
  const pctEl = document.getElementById('an-gauge-pct');
  if (pctEl) pctEl.textContent = `${pct}%`;
  const lblEl = document.getElementById('an-gauge-label');
  if (lblEl) {
    lblEl.textContent = pct >= 75 ? 'Heavily diverged'
      : pct >= 50 ? 'Significantly diverged'
      : pct >= 20 ? 'Mildly diverged'
      : 'Nearly identical';
  }
}

// ---------------------------------------------------------------------------
// Load divergence
// ---------------------------------------------------------------------------
async function loadDivergence(branchA: string, branchB: string): Promise<void> {
  const radarEl    = document.getElementById('an-radar-svg');
  const cardsEl    = document.getElementById('an-dim-cards');
  const ancestorEl = document.getElementById('an-ancestor');

  if (radarEl) radarEl.innerHTML = '<div class="an-loading-sm">Computing divergence…</div>';
  if (cardsEl) cardsEl.innerHTML = '<div class="an-loading-sm">Loading dimensions…</div>';

  try {
    const data = await apiFetch(
      `/repos/${cfg.repoId}/divergence?branch_a=${encodeURIComponent(branchA)}&branch_b=${encodeURIComponent(branchB)}`
    ) as DivergenceData;

    const pct = Math.round(data.overallScore * 100);
    updateGauge(pct);
    if (radarEl) radarEl.innerHTML = buildRadarSvg(data.dimensions);
    if (cardsEl) cardsEl.innerHTML = buildDimCards(data.dimensions);
    if (ancestorEl) {
      const sha = data.commonAncestor ? data.commonAncestor.substring(0, 8) : 'none';
      ancestorEl.textContent = `Common ancestor: ${sha}`;
    }
  } catch (e) {
    const raw = (e as Error).message ?? '';
    // Parse friendly message from JSON error bodies (e.g. 422 {"detail":"..."})
    let friendly = raw;
    try {
      const colonIdx = raw.indexOf(':');
      if (colonIdx !== -1) {
        const jsonPart = raw.slice(colonIdx + 1).trim();
        const parsed = JSON.parse(jsonPart) as { detail?: string };
        if (parsed.detail) friendly = parsed.detail;
      }
    } catch { /* leave friendly as raw */ }

    const isNoCommits = friendly.toLowerCase().includes('no commits');
    const msg = isNoCommits
      ? `Branch <strong>${escHtml(branchA === cfg.defaultBranch ? branchB : branchA)}</strong> has no commits yet — push at least one commit to enable divergence analysis.`
      : escHtml(friendly);

    if (cardsEl) cardsEl.innerHTML = `<div class="an-loading-sm ${isNoCommits ? '' : 'error'}" style="text-align:left;padding:16px">${msg}</div>`;
    if (radarEl && !isNoCommits) radarEl.innerHTML = `<div class="an-loading-sm error">✕ ${escHtml(friendly)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export function initAnalysis(): void {
  cfg = (window as unknown as { __analysisCfg: AnalysisCfg }).__analysisCfg;
  if (!cfg) return;

  initRepoNav(cfg.repoId);

  const selA = document.getElementById('an-branch-a') as HTMLSelectElement | null;
  const selB = document.getElementById('an-branch-b') as HTMLSelectElement | null;

  const doCompare = () => {
    const bA = selA?.value;
    const bB = selB?.value;
    if (bA && bB) void loadDivergence(bA, bB);
  };

  // Attach event listeners via JS — no inline onchange/onclick on the HTML
  // elements. This prevents Chrome's autofill extension from firing change
  // events before our handler is ready and accidentally triggering API calls.
  selA?.addEventListener('change', doCompare);
  selB?.addEventListener('change', doCompare);
  document.getElementById('an-compare-btn')?.addEventListener('click', doCompare);

  // Keep window.onBranchChange as a no-op fallback (template may reference it)
  window.onBranchChange = doCompare;
}

declare global {
  interface Window {
    onBranchChange: () => void;
    __analysisCfg: AnalysisCfg;
  }
}
