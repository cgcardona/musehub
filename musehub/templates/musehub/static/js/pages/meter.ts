/**
 * meter.ts — Meter analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "meter", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

function beatStrengthSvg(profile: number[]): string {
  if (!profile || profile.length === 0) return '<p class="loading">No beat data.</p>';
  const W = 400, H = 80, PAD = 16;
  const barW = Math.floor((W - PAD * 2) / profile.length) - 2;
  const maxV = Math.max(...profile, 0.01);
  const bars = profile.map((v, i) => {
    const x = PAD + i * (barW + 2);
    const h = Math.max(4, Math.round(((H - PAD * 2) * v) / maxV));
    const y = H - PAD - h;
    const color = i === 0 ? '#58a6ff' : '#30363d';
    return `<rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="2" fill="${color}"/>
            <text x="${x + barW / 2}" y="${H - 2}" text-anchor="middle" font-size="9" fill="#8b949e">${i + 1}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block" role="img"
       aria-label="Beat strength profile">
    ${bars}
  </svg>`;
}

interface IrregularSection { timeSignature: string; startBeat: number; endBeat: number }

function irregularRow(sec: IrregularSection): string {
  return `<div style="display:flex;align-items:center;gap:12px;padding:6px 0;border-top:1px solid #21262d;font-size:13px">
    <span style="font-family:monospace;color:#ffa657;min-width:48px">${window.escHtml(sec.timeSignature)}</span>
    <span style="color:#8b949e">beats ${sec.startBeat.toFixed(1)} &ndash; ${sec.endBeat.toFixed(1)}</span>
  </div>`;
}

export function initMeter(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface MeterData {
        timeSignature: string;
        isCompound: boolean;
        beatStrengthProfile: number[];
        irregularSections: IrregularSection[];
      }
      interface MeterResp { data: MeterData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/meter',
      )) as MeterResp;
      const d = resp.data;

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
            <h1 style="margin:0">&#127932; Meter Analysis</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div class="meta-row" style="margin-bottom:20px">
            <div class="meta-item">
              <span class="meta-label">Time Signature</span>
              <span class="meta-value" style="font-size:28px;font-weight:700;font-family:monospace;color:#58a6ff">
                ${window.escHtml(d.timeSignature)}
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Meter Type</span>
              <span class="meta-value">
                <span class="badge" style="background:${d.isCompound ? '#bc8cff22' : '#3fb95022'};
                  color:${d.isCompound ? '#bc8cff' : '#3fb950'};
                  border:1px solid ${d.isCompound ? '#bc8cff44' : '#3fb95044'};font-size:13px">
                  ${d.isCompound ? 'compound' : 'simple'}
                </span>
              </span>
            </div>
          </div>
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:16px">
            <span class="meta-label" style="display:block;margin-bottom:8px">Beat Strength Profile</span>
            ${beatStrengthSvg(d.beatStrengthProfile)}
            <p style="font-size:11px;color:#8b949e;margin:6px 0 0">
              Bar 1 is highlighted. Beat 1 is always the strongest downbeat.
            </p>
          </div>
          ${d.irregularSections && d.irregularSections.length > 0 ? `
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px">
            <span class="meta-label" style="display:block;margin-bottom:4px">Irregular Sections</span>
            ${d.irregularSections.map(irregularRow).join('')}
          </div>` : `
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;color:#8b949e;font-size:13px">
            No irregular meter sections detected.
          </div>`}
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
