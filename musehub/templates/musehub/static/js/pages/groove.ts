/**
 * groove.ts — Groove analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "groove", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

const GROOVE_STYLE_COLORS: Record<string, string> = {
  straight: '#3fb950',
  swing:    '#58a6ff',
  shuffled: '#bc8cff',
  latin:    '#ffa657',
  funk:     '#f0883e',
};

function grooveStyleColor(style: string): string {
  return GROOVE_STYLE_COLORS[style] ?? '#8b949e';
}

function scoreGauge(score: number): string {
  const pct = Math.round(score * 100);
  const color = score >= 0.8 ? '#3fb950' : score >= 0.6 ? '#f0883e' : '#f85149';
  return `
    <div style="margin-top:8px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:12px;color:#8b949e">0 (loose)</span>
        <span style="font-size:14px;font-weight:700;color:${color}">${pct}%</span>
        <span style="font-size:12px;color:#8b949e">100 (tight)</span>
      </div>
      <div style="height:10px;background:#21262d;border-radius:5px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:5px;transition:width 0.5s ease"></div>
      </div>
    </div>`;
}

function swingBar(swingFactor: number): string {
  const pct = Math.round(swingFactor * 100);
  const label = swingFactor < 0.53 ? 'straight' : swingFactor < 0.60 ? 'light swing' : 'hard swing';
  return `
    <div style="margin-top:8px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:12px;color:#8b949e">0.5 (straight)</span>
        <span style="font-size:13px;color:#e6edf3">${swingFactor.toFixed(3)} — ${label}</span>
        <span style="font-size:12px;color:#8b949e">0.67 (triplet)</span>
      </div>
      <div style="height:8px;background:#21262d;border-radius:4px;overflow:hidden;position:relative">
        <div style="position:absolute;left:0;right:0;top:0;bottom:0">
          <div style="height:100%;width:${pct}%;background:#58a6ff;border-radius:4px;
            transition:width 0.5s ease"></div>
        </div>
      </div>
    </div>`;
}

export function initGroove(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface GrooveData {
        style: string;
        bpm: number;
        gridResolution: string;
        onsetDeviation: number;
        grooveScore: number;
        swingFactor: number;
      }
      interface GrooveResp { data: GrooveData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/groove',
      )) as GrooveResp;
      const d = resp.data;
      const styleCol = grooveStyleColor(d.style);

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
            <h1 style="margin:0">&#129345; Groove Analysis</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div class="meta-row" style="margin-bottom:20px;flex-wrap:wrap">
            <div class="meta-item">
              <span class="meta-label">Style</span>
              <span class="meta-value">
                <span class="badge" style="background:${styleCol}22;color:${styleCol};
                      border:1px solid ${styleCol}44;font-size:14px;text-transform:capitalize">
                  ${window.escHtml(d.style)}
                </span>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">BPM</span>
              <span class="meta-value" style="font-size:22px;font-weight:700;color:#e6edf3">
                ${d.bpm.toFixed(1)}
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Grid Resolution</span>
              <span class="meta-value" style="font-family:monospace">${window.escHtml(d.gridResolution)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Onset Deviation</span>
              <span class="meta-value">${d.onsetDeviation.toFixed(4)} beats</span>
            </div>
          </div>
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;margin-bottom:14px">
            <span class="meta-label" style="display:block;margin-bottom:4px">Groove Score</span>
            ${scoreGauge(d.grooveScore)}
          </div>
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px">
            <span class="meta-label" style="display:block;margin-bottom:4px">Swing Factor</span>
            ${swingBar(d.swingFactor)}
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
