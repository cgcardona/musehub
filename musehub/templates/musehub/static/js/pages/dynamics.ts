/**
 * dynamics.ts — Dynamics analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "dynamics", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

const ARC_COLORS: Record<string, string> = {
  flat:        '#8b949e',
  terraced:    '#bc8cff',
  crescendo:   '#3fb950',
  decrescendo: '#f0883e',
  swell:       '#58a6ff',
  hairpin:     '#ff7b72',
};

function arcBadge(arc: string): string {
  const color = ARC_COLORS[arc] ?? '#8b949e';
  return `<span style="display:inline-block;padding:2px 10px;border-radius:12px;
    font-size:12px;font-weight:600;background:${color}22;border:1px solid ${color};
    color:${color}">${window.escHtml(arc)}</span>`;
}

interface VelocityPoint { beat: number; velocity: number }

function velocityGraphSvg(curve: VelocityPoint[]): string {
  const W = 280, H = 60, PAD = 6;
  if (!curve || curve.length === 0) return '<em style="color:#8b949e;font-size:12px">no data</em>';
  const maxBeat = curve[curve.length - 1].beat || 30;
  const points = curve.map(e => {
    const x = PAD + (e.beat / maxBeat) * (W - 2 * PAD);
    const y = PAD + (1 - e.velocity / 127) * (H - 2 * PAD);
    return x + ',' + y;
  }).join(' ');
  const firstX = PAD + (curve[0].beat / maxBeat) * (W - 2 * PAD);
  const lastX  = PAD + (curve[curve.length - 1].beat / maxBeat) * (W - 2 * PAD);
  const polyFill = points + ' ' + lastX + ',' + (H - PAD) + ' ' + firstX + ',' + (H - PAD);
  return `<svg width="${W}" height="${H}" style="display:block;border-radius:4px;background:#0d1117">
    <defs>
      <linearGradient id="vg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.5"/>
        <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.05"/>
      </linearGradient>
    </defs>
    <polygon points="${polyFill}" fill="url(#vg)"/>
    <polyline points="${points}" fill="none" stroke="#58a6ff" stroke-width="1.5"
      stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

interface TrackData {
  track: string;
  arc: string;
  peakVelocity: number;
  minVelocity: number;
  meanVelocity: number;
  velocityRange: number;
  velocityCurve: VelocityPoint[];
}

function loudnessBarChart(tracks: TrackData[]): string {
  if (!tracks || tracks.length === 0) return '';
  const bars = tracks.map(t => {
    const pct = Math.round((t.peakVelocity / 127) * 100);
    const color = ARC_COLORS[t.arc] ?? '#58a6ff';
    return `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:13px">
        <span style="color:#e6edf3">${window.escHtml(t.track)}</span>
        <span style="color:#8b949e;font-size:12px">${t.peakVelocity} / 127</span>
      </div>
      <div style="background:#21262d;border-radius:4px;height:10px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:4px;transition:width 0.4s ease"></div>
      </div>
    </div>`;
  }).join('');
  return `<div style="margin-top:8px">${bars}</div>`;
}

function trackCard(t: TrackData): string {
  return `<div class="card" style="margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap">
      <h2 style="margin:0;font-size:15px;color:#e6edf3">${window.escHtml(t.track)}</h2>
      ${arcBadge(t.arc)}
    </div>
    <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:10px">
      <div class="meta-item">
        <span class="meta-label">Peak Velocity</span>
        <span class="meta-value" style="font-size:18px;color:#58a6ff">${t.peakVelocity}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Min Velocity</span>
        <span class="meta-value">${t.minVelocity}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Mean Velocity</span>
        <span class="meta-value">${t.meanVelocity.toFixed(1)}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Range</span>
        <span class="meta-value">${t.velocityRange}</span>
      </div>
    </div>
    <div>
      <span class="meta-label" style="display:block;margin-bottom:6px">Velocity Profile</span>
      ${velocityGraphSvg(t.velocityCurve)}
    </div>
  </div>`;
}

let _knownTracks: string[] = [];
const _sections = ['intro', 'verse_1', 'chorus', 'verse_2', 'outro'];

let _repoId = '';
let _ref = '';
let _base = '';

function buildFilters(currentTrack: string, currentSection: string): string {
  const trackOpts = ['', ..._knownTracks].map(t =>
    `<option value="${window.escHtml(t)}" ${t === currentTrack ? 'selected' : ''}>${t || 'All tracks'}</option>`,
  ).join('');
  const secOpts = ['', ..._sections].map(s =>
    `<option value="${window.escHtml(s)}" ${s === currentSection ? 'selected' : ''}>${s || 'All sections'}</option>`,
  ).join('');
  return `
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
      <div class="meta-item">
        <span class="meta-label">Track</span>
        <select id="track-sel" onchange="window._dynApplyFilters()">
          ${trackOpts}
        </select>
      </div>
      <div class="meta-item">
        <span class="meta-label">Section</span>
        <select id="section-sel" onchange="window._dynApplyFilters()">
          ${secOpts}
        </select>
      </div>
    </div>`;
}

async function loadDynamics(track: string | null, section: string | null): Promise<void> {
  const contentEl = document.getElementById('content');
  if (contentEl) contentEl.innerHTML = '<p class="loading">Loading dynamics data&#8230;</p>';
  try {
    let url = '/repos/' + _repoId + '/analysis/' + encodeURIComponent(_ref) + '/dynamics/page';
    const params: string[] = [];
    if (track)   params.push('track='   + encodeURIComponent(track));
    if (section) params.push('section=' + encodeURIComponent(section));
    if (params.length) url += '?' + params.join('&');

    interface DynamicsResp { tracks: TrackData[] }
    const data = (await window.apiFetch(url)) as DynamicsResp;

    _knownTracks = data.tracks.map(t => t.track);
    const trackCards = data.tracks.length === 0
      ? '<p class="loading">No track data available for this ref.</p>'
      : data.tracks.map(trackCard).join('');
    const sortedTracks = [...data.tracks].sort((a, b) => b.peakVelocity - a.peakVelocity);

    const el = document.getElementById('content');
    if (!el) return;
    el.innerHTML = `
      <div style="margin-bottom:12px">
        <a href="${_base}">&larr; Back to repo</a>
      </div>
      <div class="card" style="border-color:#1f6feb;margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap">
          <h1 style="margin:0">&#127897; Dynamics Analysis</h1>
          <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;
            color:#8b949e">${window.escHtml(_ref.substring(0, 12))}</code>
          <span style="font-size:13px;color:#8b949e">
            ${data.tracks.length} track${data.tracks.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>
      ${buildFilters(track ?? '', section ?? '')}
      <div class="card" style="margin-bottom:16px">
        <h2 style="margin-bottom:14px">&#128202; Cross-Track Loudness</h2>
        ${loudnessBarChart(sortedTracks)}
      </div>
      ${trackCards}
    `;
  } catch (e: unknown) {
    const err = e as { message?: string };
    if (err.message !== 'auth') {
      const el = document.getElementById('content');
      if (el) el.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
    }
  }
}

export function initDynamics(data: PageData): void {
  _repoId = String(data['repoId'] ?? '');
  _ref    = String(data['ref'] ?? '');
  _base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(_repoId);

  // Expose filter handler to HTML event handlers
  (window as unknown as Record<string, unknown>)['_dynApplyFilters'] = () => {
    const track   = (document.getElementById('track-sel') as HTMLSelectElement | null)?.value ?? null;
    const section = (document.getElementById('section-sel') as HTMLSelectElement | null)?.value ?? null;
    void loadDynamics(track || null, section || null);
  };

  void loadDynamics(null, null);
}
