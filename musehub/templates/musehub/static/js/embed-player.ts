/**
 * embed-player.ts — Standalone embed audio player.
 *
 * Reads config from the #embed-data JSON element:
 *   { repoId, ref, trackUrl, trackName }
 *
 * Compiled separately to static/embed-player.js (not bundled with app.ts).
 */

interface EmbedData {
  repoId:    string;
  ref:       string;
  trackUrl:  string | null;
  trackName: string | null;
}

function fmtTime(s: number): string {
  if (!isFinite(s)) return '0:00';
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function init(): void {
  const dataEl = document.getElementById('embed-data');
  if (!dataEl) return;

  let cfg: EmbedData;
  try {
    cfg = JSON.parse(dataEl.textContent ?? '{}') as EmbedData;
  } catch {
    return;
  }

  const audio      = document.getElementById('audio-el')       as HTMLAudioElement   | null;
  const playBtn    = document.getElementById('play-btn')        as HTMLButtonElement  | null;
  const fill       = document.getElementById('progress-fill')   as HTMLElement        | null;
  const bar        = document.getElementById('progress-bar')    as HTMLElement        | null;
  const timeCur    = document.getElementById('time-cur')        as HTMLElement        | null;
  const timeDur    = document.getElementById('time-dur')        as HTMLElement        | null;
  const trackTitle = document.getElementById('track-title')     as HTMLElement        | null;
  const trackSub   = document.getElementById('track-sub')       as HTMLElement        | null;

  if (!audio) return;

  function setStatus(msg: string, isError: boolean): void {
    if (trackTitle) {
      trackTitle.textContent = isError ? msg : (trackTitle.textContent || msg);
      if (isError) trackTitle.classList.add('error');
    }
  }

  audio.addEventListener('timeupdate', () => {
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    if (fill) fill.style.width = pct + '%';
    if (timeCur) timeCur.textContent = fmtTime(audio.currentTime);
  });

  audio.addEventListener('durationchange', () => {
    if (timeDur) timeDur.textContent = fmtTime(audio.duration);
  });

  audio.addEventListener('ended', () => {
    if (playBtn) playBtn.innerHTML = '&#9654;';
    if (fill) fill.style.width = '0%';
    audio.currentTime = 0;
  });

  audio.addEventListener('canplay', () => {
    if (playBtn) playBtn.disabled = false;
  });

  audio.addEventListener('error', () => { setStatus('Audio unavailable', true); });

  if (playBtn) {
    playBtn.addEventListener('click', () => {
      if (audio.paused) {
        void audio.play();
        playBtn.innerHTML = '&#9646;&#9646;';
      } else {
        audio.pause();
        playBtn.innerHTML = '&#9654;';
      }
    });
  }

  if (bar) {
    bar.addEventListener('click', (e: MouseEvent) => {
      if (!audio.duration) return;
      const rect = bar.getBoundingClientRect();
      const pct  = (e.clientX - rect.left) / rect.width;
      audio.currentTime = pct * audio.duration;
    });
  }

  async function loadTrack(): Promise<void> {
    if (cfg.trackUrl && cfg.trackName) {
      if (trackTitle) trackTitle.textContent = cfg.trackName;
      if (trackSub) trackSub.textContent = 'ref: ' + cfg.ref.substring(0, 8);
      audio.src = cfg.trackUrl;
      audio.load();
      return;
    }

    try {
      const objRes = await fetch('/api/v1/musehub/repos/' + cfg.repoId + '/objects');
      if (!objRes.ok) throw new Error('objects ' + objRes.status);
      const objData = (await objRes.json()) as { objects?: Array<{ path: string; objectId: string }> };
      const objects = objData.objects ?? [];

      const AUDIO_EXTS = new Set(['mp3', 'ogg', 'wav', 'm4a']);
      const audioObj = objects.find(o => {
        const ext = o.path.split('.').pop()?.toLowerCase() ?? '';
        return AUDIO_EXTS.has(ext);
      });

      if (!audioObj) {
        if (trackTitle) trackTitle.textContent = 'No audio in this commit';
        if (trackSub) trackSub.textContent = 'ref: ' + cfg.ref.substring(0, 8);
        return;
      }

      const name = audioObj.path.split('/').pop() ?? audioObj.path;
      if (trackTitle) trackTitle.textContent = name;
      if (trackSub) trackSub.textContent = 'ref: ' + cfg.ref.substring(0, 8);

      const audioUrl = '/api/v1/musehub/repos/' + cfg.repoId + '/objects/' + audioObj.objectId + '/content';
      audio.src = audioUrl;
      audio.load();
    } catch (e: unknown) {
      const err = e as { message?: string };
      setStatus('Could not load track', true);
      if (trackSub) trackSub.textContent = String(err.message ?? e);
    }
  }

  void loadTrack();
}

document.addEventListener('DOMContentLoaded', init);
