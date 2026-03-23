/**
 * contour.ts — Melodic contour page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "contour", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

function pitchCurveSvg(pitchCurve: number[]): string {
  if (!pitchCurve || pitchCurve.length === 0) return '<p class="loading">No pitch data.</p>';
  const W = 700, H = 120, pad = 24;
  const min = Math.min(...pitchCurve);
  const max = Math.max(...pitchCurve);
  const range = max - min || 1;
  const pts = pitchCurve.map((v, i) => {
    const x = pad + (i / (pitchCurve.length - 1 || 1)) * (W - pad * 2);
    const y = pad + ((max - v) / range) * (H - pad * 2);
    return x + ',' + y;
  }).join(' ');
  return `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block" role="img"
         aria-label="Melodic pitch contour">
      <polyline points="${pts}" fill="none" stroke="#58a6ff" stroke-width="2"/>
      <text x="${pad}" y="${H - 6}" font-size="10" fill="#8b949e" font-family="monospace">beat 1</text>
      <text x="${W - pad - 10}" y="${H - 6}" font-size="10" fill="#8b949e" font-family="monospace">${pitchCurve.length}</text>
      <text x="6" y="${pad + 4}" font-size="10" fill="#8b949e" font-family="monospace">${Math.round(max)}</text>
      <text x="6" y="${H - pad + 4}" font-size="10" fill="#8b949e" font-family="monospace">${Math.round(min)}</text>
    </svg>`;
}

const SHAPE_COLORS: Record<string, string> = {
  ascending: '#3fb950', descending: '#f85149', arch: '#58a6ff',
  'inverted-arch': '#f0883e', wave: '#bc8cff', static: '#8b949e', flat: '#8b949e',
};

function shapeColor(s: string): string { return SHAPE_COLORS[s] ?? '#8b949e'; }

function midiNoteName(midi: number): string {
  const names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const oct = Math.floor(midi / 12) - 1;
  return names[midi % 12] + oct;
}

function tessituraBar(pitchCurve: number[]): string {
  if (!pitchCurve || pitchCurve.length === 0) return '';
  const lo = Math.min(...pitchCurve);
  const hi = Math.max(...pitchCurve);
  const octaves = ((hi - lo) / 12).toFixed(1);
  const loNote  = midiNoteName(Math.round(lo));
  const hiNote  = midiNoteName(Math.round(hi));
  const pct = Math.min(100, ((hi - lo) / 48) * 100);
  return `
    <div style="margin-top:12px">
      <span class="meta-label">Tessitura</span>
      <div style="display:flex;align-items:center;gap:10px;margin-top:4px">
        <span style="font-size:13px;color:#8b949e;font-family:monospace;min-width:28px">${loNote}</span>
        <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div style="height:100%;width:${pct}%;background:#58a6ff;border-radius:4px"></div>
        </div>
        <span style="font-size:13px;color:#8b949e;font-family:monospace;min-width:28px">${hiNote}</span>
        <span style="font-size:12px;color:#8b949e">${octaves} oct</span>
      </div>
    </div>`;
}

let _repoId = '';
let _ref = '';
let _base = '';

interface ContourData {
  shape: string;
  overallDirection: string;
  directionChanges: number;
  peakBeat: number;
  valleyBeat: number;
  pitchCurve: number[];
}

async function loadContour(track: string | null): Promise<void> {
  try {
    let url = '/repos/' + _repoId + '/analysis/' + encodeURIComponent(_ref) + '/contour';
    if (track) url += '?track=' + encodeURIComponent(track);

    interface ContourResp { data: ContourData }
    const resp = (await window.apiFetch(url)) as ContourResp;
    const d = resp.data;
    const shapeCol = shapeColor(d.shape);
    const svg = pitchCurveSvg(d.pitchCurve);
    const tess = tessituraBar(d.pitchCurve);

    const el = document.getElementById('content');
    if (!el) return;
    el.innerHTML = `
      <div style="margin-bottom:12px">
        <a href="${_base}">&larr; Back to repo</a>
      </div>
      <div class="card">
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px">
          <h1 style="margin:0">&#9835; Melodic Contour</h1>
          <span class="meta-value" style="font-family:monospace;color:#8b949e;font-size:13px">
            ref: ${window.escHtml(_ref.substring(0, 8))}
          </span>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px">
          <label style="font-size:13px;color:#8b949e">Track filter:</label>
          <input id="track-inp" type="text" placeholder="bass, keys, lead&#8230;"
                 value="${window.escHtml(track ?? '')}"
                 style="background:#0d1117;color:#c9d1d9;border:1px solid #30363d;
                        border-radius:6px;padding:6px 10px;font-size:13px;width:180px" />
          <button class="btn btn-secondary" style="font-size:13px"
                  onclick="window._contourLoad((document.getElementById('track-inp')).value.trim() || null)">
            Apply
          </button>
        </div>
        <div class="meta-row" style="margin-bottom:16px">
          <div class="meta-item">
            <span class="meta-label">Shape</span>
            <span class="meta-value">
              <span class="badge" style="background:${shapeCol}22;color:${shapeCol};
                    border:1px solid ${shapeCol}44;font-size:14px">${window.escHtml(d.shape)}</span>
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Overall Direction</span>
            <span class="meta-value">${window.escHtml(d.overallDirection)}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Direction Changes</span>
            <span class="meta-value">${d.directionChanges}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Peak Beat</span>
            <span class="meta-value">${d.peakBeat}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Valley Beat</span>
            <span class="meta-value">${d.valleyBeat}</span>
          </div>
        </div>
        <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:12px">
          <span class="meta-label" style="display:block;margin-bottom:8px">
            Pitch Curve (MIDI, per quarter-note)
          </span>
          ${svg}
        </div>
        ${tess}
      </div>`;
  } catch (e: unknown) {
    const err = e as { message?: string };
    if (err.message !== 'auth') {
      const el = document.getElementById('content');
      if (el) el.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
    }
  }
}

export function initContour(data: PageData): void {
  _repoId = String(data['repoId'] ?? '');
  _ref    = String(data['ref'] ?? '');
  _base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(_repoId);

  // Expose load function for button onclick
  (window as unknown as Record<string, unknown>)['_contourLoad'] = (track: string | null) => {
    void loadContour(track);
  };

  void loadContour(null);
}
