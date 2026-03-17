/**
 * audio-player.ts — MuseHub advanced audio player component.
 *
 * Wraps the vendored WaveSurfer implementation
 * (/musehub/static/vendor/wavesurfer.min.js) to provide:
 *
 *   - Waveform visualization via canvas with seek-on-click
 *   - A/B loop region (Shift+drag on waveform, or programmatic)
 *   - Playback speed control: 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x
 *   - Time display: current MM:SS / total MM:SS
 *   - Volume slider
 *   - Keyboard shortcuts: Space=play/pause, L=clear loop, ArrowLeft/Right=seek 5s
 *
 * Usage:
 *   const player = AudioPlayer.init({
 *     waveformEl: document.getElementById('waveform'),
 *     playBtnEl:  document.getElementById('play-btn'),
 *     timeCurEl:  document.getElementById('time-cur'),
 *     timeDurEl:  document.getElementById('time-dur'),
 *     speedSelEl: document.getElementById('speed-sel'),
 *     loopBtnEl:  document.getElementById('loop-btn'),
 *     loopInfoEl: document.getElementById('loop-info'),
 *   });
 *   player.load(url, autoPlay);
 *
 * WaveSurfer must be loaded first via the vendor script tag.
 */

// WaveSurfer is loaded via /musehub/static/vendor/wavesurfer.min.js
declare const WaveSurfer: {
  create(opts: {
    container: HTMLElement;
    waveColor: string;
    progressColor: string;
    cursorColor: string;
    height: number;
    barWidth: number;
    barGap: number;
  }): WaveSurferInstance;
};

interface WaveSurferInstance {
  on(event: string, cb: (...args: unknown[]) => void): void;
  play(): void;
  pause(): void;
  playPause(): void;
  load(url: string): void;
  getDuration(): number;
  getCurrentTime(): number;
  seekTo(progress: number): void;
  setPlaybackRate(rate: number): void;
  setVolume(volume: number): void;
  clearRegion(): void;
  destroy(): void;
}

const SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

function fmtTime(secs: number): string {
  if (!isFinite(secs) || secs < 0) return '0:00';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return m + ':' + (s < 10 ? '0' : '') + s;
}

export interface AudioPlayerOpts {
  waveformEl: HTMLElement;
  playBtnEl?: HTMLButtonElement | null;
  timeCurEl?: HTMLElement | null;
  timeDurEl?: HTMLElement | null;
  speedSelEl?: HTMLSelectElement | null;
  loopBtnEl?: HTMLElement | null;
  loopInfoEl?: HTMLElement | null;
  volSliderEl?: HTMLInputElement | null;
}

export class AudioPlayer {
  private _ws: WaveSurferInstance | null = null;
  private _opts: AudioPlayerOpts;
  private _autoPlay = false;

  private constructor(opts: AudioPlayerOpts) {
    this._opts = opts;
  }

  static init(opts: AudioPlayerOpts): AudioPlayer {
    const player = new AudioPlayer(opts);
    player._setup();
    return player;
  }

  private _setup(): void {
    const self = this;
    const opts = this._opts;

    this._ws = WaveSurfer.create({
      container: opts.waveformEl,
      waveColor: '#4a5568',
      progressColor: '#1f6feb',
      cursorColor: '#58a6ff',
      height: 80,
      barWidth: 2,
      barGap: 1,
    });

    this._ws.on('ready', () => {
      const dur = self._ws!.getDuration();
      if (opts.timeDurEl) opts.timeDurEl.textContent = fmtTime(dur);
      if (opts.playBtnEl) opts.playBtnEl.disabled = false;
      if (self._autoPlay) {
        self._autoPlay = false;
        self._ws!.play();
      }
    });

    this._ws.on('play', () => {
      if (opts.playBtnEl) opts.playBtnEl.innerHTML = '&#9646;&#9646;';
    });

    this._ws.on('pause', () => {
      if (opts.playBtnEl) opts.playBtnEl.innerHTML = '&#9654;';
    });

    this._ws.on('finish', () => {
      if (opts.playBtnEl) opts.playBtnEl.innerHTML = '&#9654;';
    });

    this._ws.on('timeupdate', (t: unknown) => {
      if (opts.timeCurEl) opts.timeCurEl.textContent = fmtTime(t as number);
    });

    this._ws.on('region-update', (region: unknown) => {
      const r = region as { start: number; end: number };
      if (opts.loopInfoEl) {
        opts.loopInfoEl.textContent =
          'Loop: ' + fmtTime(r.start) + ' – ' + fmtTime(r.end);
        opts.loopInfoEl.style.display = '';
      }
      if (opts.loopBtnEl) opts.loopBtnEl.style.display = '';
    });

    this._ws.on('region-clear', () => {
      if (opts.loopInfoEl) opts.loopInfoEl.style.display = 'none';
      if (opts.loopBtnEl) opts.loopBtnEl.style.display = 'none';
    });

    this._ws.on('error', (msg: unknown) => {
      if (opts.waveformEl) {
        const errEl = document.createElement('p');
        errEl.style.cssText = 'color:#f85149;padding:16px;margin:0;';
        errEl.textContent = '\u274C Audio unavailable: ' + String(msg);
        opts.waveformEl.appendChild(errEl);
      }
    });

    if (opts.playBtnEl) {
      opts.playBtnEl.disabled = true;
      opts.playBtnEl.addEventListener('click', () => self._ws!.playPause());
    }

    if (opts.speedSelEl) {
      SPEEDS.forEach((s, idx) => {
        const opt = document.createElement('option');
        opt.value = String(s);
        opt.textContent = s + 'x';
        if (idx === 2) opt.selected = true;
        opts.speedSelEl!.appendChild(opt);
      });
      opts.speedSelEl.addEventListener('change', function (this: HTMLSelectElement) {
        self._ws!.setPlaybackRate(parseFloat(this.value));
      });
    }

    if (opts.loopBtnEl) {
      opts.loopBtnEl.style.display = 'none';
      opts.loopBtnEl.addEventListener('click', () => self._ws!.clearRegion());
    }

    if (opts.loopInfoEl) opts.loopInfoEl.style.display = 'none';

    if (opts.volSliderEl) {
      opts.volSliderEl.addEventListener('input', function (this: HTMLInputElement) {
        self._ws!.setVolume(parseFloat(this.value));
      });
    }

    document.addEventListener('keydown', (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName ?? '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        self._ws!.playPause();
      } else if (e.code === 'KeyL') {
        self._ws!.clearRegion();
      } else if (e.code === 'ArrowLeft') {
        const t = Math.max(0, self._ws!.getCurrentTime() - 5);
        const d = self._ws!.getDuration();
        if (d > 0) self._ws!.seekTo(t / d);
      } else if (e.code === 'ArrowRight') {
        const tc = self._ws!.getCurrentTime() + 5;
        const dc = self._ws!.getDuration();
        if (dc > 0) self._ws!.seekTo(Math.min(1, tc / dc));
      }
    });
  }

  load(url: string, autoPlay = false): void {
    this._autoPlay = autoPlay;
    if (this._opts.playBtnEl) this._opts.playBtnEl.disabled = true;
    if (this._opts.timeCurEl) this._opts.timeCurEl.textContent = '0:00';
    if (this._opts.timeDurEl) this._opts.timeDurEl.textContent = '0:00';
    this._ws!.load(url);
  }

  destroy(): void {
    if (this._ws) {
      this._ws.destroy();
      this._ws = null;
    }
  }
}

// Expose to global scope for page-level scripts
declare global {
  interface Window {
    AudioPlayer: typeof AudioPlayer;
  }
}
window.AudioPlayer = AudioPlayer;
