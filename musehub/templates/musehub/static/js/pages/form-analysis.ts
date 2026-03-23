/**
 * form-analysis.ts — Form analysis page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "form-analysis", repoId, ref, base }
 */

type PageData = Record<string, unknown>;

const SECTION_COLORS: Record<string, string> = {
  intro:  '#58a6ff',
  verse:  '#3fb950',
  chorus: '#ffa657',
  bridge: '#bc8cff',
  outro:  '#8b949e',
  break:  '#f0883e',
};

function sectionColor(label: string): string {
  const key = (label ?? '').split('_')[0].toLowerCase();
  return SECTION_COLORS[key] ?? '#8b949e';
}

interface FormSection {
  label: string;
  function: string;
  startBeat: number;
  endBeat: number;
  lengthBeats: number;
}

function sectionBar(section: FormSection, totalBeats: number): string {
  const col = sectionColor(section.label);
  const startPct = totalBeats > 0 ? (section.startBeat / totalBeats) * 100 : 0;
  const widthPct = totalBeats > 0 ? (section.lengthBeats / totalBeats) * 100 : 10;
  return `<div style="position:absolute;left:${startPct.toFixed(2)}%;width:${Math.max(widthPct, 2).toFixed(2)}%;
            height:100%;background:${col};border-radius:3px;overflow:hidden"
            title="${window.escHtml(section.label)} (${section.lengthBeats.toFixed(0)} beats)">
    <span style="font-size:10px;color:#fff;padding:2px 4px;white-space:nowrap;
      overflow:hidden;display:inline-block;max-width:100%">
      ${window.escHtml(section.label)}
    </span>
  </div>`;
}

function sectionRow(section: FormSection): string {
  const col = sectionColor(section.label);
  return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;
            border-top:1px solid #21262d;font-size:13px">
    <span style="display:inline-block;width:12px;height:12px;border-radius:3px;
      background:${col};flex-shrink:0"></span>
    <span style="min-width:80px;font-weight:600;color:#e6edf3">${window.escHtml(section.label)}</span>
    <span style="color:#8b949e;min-width:80px">${window.escHtml(section.function)}</span>
    <span style="color:#8b949e;font-family:monospace;font-size:12px">
      b${section.startBeat.toFixed(0)} &ndash; ${section.endBeat.toFixed(0)}
      (${section.lengthBeats.toFixed(0)} beats)
    </span>
  </div>`;
}

export function initFormAnalysis(data: PageData): void {
  const repoId = String(data['repoId'] ?? '');
  const ref    = String(data['ref'] ?? '');
  const base   = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  void (async () => {
    try {
      interface FormData {
        formLabel: string;
        totalBeats: number;
        sections: FormSection[];
      }
      interface FormResp { data: FormData }
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + encodeURIComponent(ref) + '/form',
      )) as FormResp;
      const d = resp.data;

      const totalBeats = d.totalBeats || 1;
      const timeline = d.sections && d.sections.length > 0
        ? d.sections.map(s => sectionBar(s, totalBeats)).join('')
        : '';
      const sectionList = d.sections && d.sections.length > 0
        ? d.sections.map(sectionRow).join('')
        : '<p class="loading">No section data available.</p>';

      const el = document.getElementById('content');
      if (!el) return;
      el.innerHTML = `
        <div style="margin-bottom:12px">
          <a href="${window.escHtml(base)}">&larr; Back to repo</a>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
            <h1 style="margin:0">&#128203; Form Analysis</h1>
            <code style="font-size:13px;background:#0d1117;padding:2px 8px;border-radius:4px;color:#8b949e">
              ref: ${window.escHtml(ref.substring(0, 8))}
            </code>
          </div>
          <div class="meta-row" style="margin-bottom:20px">
            <div class="meta-item">
              <span class="meta-label">Form</span>
              <span class="meta-value" style="font-size:20px;font-weight:700;font-family:monospace;color:#58a6ff">
                ${window.escHtml(d.formLabel)}
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Total Beats</span>
              <span class="meta-value">${d.totalBeats}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Sections</span>
              <span class="meta-value">${d.sections ? d.sections.length : 0}</span>
            </div>
          </div>
          ${timeline ? `
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;margin-bottom:16px">
            <span class="meta-label" style="display:block;margin-bottom:10px">Form Timeline</span>
            <div style="position:relative;height:32px;background:#161b22;border-radius:4px;overflow:hidden">
              ${timeline}
            </div>
          </div>` : ''}
          <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px">
            <span class="meta-label" style="display:block;margin-bottom:4px">Sections</span>
            ${sectionList}
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
