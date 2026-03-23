/**
 * emotion.ts — Emotion analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "emotion", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

const EMOTION_COLORS: Record<string, string> = {
  joyful:      '#ffa657',
  serene:      '#3fb950',
  melancholic: '#58a6ff',
  tense:       '#f85149',
  energetic:   '#bc8cff',
  nostalgic:   '#f0883e',
  mysterious:  '#8b949e',
};

function emotionColor(label: string): string {
  return EMOTION_COLORS[label] ?? '#58a6ff';
}

function valenceArousalPlot(valence: number, arousal: number): string {
  const W = 240, H = 240, PAD = 20;
  const cx = PAD + ((valence + 1) / 2) * (W - PAD * 2);
  const cy = H - PAD - arousal * (H - PAD * 2);
  return `
    <svg viewBox="0 0 ${W} ${H}" style="width:${W}px;height:${H}px;display:block" role="img"
         aria-label="Valence-arousal plot">
      <line x1="${PAD}" y1="${H/2}" x2="${W-PAD}" y2="${H/2}" stroke="#30363d" stroke-width="1"/>
      <line x1="${W/2}" y1="${PAD}" x2="${W/2}" y2="${H-PAD}" stroke="#30363d" stroke-width="1"/>
      <text x="${PAD+2}" y="${H/2 - 4}" font-size="9" fill="#8b949e" font-family="monospace">negative</text>
      <text x="${W-PAD-34}" y="${H/2 - 4}" font-size="9" fill="#8b949e" font-family="monospace">positive</text>
      <text x="${W/2+4}" y="${PAD+10}" font-size="9" fill="#8b949e" font-family="monospace">energetic</text>
      <text x="${W/2+4}" y="${H-PAD-4}" font-size="9" fill="#8b949e" font-family="monospace">calm</text>
      <circle cx="${cx}" cy="${cy}" r="8" fill="#58a6ff" opacity="0.8"/>
      <circle cx="${cx}" cy="${cy}" r="12" fill="none" stroke="#58a6ff" stroke-width="1" opacity="0.4"/>
    </svg>`;
}

function axisBar(label: string, value: number, color: string): string {
  const pct = Math.round(value * 100);
  return `<div style="margin-bottom:12px">
    <div style="display:flex;justify-content:space-between;margin-bottom:4px">
      <span class="meta-label">${label}</span>
      <span style="font-size:13px;color:${color};font-weight:600">${pct}%</span>
    </div>
    <div style="height:8px;background:#21262d;border-radius:4px;overflow:hidden">
      <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;transition:width 0.4s ease"></div>
    </div>
  </div>`;
}

export function initEmotion(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface EmotionData {
        primaryEmotion: string;
        valence: number;
        arousal: number;
        tension: number;
        confidence: number;
      }
      interface EmotionResp { data: EmotionData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/emotion',
      )) as EmotionResp;
      const d = resp.data;
      const col = emotionColor(d.primaryEmotion);
      const valenceNorm = (d.valence + 1) / 2;

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
            <h1 style="margin:0">&#127917; Emotion Analysis</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:20px;align-items:flex-start">
            <div style="text-align:center">
              ${valenceArousalPlot(d.valence, d.arousal)}
              <span style="font-size:11px;color:#8b949e">Valence &times; Arousal</span>
            </div>
            <div style="flex:1;min-width:200px">
              <div style="margin-bottom:16px">
                <span class="meta-label">Primary Emotion</span>
                <div style="margin-top:6px">
                  <span class="badge" style="background:${col}22;color:${col};
                        border:1px solid ${col}44;font-size:16px;padding:4px 14px;text-transform:capitalize">
                    ${window.escHtml(d.primaryEmotion)}
                  </span>
                </div>
              </div>
              ${axisBar('Valence (negative \u2192 positive)', valenceNorm, '#58a6ff')}
              ${axisBar('Arousal (calm \u2192 energetic)', d.arousal, '#ffa657')}
              ${axisBar('Tension (relaxed \u2192 tense)', d.tension, '#f85149')}
              <div style="margin-top:8px">
                <span class="meta-label">Confidence</span>
                <span class="meta-value" style="margin-left:8px">${Math.round(d.confidence * 100)}%</span>
              </div>
            </div>
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
