/**
 * key.ts — Key detection page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "key", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

const MODE_COLORS: Record<string, string> = {
  major:      '#3fb950',
  minor:      '#58a6ff',
  dorian:     '#bc8cff',
  phrygian:   '#f85149',
  lydian:     '#ffa657',
  mixolydian: '#f0883e',
  locrian:    '#8b949e',
};

function modeColor(mode: string): string {
  return MODE_COLORS[mode] ?? '#58a6ff';
}

function confidenceBar(confidence: number): string {
  const pct = Math.round(confidence * 100);
  const color = confidence >= 0.8 ? '#3fb950' : confidence >= 0.6 ? '#f0883e' : '#f85149';
  return `
    <div style="display:flex;align-items:center;gap:10px;margin-top:4px">
      <div style="flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;transition:width 0.4s ease"></div>
      </div>
      <span style="font-size:13px;color:#8b949e;min-width:36px">${pct}%</span>
    </div>`;
}

interface AltKey { tonic: string; mode: string; confidence: number }

function alternateKeyRow(alt: AltKey): string {
  const color = modeColor(alt.mode);
  const pct = Math.round(alt.confidence * 100);
  return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-top:1px solid #21262d">
    <span style="min-width:80px;font-weight:600;color:#e6edf3;font-family:monospace">${window.escHtml(alt.tonic)} ${window.escHtml(alt.mode)}</span>
    <div style="flex:1;height:6px;background:#21262d;border-radius:4px;overflow:hidden">
      <div style="height:100%;width:${pct}%;background:${color}88;border-radius:4px"></div>
    </div>
    <span style="font-size:12px;color:#8b949e;min-width:32px">${pct}%</span>
  </div>`;
}

export function initKey(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface KeyData {
        tonic: string;
        mode: string;
        relativeKey: string;
        confidence: number;
        alternateKeys: AltKey[];
      }
      interface KeyResp { data: KeyData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/key',
      )) as KeyResp;
      const d = resp.data;
      const col = modeColor(d.mode);

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
            <h1 style="margin:0">&#127925; Key Detection</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px;flex-wrap:wrap">
            <div style="background:#0d1117;border:2px solid ${col}44;border-radius:12px;padding:20px 32px;text-align:center">
              <div style="font-size:36px;font-weight:700;color:${col};font-family:monospace;letter-spacing:2px">
                ${window.escHtml(d.tonic)}
              </div>
              <div style="font-size:15px;color:#8b949e;margin-top:4px;text-transform:capitalize">
                ${window.escHtml(d.mode)}
              </div>
            </div>
            <div>
              <div class="meta-row" style="gap:16px">
                <div class="meta-item">
                  <span class="meta-label">Relative Key</span>
                  <span class="meta-value" style="font-family:monospace">${window.escHtml(d.relativeKey)}</span>
                </div>
                <div class="meta-item" style="min-width:160px">
                  <span class="meta-label">Detection Confidence</span>
                  ${confidenceBar(d.confidence)}
                </div>
              </div>
            </div>
          </div>
          ${d.alternateKeys && d.alternateKeys.length > 0 ? `
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;margin-top:8px">
            <span class="meta-label" style="display:block;margin-bottom:8px">Alternate Key Candidates</span>
            ${d.alternateKeys.map(alternateKeyRow).join('')}
          </div>` : ''}
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
