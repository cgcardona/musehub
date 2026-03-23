/**
 * motifs.ts — Motif browser page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "motifs", repoId, ref, owner, repoSlug, base }
 */

type PageData = Record<string, unknown>;

interface MotifTransformation {
  transformationType: string;
  transpositionSemitones: number;
  intervals: number[];
  track: string;
  occurrences: unknown[];
}

interface RecurrenceCell {
  track: string;
  section: string;
  present: boolean;
  transformationTypes?: string[];
  occurrenceCount?: number;
}

interface Motif {
  motifId: string;
  contourLabel: string;
  occurrenceCount: number;
  lengthBeats: number;
  track: string;
  tracks: string[];
  intervals: number[];
  recurrenceGrid: RecurrenceCell[];
  transformations: MotifTransformation[];
}

interface MotifsData {
  data: {
    motifs: Motif[];
    sections: string[];
    allTracks: string[];
    totalMotifs: number;
  };
}

let _allMotifs: Motif[] = [];
let _activeTrack   = '';
let _activeSection = '';
let _motifsApiData: MotifsData['data'] | null = null;

function pianoRollHtml(intervals: number[], motifId: string): string {
  const MAX_H = 48, MIN_H = 6;
  let pitch = 60;
  const pitches = [pitch];
  intervals.forEach(iv => { pitch += iv; pitches.push(pitch); });
  const lo = Math.min(...pitches);
  const hi = Math.max(...pitches);
  const span = hi - lo || 1;
  const notes = pitches.map(p => {
    const h = Math.round(MIN_H + ((p - lo) / span) * (MAX_H - MIN_H));
    const semitone = p % 12;
    const isBlack = [1,3,6,8,10].includes(semitone);
    const noteName = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][semitone];
    const bg = isBlack
      ? 'linear-gradient(to top,#0d419d,#388bfd)'
      : 'linear-gradient(to top,#1f6feb,#58a6ff)';
    return `<div class="piano-note" style="height:${h}px;background:${bg}"
      title="${noteName} (MIDI ${p})"></div>`;
  }).join('');
  return `<div class="piano-roll" id="roll-${window.escHtml(motifId)}">${notes}</div>
    <div class="interval-label">
      ${intervals.length > 0
        ? intervals.map(iv => (iv > 0 ? '+' : '') + iv).join(' ')
        : '(single note)'}
    </div>`;
}

function recurrenceGridHtml(
  _m: Motif,
  grid: RecurrenceCell[],
  sections: string[],
  tracks: string[],
): string {
  const sectionCols = sections.map(s => `<th>${window.escHtml(s)}</th>`).join('');
  const rows = tracks.map(track => {
    const cells = sections.map(sec => {
      const cell = (grid || []).find(c => c.track === track && c.section === sec);
      if (!cell?.present) return `<td class="cell-absent" title="Not present">—</td>`;
      const types = cell.transformationTypes ?? [];
      let cls = 'cell-present';
      let icon = '&#9679;';
      if (types.includes('inversion')) { cls = 'cell-inversion'; icon = '&#9651;'; }
      else if (types.includes('transposition')) { cls = 'cell-transposition'; icon = '&#9632;'; }
      const cnt = (cell.occurrenceCount ?? 0) > 1 ? ` &times;${cell.occurrenceCount}` : '';
      const tip = types.join(', ') + (cnt ? ', count: ' + String(cell.occurrenceCount) : '');
      return `<td class="${cls}" title="${window.escHtml(tip)}">${icon}${cnt}</td>`;
    }).join('');
    return `<tr><td class="track-label">&#127932; ${window.escHtml(track)}</td>${cells}</tr>`;
  }).join('');

  return `
    <div class="recurrence-grid">
      <table class="recurrence-table">
        <thead><tr><th>Track \\ Section</th>${sectionCols}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p style="font-size:11px;color:#8b949e;margin-top:6px">
        &#9679; original &nbsp; &#9651; inversion &nbsp; &#9632; transposition
      </p>
    </div>`;
}

function transformationsHtml(transformations: MotifTransformation[]): string {
  if (!transformations || transformations.length === 0) {
    return '<p style="font-size:13px;color:#8b949e">No transformations detected.</p>';
  }
  const rows = transformations.map(t => {
    const badge = `<span class="badge badge-transform"
      style="text-transform:uppercase;font-size:11px">${window.escHtml(t.transformationType)}</span>`;
    const transposeNote = t.transpositionSemitones !== 0
      ? `<span class="badge badge-track" style="font-size:11px">
          ${t.transpositionSemitones > 0 ? '+' : ''}${t.transpositionSemitones} st
         </span>`
      : '';
    const occ = (t.occurrences || []).length;
    return `
      <div class="transform-row">
        <div style="min-width:160px;display:flex;flex-direction:column;gap:6px">
          ${badge} ${transposeNote}
          <span style="font-size:12px;color:#8b949e">
            track: ${window.escHtml(t.track)} &bull; ${occ} occurrence${occ !== 1 ? 's' : ''}
          </span>
        </div>
        <div style="flex:1">
          ${pianoRollHtml(t.intervals || [], t.transformationType + '-' + t.track)}
        </div>
      </div>`;
  }).join('');
  return `<div class="transform-section">${rows}</div>`;
}

function motifCardHtml(m: Motif, sections: string[], tracks: string[]): string {
  const trackBadges = (m.tracks ?? []).map(t =>
    `<span class="badge badge-track" style="font-size:11px">&#127932; ${window.escHtml(t)}</span>`,
  ).join(' ');
  const contourBadge = `<span class="badge badge-contour" style="font-size:11px">
    &#128200; ${window.escHtml(m.contourLabel)}
  </span>`;
  const occBadge = `<span class="badge badge-open" style="font-size:11px">
    ${m.occurrenceCount} occurrence${m.occurrenceCount !== 1 ? 's' : ''}
  </span>`;
  const lenBadge = `<span class="badge" style="background:#21262d;border:1px solid #30363d;font-size:11px">
    ${m.lengthBeats} beat${m.lengthBeats !== 1 ? 's' : ''}
  </span>`;

  return `
    <div class="motif-card" id="motif-${window.escHtml(m.motifId)}">
      <div class="motif-header">
        <span class="motif-id">${window.escHtml(m.motifId)}</span>
        ${contourBadge}
        ${occBadge}
        ${lenBadge}
      </div>
      <div class="motif-meta">
        <div class="motif-meta-item">
          <span class="meta-label">Primary Track</span>
          <span class="meta-value">&#127932; ${window.escHtml(m.track)}</span>
        </div>
        <div class="motif-meta-item">
          <span class="meta-label">Cross-Track Sharing</span>
          <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">
            ${trackBadges || '<span style="color:#8b949e;font-size:13px">Only in primary track</span>'}
          </div>
        </div>
      </div>
      <div style="margin-bottom:12px">
        <span class="meta-label" style="display:block;margin-bottom:4px">Pattern</span>
        ${pianoRollHtml(m.intervals ?? [], m.motifId)}
      </div>
      <details style="margin-bottom:8px">
        <summary style="cursor:pointer;font-size:13px;color:#8b949e;
                        list-style:none;display:flex;align-items:center;gap:6px">
          <span>&#9660;</span>
          <strong style="color:#c9d1d9">Recurrence Grid</strong>
          <span style="font-size:11px;color:#8b949e">(tracks &times; sections)</span>
        </summary>
        ${recurrenceGridHtml(m, m.recurrenceGrid ?? [], sections, tracks)}
      </details>
      <details>
        <summary style="cursor:pointer;font-size:13px;color:#8b949e;
                        list-style:none;display:flex;align-items:center;gap:6px">
          <span>&#9660;</span>
          <strong style="color:#c9d1d9">Transformations</strong>
          <span class="badge" style="background:#1f3a1f;border:1px solid #238636;
                                     color:#56d364;font-size:11px">
            ${(m.transformations ?? []).length}
          </span>
        </summary>
        ${transformationsHtml(m.transformations ?? [])}
      </details>
    </div>`;
}

function renderMotifList(motifs: Motif[]): void {
  const listEl = document.getElementById('motif-list');
  if (!listEl) return;
  if (motifs.length === 0) {
    listEl.innerHTML = '<p class="loading">No motifs match the selected filters.</p>';
    return;
  }
  const sections = _motifsApiData?.sections ?? [];
  const tracks   = _motifsApiData?.allTracks ?? [];
  listEl.innerHTML = motifs.map(m => motifCardHtml(m, sections, tracks)).join('');
}

function applyFilters(): void {
  const filtered = _allMotifs.filter(m => {
    if (_activeTrack && m.track !== _activeTrack &&
        !(m.tracks ?? []).includes(_activeTrack)) return false;
    if (_activeSection) {
      const hasSection = (m.recurrenceGrid ?? [])
        .some(c => c.section === _activeSection && c.present);
      if (!hasSection) return false;
    }
    return true;
  });
  renderMotifList(filtered);
}

export function initMotifs(data: PageData): void {
  const repoId   = String(data['repoId'] ?? '');
  const ref      = String(data['ref'] ?? '');
  const base     = String(data['base'] ?? '');

  if (window.initRepoNav) void window.initRepoNav(repoId);

  // Inject toolbar HTML
  const contentEl = document.getElementById('content');
  if (contentEl) {
    contentEl.innerHTML = `
      <div style="margin-bottom:12px">
        <a href="${base}">&larr; Back to repo</a>
      </div>
      <div class="card">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">
          <h1 style="margin:0">&#127926; Motif Browser</h1>
          <code style="font-size:12px;background:#0d1117;padding:2px 8px;
                       border-radius:4px;border:1px solid #30363d">
            ref: ${ref.substring(0, 8)}
          </code>
          <a href="${base}/analysis/${ref}"
             class="btn btn-secondary" style="font-size:12px">
            All Dimensions
          </a>
        </div>
        <div id="summary" class="loading">Loading&#8230;</div>
        <div class="filter-bar" style="margin-top:12px">
          <div>
            <label for="track-filter">Track</label>
            <select id="track-filter" onchange="window._motifsTrackChange(this.value)">
              <option value="">All tracks</option>
            </select>
          </div>
          <div>
            <label for="section-filter">Section</label>
            <select id="section-filter" onchange="window._motifsSectionChange(this.value)">
              <option value="">All sections</option>
            </select>
          </div>
        </div>
      </div>
      <div id="motif-list"><p class="loading">Loading&#8230;</p></div>
    `;
  }

  // Expose filter handlers to HTML
  (window as unknown as Record<string, unknown>)['_motifsTrackChange'] = (v: string) => {
    _activeTrack = v;
    applyFilters();
  };
  (window as unknown as Record<string, unknown>)['_motifsSectionChange'] = (v: string) => {
    _activeSection = v;
    applyFilters();
  };

  void (async () => {
    try {
      const resp = (await window.apiFetch(
        '/repos/' + repoId + '/analysis/' + ref + '/motifs',
      )) as MotifsData;
      _motifsApiData = resp.data;
      _allMotifs = resp.data.motifs ?? [];
      const sections = resp.data.sections ?? [];
      const tracks   = resp.data.allTracks ?? [];
      const total    = resp.data.totalMotifs ?? 0;

      const trackOpts = ['<option value="">All tracks</option>',
        ...tracks.map(t => `<option value="${window.escHtml(t)}">${window.escHtml(t)}</option>`),
      ].join('');
      const sectionOpts = ['<option value="">All sections</option>',
        ...sections.map(s => `<option value="${window.escHtml(s)}">${window.escHtml(s)}</option>`),
      ].join('');

      const trackFilter = document.getElementById('track-filter');
      const sectionFilter = document.getElementById('section-filter');
      if (trackFilter) trackFilter.innerHTML = trackOpts;
      if (sectionFilter) sectionFilter.innerHTML = sectionOpts;

      const summaryEl = document.getElementById('summary');
      if (summaryEl) {
        summaryEl.innerHTML = `<span style="color:#8b949e;font-size:14px">
          ${total} motif${total !== 1 ? 's' : ''} detected &nbsp;&bull;&nbsp;
          ${sections.length} section${sections.length !== 1 ? 's' : ''} &nbsp;&bull;&nbsp;
          ${tracks.length} track${tracks.length !== 1 ? 's' : ''}
        </span>`;
      }

      renderMotifList(_allMotifs);
    } catch (e: unknown) {
      const err = e as { message?: string };
      if (err.message !== 'auth') {
        const el = document.getElementById('content');
        if (el) el.innerHTML = '<p class="error">&#10005; ' + window.escHtml(String(err.message ?? e)) + '</p>';
      }
    }
  })();
}
