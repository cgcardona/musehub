/**
 * score.ts — Musical score / notation viewer page module.
 *
 * Config is read from window.__scoreCfg (set by the page_data block).
 * Registered as: window.MusePages['score']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScoreCfg {
  repoId: string;
  ref: string;
  owner: string;
  repoSlug: string;
  base: string;
  scorePath: string | null;
}

interface ScoreNote {
  pitch_name: string;
  octave: number;
  duration: string;
  start_beat: number;
  velocity?: number;
  track_id?: number;
}

interface ScoreTrack {
  track_id: number;
  clef?: string;
  key_signature?: string;
  time_signature?: string;
  instrument?: string;
  notes?: ScoreNote[];
}

interface NotationData {
  key?: string;
  tempo?: number;
  timeSig?: string;
  tracks?: ScoreTrack[];
}

declare global {
  interface Window { __scoreCfg?: ScoreCfg; }
}

// Globals injected from musehub.ts bundle
declare const escHtml: (s: unknown) => string;
declare const apiFetch: (path: string) => Promise<unknown>;
declare const initRepoNav: (id: string) => void;

// ── Score renderer constants ───────────────────────────────────────────────────

// STAFF_HEIGHT = 80 px total per staff (5 lines × 16px apart) — kept for reference
const LINE_GAP      = 8;   // px between staff lines
const STAFF_Y       = 24;  // top margin inside staff-container
const STAFF_LINES   = 5;
const BAR_WIDTH     = 120; // px per bar
const LEFT_MARGIN   = 60;  // px for clef + time sig
const NOTE_RADIUS   = 5;   // px
const STEM_LENGTH   = 28;  // px

// MIDI pitch → staff position (treble clef: bottom line = E4)
const PITCH_TO_STAFF_TREBLE: Record<string, number> = {
  'C3': -7, 'D3': -6, 'E3': -5, 'F3': -4, 'G3': -3, 'A3': -2, 'B3': -1,
  'C4': 0, 'D4': 1, 'E4': 2, 'F4': 3, 'G4': 4, 'A4': 5, 'B4': 6,
  'C5': 7, 'D5': 8, 'E5': 9, 'F5': 10, 'G5': 11, 'A5': 12, 'B5': 13,
};

// Bass clef: bottom line = G2
const PITCH_TO_STAFF_BASS: Record<string, number> = {
  'C1': -5, 'D1': -4, 'E1': -3, 'F1': -2, 'G1': -1,
  'A1': 0, 'B1': 1, 'C2': 2, 'D2': 3, 'E2': 4, 'F2': 5, 'G2': 6,
  'A2': 7, 'B2': 8, 'C3': 9, 'D3': 10, 'E3': 11, 'F3': 12, 'G3': 13,
  'A3': 14, 'B3': 15, 'C4': 16,
};

const DUR_BEATS: Record<string, number> = {
  '1/1': 4, '1/2': 2, '1/4': 1, '1/8': 0.5, '1/16': 0.25,
};

// ── Module state ──────────────────────────────────────────────────────────────

let notationData: NotationData | null = null;
let activeTrack: 'all' | number = 'all';

// ── Utilities ─────────────────────────────────────────────────────────────────

function getStaffY(staffPos: number): number {
  // staffPos 0 = bottom staff line, increases upward; SVG y increases downward
  const bottomLineY = STAFF_Y + (STAFF_LINES - 1) * LINE_GAP;
  return bottomLineY - staffPos * LINE_GAP;
}

function noteStaffPos(note: ScoreNote, clef: string): number {
  const map = clef === 'bass' ? PITCH_TO_STAFF_BASS : PITCH_TO_STAFF_TREBLE;
  const naturalKey = note.pitch_name.replace('#', '').replace('b', '') + note.octave;
  const pos = map[naturalKey];
  return pos !== undefined ? pos : 4;
}

function drawStaffLines(numBars: number): { prefix: string; totalWidth: number } {
  const totalWidth = LEFT_MARGIN + numBars * BAR_WIDTH + 20;
  let svg = `<svg class="staff-svg" height="${STAFF_Y + (STAFF_LINES - 1) * LINE_GAP + 40}" width="${totalWidth}">`;
  for (let i = 0; i < STAFF_LINES; i++) {
    const y = STAFF_Y + i * LINE_GAP;
    svg += `<line class="staff-line" x1="${LEFT_MARGIN}" y1="${y}" x2="${totalWidth - 10}" y2="${y}"/>`;
  }
  for (let b = 0; b <= numBars; b++) {
    const x = LEFT_MARGIN + b * BAR_WIDTH;
    svg += `<line class="bar-line" x1="${x}" y1="${STAFF_Y}" x2="${x}" y2="${STAFF_Y + (STAFF_LINES - 1) * LINE_GAP}"/>`;
  }
  return { prefix: svg, totalWidth };
}

function drawClef(clef: string): string {
  const label = clef === 'bass' ? 'Bass' : 'Treble';
  return `<text class="clef-text" x="8" y="${STAFF_Y + (STAFF_LINES - 1) * LINE_GAP - 2}" font-size="11" fill="#8b949e" font-weight="600">${escHtml(label)}</text>`;
}

function drawTimeSig(timeSig: string, x: number): string {
  const [num, den] = timeSig.split('/');
  const midY = STAFF_Y + ((STAFF_LINES - 1) * LINE_GAP) / 2;
  return (
    `<text class="timesig-text" x="${x}" y="${midY - 4}" text-anchor="middle">${escHtml(num)}</text>` +
    `<text class="timesig-text" x="${x}" y="${midY + 12}" text-anchor="middle">${escHtml(den)}</text>`
  );
}

function drawNote(note: ScoreNote, clef: string, beatsPerBar: number): string {
  const bar = Math.floor(note.start_beat / beatsPerBar);
  const beatInBar = note.start_beat % beatsPerBar;
  const x = LEFT_MARGIN + bar * BAR_WIDTH + (beatInBar / beatsPerBar) * BAR_WIDTH + BAR_WIDTH * 0.1;
  const staffPos = noteStaffPos(note, clef);
  const y = getStaffY(staffPos);
  const midLine = STAFF_Y + 2 * LINE_GAP;
  const stemUp = y >= midLine;

  let result = '';

  // Ledger lines below staff
  if (staffPos < 0) {
    for (let lp = -2; lp >= staffPos; lp -= 2) {
      const ly = getStaffY(lp);
      result += `<line class="note-ledger" x1="${x - NOTE_RADIUS - 3}" y1="${ly}" x2="${x + NOTE_RADIUS + 3}" y2="${ly}"/>`;
    }
  } else if (staffPos > (STAFF_LINES - 1) * 2) {
    for (let lp = (STAFF_LINES - 1) * 2 + 2; lp <= staffPos; lp += 2) {
      const ly = getStaffY(lp);
      result += `<line class="note-ledger" x1="${x - NOTE_RADIUS - 3}" y1="${ly}" x2="${x + NOTE_RADIUS + 3}" y2="${ly}"/>`;
    }
  }

  const beats = DUR_BEATS[note.duration] ?? 1;
  const filled = beats < 2;
  if (filled) {
    result += `<ellipse class="note-head" cx="${x}" cy="${y}" rx="${NOTE_RADIUS}" ry="${NOTE_RADIUS - 1}"/>`;
  } else {
    result += `<ellipse cx="${x}" cy="${y}" rx="${NOTE_RADIUS}" ry="${NOTE_RADIUS - 1}" fill="none" stroke="#58a6ff" stroke-width="1.5"/>`;
  }

  if (beats < 4) {
    if (stemUp) {
      result += `<line class="note-stem" x1="${x + NOTE_RADIUS}" y1="${y}" x2="${x + NOTE_RADIUS}" y2="${y - STEM_LENGTH}"/>`;
    } else {
      result += `<line class="note-stem" x1="${x - NOTE_RADIUS}" y1="${y}" x2="${x - NOTE_RADIUS}" y2="${y + STEM_LENGTH}"/>`;
    }
  }

  if (beats === 0.5) {
    const sx = stemUp ? x + NOTE_RADIUS : x - NOTE_RADIUS;
    const sy = stemUp ? y - STEM_LENGTH : y + STEM_LENGTH;
    const fy = stemUp ? sy + 10 : sy - 10;
    result += `<path d="M${sx},${sy} Q${sx + 10},${(sy + fy) / 2} ${sx},${fy}" stroke="#58a6ff" stroke-width="1.5" fill="none"/>`;
  }

  if (note.pitch_name.includes('#')) {
    result += `<text x="${x - NOTE_RADIUS - 8}" y="${y + 4}" font-size="12" fill="#f0883e">#</text>`;
  } else if (note.pitch_name.includes('b')) {
    result += `<text x="${x - NOTE_RADIUS - 8}" y="${y + 4}" font-size="12" fill="#f0883e">b</text>`;
  }

  return result;
}

function renderTrackStaff(track: ScoreTrack): string {
  if (!track.notes || track.notes.length === 0) {
    return `<div class="score-empty">No notes in this track.</div>`;
  }

  const timeSig = notationData?.timeSig ?? '4/4';
  const beatsPerBar = parseInt(timeSig.split('/')[0], 10);
  const maxBeat = Math.max(...track.notes.map(n => n.start_beat)) + beatsPerBar;
  const numBars = Math.ceil(maxBeat / beatsPerBar);
  const clef = track.clef ?? 'treble';

  const { prefix } = drawStaffLines(numBars);
  let svg = prefix;
  svg += drawClef(clef);
  svg += drawTimeSig(timeSig, LEFT_MARGIN + 20);
  for (const note of track.notes) {
    svg += drawNote(note, clef, beatsPerBar);
  }
  svg += '</svg>';

  return `
    <div class="staff-container">
      <div class="staff-label">
        &#127929; ${escHtml(track.instrument ?? 'Track ' + track.track_id)}
        <span class="staff-clef-label">
          ${escHtml(clef)} clef &bull; ${escHtml(track.key_signature ?? '')}
        </span>
      </div>
      ${svg}
    </div>`;
}

// ── Track selector ─────────────────────────────────────────────────────────────
// Uses data-track attributes; event delegation wired in renderScore().

function renderTrackSelector(tracks: ScoreTrack[]): string {
  const allActive = activeTrack === 'all' ? ' active' : '';
  let html = `<button class="track-btn${allActive}" data-track="all">All Parts</button>`;
  tracks.forEach((t, i) => {
    const active = activeTrack === i ? ' active' : '';
    html += `<button class="track-btn${active}" data-track="${i}">`
      + escHtml(t.instrument ?? 'Track ' + i) + '</button>';
  });
  return html;
}

function setTrack(id: 'all' | number): void {
  activeTrack = id;
  renderScore();
}

// ── Main render ───────────────────────────────────────────────────────────────

function renderScore(): void {
  if (!notationData) return;

  const tracks = notationData.tracks ?? [];
  const visible = activeTrack === 'all'
    ? tracks
    : tracks.filter((_, i) => i === activeTrack);

  const selectorEl = document.getElementById('track-selector');
  if (selectorEl) {
    selectorEl.innerHTML = renderTrackSelector(tracks);
    selectorEl.querySelectorAll<HTMLElement>('[data-track]').forEach(btn => {
      btn.addEventListener('click', () => {
        const val = btn.dataset.track;
        setTrack(val === 'all' ? 'all' : parseInt(val!, 10));
      });
    });
  }

  const metaEl = document.getElementById('score-meta');
  if (metaEl) {
    metaEl.innerHTML = `
      <div class="score-meta-item">
        <span class="score-meta-label">Key</span>
        <span class="score-meta-value">${escHtml(notationData.key ?? '\u2014')}</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Tempo</span>
        <span class="score-meta-value">${notationData.tempo ?? '\u2014'} BPM</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Time</span>
        <span class="score-meta-value">${escHtml(notationData.timeSig ?? '\u2014')}</span>
      </div>
      <div class="score-meta-item">
        <span class="score-meta-label">Parts</span>
        <span class="score-meta-value">${tracks.length}</span>
      </div>`;
  }

  const stavesEl = document.getElementById('staves');
  if (stavesEl) {
    const staffHtml = visible.map(renderTrackStaff).join('');
    stavesEl.innerHTML = staffHtml || '<div class="score-empty">No tracks found.</div>';
  }
}

// ── Data fetch ────────────────────────────────────────────────────────────────

async function load(cfg: ScoreCfg): Promise<void> {
  initRepoNav(cfg.repoId);
  try {
    const notationUrl = '/repos/' + encodeURIComponent(cfg.repoId) + '/notation/' + encodeURIComponent(cfg.ref);
    let data: unknown = null;
    try {
      data = await apiFetch(notationUrl);
    } catch (_) {
      // Notation endpoint not yet available — fall through to stub
    }

    if (data && typeof data === 'object' && data !== null) {
      const d = data as Record<string, unknown>;
      notationData = (d['data'] ?? d) as NotationData;
    } else {
      // Minimal stub so the page renders without a live API
      notationData = {
        key: 'C major',
        tempo: 120,
        timeSig: '4/4',
        tracks: [{
          track_id: 0,
          clef: 'treble',
          key_signature: 'C major',
          time_signature: '4/4',
          instrument: 'piano',
          notes: [
            { pitch_name: 'C', octave: 4, duration: '1/4', start_beat: 0, velocity: 80, track_id: 0 },
            { pitch_name: 'E', octave: 4, duration: '1/4', start_beat: 1, velocity: 75, track_id: 0 },
            { pitch_name: 'G', octave: 4, duration: '1/4', start_beat: 2, velocity: 78, track_id: 0 },
            { pitch_name: 'E', octave: 4, duration: '1/4', start_beat: 3, velocity: 72, track_id: 0 },
          ],
        }],
      };
    }

    renderScore();
  } catch (e) {
    const err = e as Error;
    if (err.message !== 'auth') {
      const stavesEl = document.getElementById('staves');
      if (stavesEl) {
        stavesEl.innerHTML = '<p class="error">&#10005; Could not load notation: ' + escHtml(err.message) + '</p>';
      }
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initScore(): void {
  const cfg = window.__scoreCfg;
  if (!cfg) return;
  void load(cfg);
}
