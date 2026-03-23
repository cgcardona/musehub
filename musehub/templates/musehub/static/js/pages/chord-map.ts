/**
 * chord-map.ts — Chord map analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "chord-map", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

function tensionColor(tension: number): string {
  if (tension >= 0.7) return '#f85149';
  if (tension >= 0.4) return '#f0883e';
  return '#3fb950';
}

interface ChordEvent {
  beat: number;
  chord: string;
  function: string;
  tension: number;
}

function chordRow(event: ChordEvent): string {
  const col = tensionColor(event.tension);
  const tensionPct = Math.round(event.tension * 100);
  return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;
            border-top:1px solid #21262d;font-size:13px">
    <span style="min-width:36px;color:#8b949e;font-size:12px">b${event.beat.toFixed(1)}</span>
    <span style="min-width:60px;font-weight:700;font-family:monospace;color:#e6edf3;font-size:15px">
      ${window.escHtml(event.chord)}
    </span>
    <span style="min-width:40px;color:#8b949e;font-family:monospace">${window.escHtml(event.function)}</span>
    <div style="flex:1;height:6px;background:#21262d;border-radius:3px;overflow:hidden">
      <div style="height:100%;width:${tensionPct}%;background:${col};border-radius:3px"></div>
    </div>
    <span style="font-size:11px;color:${col};min-width:28px">${tensionPct}%</span>
  </div>`;
}

function tensionCurveSvg(curve: number[]): string {
  if (!curve || curve.length === 0) return '';
  const W = 700, H = 80, PAD = 16;
  const pts = curve.map((v, i) => {
    const x = PAD + (i / (curve.length - 1 || 1)) * (W - PAD * 2);
    const y = PAD + (1 - v) * (H - PAD * 2);
    return x + ',' + y;
  }).join(' ');
  return `
    <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:16px">
      <span class="meta-label" style="display:block;margin-bottom:8px">Tension Curve (per beat)</span>
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block" role="img"
           aria-label="Harmonic tension curve">
        <polyline points="${pts}" fill="none" stroke="#f0883e" stroke-width="2" stroke-linejoin="round"/>
        <text x="${PAD}" y="${H - 2}" font-size="10" fill="#8b949e" font-family="monospace">beat 1</text>
        <text x="${W - PAD - 10}" y="${H - 2}" font-size="10" fill="#8b949e" font-family="monospace">${curve.length}</text>
        <text x="2" y="${PAD + 4}" font-size="10" fill="#8b949e" font-family="monospace">tense</text>
        <text x="2" y="${H - PAD + 4}" font-size="10" fill="#8b949e" font-family="monospace">calm</text>
      </svg>
    </div>`;
}

export function initChordMap(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface ChordMapData {
        totalChords: number;
        totalBeats: number;
        tensionCurve: number[];
        progression: ChordEvent[];
      }
      interface ChordMapResp { data: ChordMapData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/chord-map',
      )) as ChordMapResp;
      const d = resp.data;

      const chordRows = d.progression && d.progression.length > 0
        ? d.progression.map(chordRow).join('')
        : '<p class="loading">No chord data available.</p>';

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px">
            <h1 style="margin:0">&#127929; Chord Map</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div class="meta-row" style="margin-bottom:16px">
            <div class="meta-item">
              <span class="meta-label">Total Chords</span>
              <span class="meta-value" style="font-size:22px;font-weight:700;color:#58a6ff">${d.totalChords}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Total Beats</span>
              <span class="meta-value">${d.totalBeats}</span>
            </div>
          </div>
          ${tensionCurveSvg(d.tensionCurve)}
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;margin-bottom:16px">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
              <span class="meta-label">Chord Progression</span>
              <span style="font-size:11px;color:#8b949e">beat · chord · function · tension</span>
            </div>
            ${chordRows}
          </div>
        </div>`;
    } catch (e: unknown) {
      const err = e as { message?: string };
      if (err.message !== 'auth') {
        const el = document.getElementById('content');
        if (el) el.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
      }
    }
  })();
}
