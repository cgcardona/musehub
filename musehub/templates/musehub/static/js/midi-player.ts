/**
 * midi-player.ts — Tone.js powered MIDI playback for MuseHub.
 *
 * Converts a MidiParseResult (from /objects/{id}/parse-midi) into a scheduled
 * Tone.js sequence.  Drives the piano roll playhead and transport controls.
 *
 * Tone.js (v14) is loaded via <script> tag on the host page and exposed as
 * the global `Tone`. No ES-module import is needed here; we use `declare`.
 *
 * Architecture:
 *   - One PolySynth per logical MIDI track (colour-coded, matches piano roll)
 *   - Percussion tracks (ch 9) use a MembraneSynth + MetalSynth duo
 *   - Tone.Transport drives timing; Tone.Draw syncs the playhead to rAF
 *   - Caller registers an onProgress(beatPosition) callback; the piano roll
 *     canvas draws a red playhead line at that beat position
 *
 * Public API:
 *   const player = new MidiPlayer(midiData, { onProgress, onEnd, bpmOverride });
 *   await player.play();
 *   player.pause();
 *   player.stop();
 *   player.seek(beatPosition);
 *   player.dispose();
 */

// ---------------------------------------------------------------------------
// Tone.js global — declared but loaded by the host page via CDN <script>
// ---------------------------------------------------------------------------
declare const Tone: {
  start(): Promise<void>;
  now(): number;
  Transport: {
    bpm: { value: number };
    seconds: number;
    state: string;
    start(time?: number): void;
    pause(): void;
    stop(): void;
    cancel(time?: number): void;
    schedule(cb: (time: number) => void, time: number | string): number;
    scheduleRepeat(cb: (time: number) => void, interval: string, startTime?: number | string): number;
    clear(id: number): void;
    position: string;
  };
  Draw: {
    schedule(cb: () => void, time: number): void;
  };
  PolySynth: new (synth: unknown, opts?: unknown) => ToneSynth;
  Synth: unknown;
  MembraneSynth: new (opts?: unknown) => ToneSynth;
  MetalSynth: new (opts?: unknown) => ToneSynth;
  Gain: new (vol: number) => ToneNode;
  getDestination(): ToneNode;
};

interface ToneSynth {
  triggerAttackRelease(note: string | number, duration: string | number, time?: number, velocity?: number): void;
  triggerAttack(note: string | number, time?: number, velocity?: number): void;
  triggerRelease(note: string | number, time?: number): void;
  connect(dest: ToneNode): this;
  disconnect(): this;
  dispose(): void;
  volume: { value: number };
}

interface ToneNode {
  connect(dest: ToneNode): this;
  toDestination(): this;
  dispose(): void;
}

// ---------------------------------------------------------------------------
// MIDI data types (mirrors piano-roll.ts)
// ---------------------------------------------------------------------------

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
  channel: number;
  name?: string;
  notes?: MidiNote[];
}

export interface MidiParseResult {
  tracks?: MidiTrack[];
  tempo_bpm?: number;
  time_signature?: string;
  total_beats?: number;
}

// ---------------------------------------------------------------------------
// Player options
// ---------------------------------------------------------------------------

export interface MidiPlayerOptions {
  /** Called on each animation frame with the current beat position (0-based). */
  onProgress?: (beat: number) => void;
  /** Called when playback reaches the end of the piece. */
  onEnd?: () => void;
  /** Override the file tempo. Defaults to midi.tempo_bpm. */
  bpmOverride?: number;
}

// ---------------------------------------------------------------------------
// Pitch helpers
// ---------------------------------------------------------------------------

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;

function midiToTone(pitch: number): string {
  // Tone.js uses scientific pitch: C4 = middle C (MIDI 60)
  const octave = Math.floor(pitch / 12) - 1;
  return NOTE_NAMES[pitch % 12] + octave;
}

function beatsToSeconds(beats: number, bpm: number): number {
  return (beats * 60) / bpm;
}

// ---------------------------------------------------------------------------
// Percussion mapping (GM channel 10 / index 9)
// ---------------------------------------------------------------------------

const PERC_NOTES: Record<number, { type: 'kick' | 'snare' | 'hat' | 'clap'; note: string }> = {
  35: { type: 'kick',  note: 'C1' },
  36: { type: 'kick',  note: 'C1' },
  38: { type: 'snare', note: 'E1' },
  40: { type: 'snare', note: 'E1' },
  42: { type: 'hat',   note: 'F#1' },
  44: { type: 'hat',   note: 'F#1' },
  46: { type: 'hat',   note: 'G#1' },
  49: { type: 'clap',  note: 'A1' },
  51: { type: 'hat',   note: 'A#1' },
};

// ---------------------------------------------------------------------------
// MidiPlayer
// ---------------------------------------------------------------------------

type PlayerState = 'stopped' | 'playing' | 'paused';

export class MidiPlayer {
  private readonly midi: MidiParseResult;
  private readonly opts: MidiPlayerOptions;
  private readonly bpm: number;
  private readonly totalBeats: number;

  private state: PlayerState = 'stopped';
  private synths: Map<number, ToneSynth> = new Map();
  private masterGain: ToneNode | null = null;
  private scheduledIds: number[] = [];
  private tickerId: number | null = null;
  private pausedAt = 0; // Transport.seconds when paused

  constructor(midi: MidiParseResult, opts: MidiPlayerOptions = {}) {
    this.midi = midi;
    this.opts = opts;
    this.bpm = opts.bpmOverride ?? midi.tempo_bpm ?? 120;
    this.totalBeats = midi.total_beats ?? 0;
  }

  // ── Public transport API ─────────────────────────────────────────────────

  async play(): Promise<void> {
    if (this.state === 'playing') return;

    // Tone context must be resumed from a user gesture
    await Tone.start();

    if (this.state === 'stopped') {
      this._buildSynths();
      this._scheduleNotes();
      this._startTicker();
      Tone.Transport.bpm.value = this.bpm;
      Tone.Transport.start();
    } else {
      // Resume from pause
      Tone.Transport.start();
    }

    this.state = 'playing';
  }

  pause(): void {
    if (this.state !== 'playing') return;
    this.pausedAt = Tone.Transport.seconds;
    Tone.Transport.pause();
    this.state = 'paused';
  }

  stop(): void {
    this._cleanup();
    this.state = 'stopped';
    this.pausedAt = 0;
    this.opts.onProgress?.(0);
  }

  seek(beat: number): void {
    const wasPlaying = this.state === 'playing';
    if (wasPlaying) Tone.Transport.pause();

    // Re-schedule from the new position
    this._cancelScheduled();
    Tone.Transport.seconds = beatsToSeconds(beat, this.bpm);
    this._scheduleNotes(beat);

    if (wasPlaying) Tone.Transport.start();
  }

  /** Permanently release all Tone.js resources. */
  dispose(): void {
    this._cleanup();
    this.synths.forEach(s => s.dispose());
    this.synths.clear();
    this.masterGain?.dispose();
    this.masterGain = null;
  }

  get isPlaying(): boolean { return this.state === 'playing'; }
  get isPaused(): boolean  { return this.state === 'paused'; }
  get currentBeat(): number {
    return (Tone.Transport.seconds * this.bpm) / 60;
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private _buildSynths(): void {
    if (this.synths.size > 0) return;

    const tracks = this.midi.tracks ?? [];
    const dest = Tone.getDestination();

    tracks.forEach(track => {
      const isPerc = track.channel === 9;
      let synth: ToneSynth;

      if (isPerc) {
        synth = new Tone.MembraneSynth({
          pitchDecay: 0.05,
          octaves: 4,
          envelope: { attack: 0.001, decay: 0.2, sustain: 0, release: 0.2 },
        });
      } else {
        // Piano-style attack with soft release
        synth = new Tone.PolySynth(Tone.Synth, {
          oscillator: { type: 'triangle8' },
          envelope: { attack: 0.01, decay: 0.3, sustain: 0.45, release: 1.8 },
        });
      }

      synth.volume.value = isPerc ? -14 : -18;
      synth.connect(dest as ToneNode);
      this.synths.set(track.track_id, synth);
    });
  }

  private _scheduleNotes(fromBeat = 0): void {
    const tracks = this.midi.tracks ?? [];
    const bpm = this.bpm;
    const totalBeats = this.totalBeats;
    const origin = Tone.now();

    tracks.forEach(track => {
      const synth = this.synths.get(track.track_id);
      if (!synth) return;

      const notes = (track.notes ?? []).filter(n => n.start_beat >= fromBeat);
      const isPerc = track.channel === 9;

      notes.forEach(n => {
        const startSec = beatsToSeconds(n.start_beat - fromBeat, bpm) + origin + 0.05;
        const durSec   = Math.max(beatsToSeconds(n.duration_beats, bpm), 0.02);
        const vel      = Math.max(0.01, Math.min(1, n.velocity / 127));

        const id = Tone.Transport.schedule((time: number) => {
          if (isPerc) {
            const perc = PERC_NOTES[n.pitch] ?? { note: 'C1' };
            synth.triggerAttackRelease(perc.note, '16n', time, vel);
          } else {
            const note = midiToTone(n.pitch);
            synth.triggerAttackRelease(note, durSec, time, vel);
          }
        }, startSec);

        this.scheduledIds.push(id);
      });
    });

    // Schedule "end of piece" callback
    if (totalBeats > fromBeat) {
      const endSec = beatsToSeconds(totalBeats - fromBeat, bpm) + origin + 0.1;
      const endId = Tone.Transport.schedule((_time: number) => {
        Tone.Draw.schedule(() => {
          this.stop();
          this.opts.onEnd?.();
        }, Tone.now());
      }, endSec);
      this.scheduledIds.push(endId);
    }
  }

  private _startTicker(): void {
    const bpm = this.bpm;
    const onProgress = this.opts.onProgress;
    if (!onProgress) return;

    const id = Tone.Transport.scheduleRepeat((time: number) => {
      const beat = (Tone.Transport.seconds * bpm) / 60;
      Tone.Draw.schedule(() => onProgress(beat), time);
    }, '16n');

    this.tickerId = id;
  }

  private _cancelScheduled(): void {
    this.scheduledIds.forEach(id => Tone.Transport.clear(id));
    this.scheduledIds = [];
    if (this.tickerId !== null) {
      Tone.Transport.clear(this.tickerId);
      this.tickerId = null;
    }
  }

  private _cleanup(): void {
    this._cancelScheduled();
    Tone.Transport.stop();
    Tone.Transport.cancel();
  }
}

// ---------------------------------------------------------------------------
// Playhead overlay helper — draws a red line on the piano roll canvas
// ---------------------------------------------------------------------------

export interface PlayheadOptions {
  canvas: HTMLCanvasElement;
  outerEl: HTMLElement;
  totalBeats: number;
  zoomX: number;
  panX: number;
  keyWidth: number;
}

/**
 * Draw (or erase) a translucent red playhead line at the given beat position.
 * Called from the MidiPlayer.onProgress callback on every animation frame.
 */
export function drawPlayhead(
  beat: number,
  ctx: CanvasRenderingContext2D,
  opts: PlayheadOptions,
): void {
  const { canvas, outerEl, panX, zoomX, keyWidth } = opts;
  const dpr = window.devicePixelRatio || 1;
  const w = outerEl.clientWidth;
  const h = canvas.height / dpr;

  const x = keyWidth + (beat - panX) * zoomX;
  if (x < keyWidth || x > w) return;

  ctx.save();
  ctx.globalAlpha = 0.85;
  ctx.strokeStyle = '#f85149'; // --dim-e red
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, h);
  ctx.stroke();
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Factory — resolves the MidiParseResult from the page canvas attributes
// then constructs and returns a ready MidiPlayer
// ---------------------------------------------------------------------------

export async function createPlayerFromCanvas(
  canvas: HTMLCanvasElement,
  opts: Omit<MidiPlayerOptions, 'onProgress'> & {
    onProgress?: (beat: number) => void;
  },
): Promise<MidiPlayer | null> {
  const midiUrl = canvas.dataset.midiUrl;
  if (!midiUrl) return null;

  try {
    const res = await fetch(midiUrl, { credentials: 'include' });
    if (!res.ok) return null;
    const midi = (await res.json()) as MidiParseResult;
    return new MidiPlayer(midi, opts);
  } catch {
    return null;
  }
}

// Expose to window for page-level scripts that import via bundled app.js
declare global {
  interface Window {
    MidiPlayer: typeof MidiPlayer;
    createPlayerFromCanvas: typeof createPlayerFromCanvas;
  }
}

window.MidiPlayer = MidiPlayer;
window.createPlayerFromCanvas = createPlayerFromCanvas;
