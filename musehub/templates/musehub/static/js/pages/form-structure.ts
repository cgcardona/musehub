/**
 * form-structure.ts — Form and structure analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "form-structure", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

interface SectionMapEntry {
  label: string;
  function: string;
  startBar: number;
  endBar: number;
  barCount: number;
  colorHint: string;
}

interface RepetitionEntry {
  patternLabel: string;
  occurrenceCount: number;
  occurrences: number[];
  similarityScore: number;
}

interface HeatmapData {
  labels: string[];
  matrix: number[][];
}

interface FormStructureData {
  formLabel: string;
  timeSignature: string;
  totalBars: number;
  sectionMap: SectionMapEntry[];
  repetitionStructure: RepetitionEntry[];
  sectionComparison: HeatmapData;
}

function renderSectionMap(data: FormStructureData): string {
  const sections = data.sectionMap ?? [];
  const totalBars = data.totalBars || 1;
  if (sections.length === 0) return '<p class="loading">No sections detected.</p>';

  const W = 720, H = 64, PAD = 8;
  const usable = W - PAD * 2;

  const rects = sections.map(s => {
    const x = PAD + ((s.startBar - 1) / totalBars) * usable;
    const w = Math.max(2, (s.barCount / totalBars) * usable);
    const label = s.barCount > 3 ? window.escHtml(s.label) : '';
    const barRange = s.startBar === s.endBar ? 'b' + s.startBar : 'b' + s.startBar + '-' + s.endBar;
    return `
      <rect x="${x.toFixed(1)}" y="8" width="${w.toFixed(1)}" height="36"
            rx="4" fill="${window.escHtml(s.colorHint)}" opacity="0.85">
        <title>${window.escHtml(s.label)} (${window.escHtml(s.function)}) | ${window.escHtml(barRange)} | ${s.barCount} bars</title>
      </rect>
      ${label ? `<text x="${(x + w/2).toFixed(1)}" y="31" font-size="11" fill="#fff"
          text-anchor="middle" font-family="-apple-system,sans-serif"
          style="pointer-events:none">${label}</text>` : ''}
      <text x="${(x + w/2).toFixed(1)}" y="57" font-size="9" fill="#8b949e"
          text-anchor="middle" font-family="monospace"
          style="pointer-events:none">${window.escHtml(barRange)}</text>`;
  }).join('');

  const tickStep = Math.ceil(totalBars / 16);
  let ticks = '';
  for (let b = 1; b <= totalBars; b += tickStep) {
    const x = PAD + ((b - 1) / totalBars) * usable;
    ticks += `<line x1="${x.toFixed(1)}" y1="44" x2="${x.toFixed(1)}" y2="48"
                   stroke="#30363d" stroke-width="1"/>`;
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"
               style="width:100%;height:auto;display:block">
    <rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/>
    ${rects}
    ${ticks}
  </svg>`;
}

function renderHeatmap(data: FormStructureData): string {
  const heatmap = data.sectionComparison ?? {};
  const labels = heatmap.labels ?? [];
  const matrix = heatmap.matrix ?? [];
  const n = labels.length;
  if (n === 0) return '<p class="loading">No sections to compare.</p>';

  const cellSize = Math.min(60, Math.floor(480 / n));
  const labelW   = 72;
  const svgW = labelW + n * cellSize + 8;
  const svgH = labelW + n * cellSize + 8;

  function heatColor(v: number): string {
    const r = Math.round(13  + v * (63  - 13));
    const g = Math.round(17  + v * (185 - 17));
    const b = Math.round(23  + v * (80  - 23));
    return `rgb(${r},${g},${b})`;
  }

  let cells = '';
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = (matrix[i] ?? [])[j] ?? 0;
      const x = labelW + j * cellSize;
      const y = labelW + i * cellSize;
      cells += `<rect x="${x}" y="${y}" width="${cellSize}" height="${cellSize}"
                      fill="${heatColor(v)}">
                  <title>${window.escHtml(labels[i] ?? '')} vs ${window.escHtml(labels[j] ?? '')}: ${v.toFixed(3)}</title>
                </rect>
                <text x="${(x + cellSize/2).toFixed(1)}" y="${(y + cellSize/2 + 4).toFixed(1)}"
                      font-size="9" fill="rgba(255,255,255,0.7)"
                      text-anchor="middle" font-family="monospace"
                      style="pointer-events:none">${v === 1.0 ? '1' : v.toFixed(2)}</text>`;
    }
    const ry = labelW + i * cellSize + cellSize / 2;
    cells += `<text x="${labelW - 4}" y="${(ry + 4).toFixed(1)}"
                    font-size="10" fill="#c9d1d9" text-anchor="end"
                    font-family="-apple-system,sans-serif">${window.escHtml(labels[i] ?? '')}</text>`;
    const cx = labelW + i * cellSize + cellSize / 2;
    cells += `<text x="${cx.toFixed(1)}" y="${(labelW - 6).toFixed(1)}"
                    font-size="10" fill="#c9d1d9" text-anchor="end"
                    font-family="-apple-system,sans-serif"
                    transform="rotate(-45 ${cx.toFixed(1)} ${(labelW - 6).toFixed(1)})">${window.escHtml(labels[i] ?? '')}</text>`;
  }

  const legendW = Math.min(200, n * cellSize);
  const stops = [0, 0.25, 0.5, 0.75, 1.0].map(v =>
    `<stop offset="${(v * 100).toFixed(0)}%" stop-color="${heatColor(v)}"/>`,
  ).join('');
  const legend = `
    <defs><linearGradient id="hg" x1="0" x2="1" y1="0" y2="0">${stops}</linearGradient></defs>
    <rect x="${labelW}" y="${svgH - 14}" width="${legendW}" height="8"
          fill="url(#hg)" rx="2"/>
    <text x="${labelW}" y="${svgH}" font-size="9" fill="#8b949e">0</text>
    <text x="${labelW + legendW}" y="${svgH}" font-size="9" fill="#8b949e"
          text-anchor="end">1.0</text>`;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${svgW}" height="${svgH + 20}"
               style="width:100%;height:auto;display:block;max-width:${svgW}px">
    ${cells}
    ${legend}
  </svg>`;
}

function renderRepetition(data: FormStructureData): string {
  const reps = data.repetitionStructure ?? [];
  if (reps.length === 0) return '<p class="loading">No repeated sections detected.</p>';

  return reps.map(r => {
    const occStr = r.occurrences.map(b => 'b' + b).join(', ');
    const simPct = Math.round(r.similarityScore * 100);
    return `
      <div class="commit-row" style="align-items:flex-start;flex-direction:column;gap:4px">
        <div style="display:flex;align-items:center;gap:10px;width:100%">
          <span style="font-size:14px;font-weight:600;color:#e6edf3;min-width:90px">
            ${window.escHtml(r.patternLabel)}
          </span>
          <span class="badge badge-open" style="font-size:12px;background:#1a3a5c">
            ${r.occurrenceCount}x
          </span>
          <span style="font-size:12px;color:#8b949e;margin-left:auto">sim ${simPct}%</span>
        </div>
        <div style="font-size:12px;color:#8b949e">Starts at: ${window.escHtml(occStr)}</div>
      </div>`;
  }).join('');
}

export function initFormStructure(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  void (async () => {
    try {
      const fsData = (await window.apiFetch(
        '/repos/' + repoId + '/form-structure/' + ref,
      )) as FormStructureData;

      const smEl  = document.getElementById('section-map-content');
      const repEl = document.getElementById('repetition-content');
      const hmEl  = document.getElementById('heatmap-content');

      if (smEl) {
        smEl.innerHTML = `
          <div style="overflow-x:auto">${renderSectionMap(fsData)}</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">
            ${(fsData.sectionMap ?? []).map(s =>
              '<span style="display:inline-flex;align-items:center;gap:5px;font-size:12px">'
              + '<svg width="12" height="12"><rect width="12" height="12" rx="2" fill="' + window.escHtml(s.colorHint) + '"/></svg>'
              + window.escHtml(s.label) + ' (' + s.barCount + 'b)'
              + '</span>',
            ).join('')}
          </div>`;
      }
      if (repEl) {
        repEl.innerHTML = renderRepetition(fsData);
      }
      if (hmEl) {
        hmEl.innerHTML = `
          <p style="font-size:12px;color:#8b949e;margin-bottom:12px">
            Cell colour intensity = pairwise similarity (0=unrelated, 1=identical).
            Hover a cell for the exact score.
          </p>
          <div style="overflow-x:auto">${renderHeatmap(fsData)}</div>`;
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      if (err.message !== 'auth') {
        const smEl = document.getElementById('section-map-content');
        if (smEl) smEl.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
      }
    }
  })();
}
