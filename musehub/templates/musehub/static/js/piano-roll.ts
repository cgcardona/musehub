/**
 * piano-roll.ts — Canvas-based MIDI piano roll renderer for MuseHub.
 *
 * Renders a MidiParseResult (from /objects/{id}/parse-midi) into an interactive
 * piano roll.  Features:
 *   - Piano keyboard on the left Y-axis (pitch labels)
 *   - Beat grid on the X-axis with configurable beat-line density
 *   - Per-track colour coding using the MuseHub design token palette
 *   - Velocity mapped to rectangle opacity (soft notes appear lighter)
 *   - Zoom: horizontal (beats per screen) and vertical (pixels per pitch row)
 *   - Pan: click-drag on the canvas
 *   - Hover tooltip: pitch name, velocity, beat position, duration
 *
 * Usage:
 *   PianoRoll.render(midiParseResult, containerElement, options);
 *
 * Options:
 *   selectedTrack  {number}  -1 = all tracks, 0+ = single track index
 */

// Design system track colours — mirrors CSS --track-N custom properties
const TRACK_COLORS: readonly string[] = [
  '#58a6ff', // blue
  '#3fb950', // green
  '#f0883e', // orange
  '#bc8cff', // purple
  '#ff7b72', // red
  '#79c0ff', // light blue
  '#56d364', // light green
  '#ffa657', // light orange
  '#d2a8ff', // light purple
  '#ffa198', // light red
];

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

function pitchToName(pitch: number): string {
  const octave = Math.floor(pitch / 12) - 1;
  return NOTE_NAMES[pitch % 12] + octave;
}

function isBlackKey(pitch: number): boolean {
  const pc = pitch % 12;
  return pc === 1 || pc === 3 || pc === 6 || pc === 8 || pc === 10;
}

const KEY_WIDTH = 36;
const MIN_PITCH = 21;  // A0
const MAX_PITCH = 108; // C8

export interface MidiNote {
  pitch: number;
  start_beat: number;
  duration_beats: number;
  velocity: number;
  track_id: number;
  channel: number;
}

export interface MidiTrack {
  track_id: number;
  name?: string;
  notes?: MidiNote[];
}

export interface MidiParseResult {
  tracks?: MidiTrack[];
  tempo_bpm?: number;
  time_signature?: string;
  total_beats?: number;
}

export interface PianoRollOptions {
  selectedTrack?: number;
}

function escHtml(s: unknown): string {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function render(
  midi: MidiParseResult,
  container: HTMLElement,
  opts: PianoRollOptions = {},
): void {
  const tracks = midi.tracks ?? [];
  const tempoBpm = midi.tempo_bpm ?? 120;
  const timeSig = midi.time_signature ?? '4/4';
  const totalBeats = midi.total_beats ?? 0;
  let selectedTrack = opts.selectedTrack ?? -1;

  let allNotes: MidiNote[] = [];
  tracks.forEach(t => {
    if (selectedTrack === -1 || t.track_id === selectedTrack) {
      (t.notes ?? []).forEach(n => allNotes.push(n));
    }
  });

  if (allNotes.length === 0) {
    container.innerHTML =
      '<p style="color:var(--text-muted);padding:16px;">No MIDI notes found.</p>';
    return;
  }

  let pitchMin = Math.max(
    MIN_PITCH,
    allNotes.reduce((m, n) => Math.min(m, n.pitch), 127) - 2,
  );
  let pitchMax = Math.min(
    MAX_PITCH,
    allNotes.reduce((m, n) => Math.max(m, n.pitch), 0) + 2,
  );
  let pitchRange = pitchMax - pitchMin + 1;

  container.innerHTML = pianoRollHtml(midi, tracks, selectedTrack, totalBeats, tempoBpm, timeSig);

  const outerEl = container.querySelector<HTMLElement>('#piano-roll-outer');
  const canvasEl = container.querySelector<HTMLCanvasElement>('#piano-canvas');
  const tooltip = document.querySelector<HTMLElement>('.piano-roll-tooltip');

  if (!outerEl || !canvasEl) return;

  // Non-null after the guard above
  const outer: HTMLElement = outerEl;
  const canvas: HTMLCanvasElement = canvasEl;

  let zoomX = 60;
  let zoomY = 14;
  let panX = 0;
  let panY = 0;
  let isPanning = false;
  let lastMouseX = 0;
  let lastMouseY = 0;
  const dpr = window.devicePixelRatio || 1;

  function outerW(): number { return outer.clientWidth || 800; }
  function outerH(): number { return Math.min(Math.max(pitchRange * zoomY + 40, 200), 600); }

  function resize(): void {
    const w = outerW();
    const h = outerH();
    outer.style.height = h + 'px';
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
  }

  function pitchToY(pitch: number, h: number): number {
    const row = (pitchMax - pitch) - panY;
    return 20 + row * zoomY;
  }

  function beatToX(beat: number, rollW: number): number {
    return KEY_WIDTH + (beat - panX) * zoomX;
  }

  function draw(): void {
    const w = outerW();
    const h = outerH();
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const rollW = w - KEY_WIDTH;

    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, w, h);

    for (let p = pitchMin; p <= pitchMax; p++) {
      const y = pitchToY(p, h);
      ctx.fillStyle = isBlackKey(p) ? '#131820' : '#0d1117';
      ctx.fillRect(KEY_WIDTH, y, rollW, zoomY);
      if (p % 12 === 0) {
        ctx.fillStyle = '#1f2937';
        ctx.fillRect(KEY_WIDTH, y, rollW, 1);
      }
    }

    const beatsPerScreen = rollW / zoomX;
    const beatStart = Math.floor(panX);
    const beatEnd = Math.ceil(panX + beatsPerScreen + 1);
    const beatStep = zoomX < 8 ? 8 : zoomX < 20 ? 4 : zoomX < 40 ? 2 : 1;

    for (let b = beatStart; b <= beatEnd; b += beatStep) {
      const bx = beatToX(b, rollW);
      const isMeasure = b % 4 === 0;
      ctx.strokeStyle = isMeasure ? '#30363d' : '#1a2030';
      ctx.lineWidth = isMeasure ? 1 : 0.5;
      ctx.beginPath();
      ctx.moveTo(bx, 20);
      ctx.lineTo(bx, h);
      ctx.stroke();
      if (isMeasure && bx >= KEY_WIDTH) {
        ctx.fillStyle = '#8b949e';
        ctx.font = '9px monospace';
        ctx.fillText(String(b), bx + 2, 14);
      }
    }

    allNotes.forEach(n => {
      const x1 = beatToX(n.start_beat, rollW);
      const x2 = beatToX(n.start_beat + n.duration_beats, rollW);
      const ny = pitchToY(n.pitch, h);
      const nw = Math.max(x2 - x1 - 1, 2);
      const nh = Math.max(zoomY - 1, 3);
      if (x2 < KEY_WIDTH || x1 > w) return;

      const trackColor = TRACK_COLORS[n.track_id % TRACK_COLORS.length];
      const alpha = 0.4 + (n.velocity / 127) * 0.6;

      ctx.globalAlpha = alpha;
      ctx.fillStyle = trackColor;
      ctx.fillRect(Math.max(x1, KEY_WIDTH), ny + 1, nw, nh);

      ctx.globalAlpha = alpha * 0.8;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(Math.max(x1, KEY_WIDTH), ny + 1, nw, 1);

      ctx.globalAlpha = 1;
    });

    for (let pk = pitchMin; pk <= pitchMax; pk++) {
      const pky = pitchToY(pk, h);
      const black = isBlackKey(pk);
      ctx.fillStyle = black ? '#1a1a1a' : '#e6edf3';
      ctx.fillRect(0, pky + 1, black ? KEY_WIDTH * 0.65 : KEY_WIDTH - 1, Math.max(zoomY - 1, 2));
      if (!black && pk % 12 === 0) {
        ctx.fillStyle = '#58a6ff';
        ctx.font = '9px monospace';
        ctx.fillText(pitchToName(pk), 2, pky + zoomY - 2);
      }
    }

    ctx.fillStyle = '#161b22';
    ctx.fillRect(KEY_WIDTH, 0, rollW, 20);
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, KEY_WIDTH, 20);

    ctx.fillStyle = '#8b949e';
    ctx.font = '10px monospace';
    ctx.fillText(tempoBpm.toFixed(1) + ' BPM  ' + timeSig, KEY_WIDTH + 6, 13);
  }

  const zoomXInput = container.querySelector<HTMLInputElement>('#zoom-x');
  const zoomYInput = container.querySelector<HTMLInputElement>('#zoom-y');
  const trackSel = container.querySelector<HTMLSelectElement>('#track-sel');

  zoomXInput?.addEventListener('input', function (this: HTMLInputElement) {
    zoomX = parseInt(this.value, 10); resize(); draw();
  });
  zoomYInput?.addEventListener('input', function (this: HTMLInputElement) {
    zoomY = parseInt(this.value, 10); resize(); draw();
  });
  trackSel?.addEventListener('change', function (this: HTMLSelectElement) {
    selectedTrack = parseInt(this.value, 10);
    allNotes = [];
    tracks.forEach(t => {
      if (selectedTrack === -1 || t.track_id === selectedTrack) {
        (t.notes ?? []).forEach(n => allNotes.push(n));
      }
    });
    if (allNotes.length > 0) {
      pitchMin = Math.max(MIN_PITCH, allNotes.reduce((m, n) => Math.min(m, n.pitch), 127) - 2);
      pitchMax = Math.min(MAX_PITCH, allNotes.reduce((m, n) => Math.max(m, n.pitch), 0) + 2);
      pitchRange = pitchMax - pitchMin + 1;
    }
    resize(); draw();
  });

  canvas.addEventListener('mousedown', (e: MouseEvent) => {
    isPanning = true;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    outer.classList.add('panning');
  });

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (isPanning) {
      const dx = e.clientX - lastMouseX;
      const dy = e.clientY - lastMouseY;
      panX = Math.max(0, panX - dx / zoomX);
      panY = Math.max(0, panY - dy / zoomY);
      lastMouseX = e.clientX;
      lastMouseY = e.clientY;
      draw();
    } else {
      showTooltip(e);
    }
  });

  window.addEventListener('mouseup', () => {
    isPanning = false;
    outer.classList.remove('panning');
  });

  canvas.addEventListener('mouseleave', () => {
    if (tooltip) tooltip.style.display = 'none';
  });

  function showTooltip(e: MouseEvent): void {
    if (!tooltip) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (mx < KEY_WIDTH || my < 20) { tooltip.style.display = 'none'; return; }

    const beat = panX + (mx - KEY_WIDTH) / zoomX;
    const pitch = pitchMax - Math.floor((my - 20) / zoomY) - Math.round(panY);

    const hit = allNotes.find(
      n => n.pitch === pitch && n.start_beat <= beat && n.start_beat + n.duration_beats >= beat,
    );

    if (!hit) { tooltip.style.display = 'none'; return; }

    tooltip.innerHTML =
      '<strong>' + pitchToName(hit.pitch) + '</strong> (MIDI ' + hit.pitch + ')<br>' +
      'Beat: ' + hit.start_beat.toFixed(2) + '<br>' +
      'Duration: ' + hit.duration_beats.toFixed(2) + ' beats<br>' +
      'Velocity: ' + hit.velocity + '<br>' +
      'Track: ' + hit.track_id + ' / Ch ' + hit.channel;
    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top = (e.clientY - 10) + 'px';
  }

  window.addEventListener('resize', () => { resize(); draw(); });

  resize();
  draw();
}

function pianoRollHtml(
  _midi: MidiParseResult,
  tracks: MidiTrack[],
  selectedTrack: number,
  totalBeats: number,
  tempoBpm: number,
  timeSig: string,
): string {
  const trackOpts =
    '<option value="-1">All tracks</option>' +
    tracks
      .map(t => {
        const sel = t.track_id === selectedTrack ? ' selected' : '';
        return (
          '<option value="' +
          t.track_id +
          '"' +
          sel +
          '>' +
          escHtml(t.name ?? 'Track ' + t.track_id) +
          ' (' +
          (t.notes ?? []).length +
          ' notes)</option>'
        );
      })
      .join('');

  const legendItems = tracks
    .map(t => {
      const color = TRACK_COLORS[t.track_id % TRACK_COLORS.length];
      return (
        '<div class="track-legend-item">' +
        '<div class="track-legend-swatch" style="background:' +
        color +
        '"></div>' +
        escHtml(t.name ?? 'Track ' + t.track_id) +
        '</div>'
      );
    })
    .join('');

  return (
    '<div class="piano-roll-wrapper">' +
    '<div class="piano-roll-controls">' +
    '<label>Track: <select id="track-sel">' +
    trackOpts +
    '</select></label>' +
    '<label>H-Zoom: <input type="range" id="zoom-x" min="4" max="200" value="60" style="width:80px"></label>' +
    '<label>V-Zoom: <input type="range" id="zoom-y" min="4" max="40" value="14" style="width:60px"></label>' +
    '<span style="font-size:12px;color:#8b949e;margin-left:auto">' +
    totalBeats.toFixed(1) +
    ' beats &bull; ' +
    tempoBpm.toFixed(1) +
    ' BPM &bull; ' +
    escHtml(timeSig) +
    '</span>' +
    '</div>' +
    '<div id="piano-roll-outer"><canvas id="piano-canvas"></canvas></div>' +
    '<div class="track-legend">' +
    legendItems +
    '</div>' +
    '</div>'
  );
}

export const PianoRoll = { render };

// Expose to global scope for page-level scripts
declare global {
  interface Window {
    PianoRoll: typeof PianoRoll;
  }
}
window.PianoRoll = PianoRoll;
