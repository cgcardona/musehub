/**
 * listen.ts — MuseHub listen page module.
 *
 * Renders the track list and audio player for a repo's audio renders.
 * All data is fetched from the JSON API; the server only renders the
 * loading skeleton and injects the page data JSON.
 *
 * Data expected in #page-data:
 *   { "page": "listen", "repo_id": "...", "ref": "main", "api_base": "..." }
 *
 * Registered as: window.MusePages['listen']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

export interface ListenPageData extends RepoPageData {
  ref?: string;
  api_base?: string;
}

interface TrackInfo {
  name: string;
  path: string;
  url: string;
  size?: number;
  durationSec?: number;
  objectId?: string;
}

interface ListingResponse {
  hasRenders: boolean;
  tracks: TrackInfo[];
  fullMixUrl: string | null;
  ref: string;
  repoId: string;
}

let mixAudio: HTMLAudioElement | null = null;
const trackAudios: Record<string, HTMLAudioElement> = {};

function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m + ':' + (sec < 10 ? '0' : '') + sec;
}

function fmtBytes(n: number): string {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(0) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}

function miniWaveform(objectId: string, _isPlaying: boolean): string {
  const seed = objectId ? objectId.charCodeAt(objectId.length - 1) : 0;
  const heights: number[] = [];
  for (let i = 0; i < 16; i++) {
    heights.push(Math.round(20 + Math.abs(Math.sin((seed + i * 7) * 0.8)) * 45));
  }
  return heights.map((h) => `<div class="track-waveform-bar" style="height:${h}%"></div>`).join('');
}

function pauseAllTracks(): void {
  Object.values(trackAudios).forEach((a) => { if (!a.paused) a.pause(); });
  document.querySelectorAll('.track-play-btn').forEach((b) => {
    (b as HTMLElement).innerHTML = '&#9654;';
    (b as HTMLElement).classList.remove('is-playing');
  });
  document.querySelectorAll('.track-row').forEach((r) => r.classList.remove('is-playing'));
}

function renderMixPlayer(url: string, _title: string): string {
  return `
  <div class="listen-player-card">
    <div class="listen-player-title">Full Mix</div>
    <div class="listen-player-sub">Master render — all tracks combined</div>
    <div class="listen-controls">
      <button id="mix-play-btn" class="listen-play-btn" disabled title="Play / Pause">&#9654;</button>
      <div class="listen-progress-wrap">
        <div id="mix-progress-bar" class="listen-progress-bar">
          <div id="mix-progress-fill" class="listen-progress-fill"></div>
        </div>
        <div class="listen-time-row">
          <span id="mix-time-cur">0:00</span>
          <span id="mix-time-dur">—</span>
        </div>
      </div>
    </div>
    <div class="listen-actions">
      <a href="${url}" download class="btn btn-secondary btn-sm">&#8595; Download</a>
    </div>
  </div>`;
}

function initMixPlayer(url: string): void {
  mixAudio = new Audio();
  mixAudio.preload = 'metadata';
  const playBtn = document.getElementById('mix-play-btn') as HTMLButtonElement | null;
  const fill    = document.getElementById('mix-progress-fill') as HTMLElement | null;
  const bar     = document.getElementById('mix-progress-bar') as HTMLElement | null;
  const timeCur = document.getElementById('mix-time-cur') as HTMLElement | null;
  const timeDur = document.getElementById('mix-time-dur') as HTMLElement | null;
  if (!playBtn) return;

  mixAudio.addEventListener('canplay', () => { playBtn.disabled = false; });
  mixAudio.addEventListener('timeupdate', () => {
    const pct = mixAudio!.duration ? (mixAudio!.currentTime / mixAudio!.duration) * 100 : 0;
    if (fill) fill.style.width = pct + '%';
    if (timeCur) timeCur.textContent = fmtTime(mixAudio!.currentTime);
  });
  mixAudio.addEventListener('durationchange', () => { if (timeDur) timeDur.textContent = fmtTime(mixAudio!.duration); });
  mixAudio.addEventListener('ended', () => { playBtn.innerHTML = '&#9654;'; if (fill) fill.style.width = '0%'; mixAudio!.currentTime = 0; });
  mixAudio.addEventListener('error', () => { playBtn.disabled = true; playBtn.title = 'Audio unavailable'; });

  playBtn.addEventListener('click', () => {
    pauseAllTracks();
    if (mixAudio!.paused) {
      mixAudio!.src = url; mixAudio!.play();
      playBtn.innerHTML = '&#9646;&#9646;';
    } else { mixAudio!.pause(); playBtn.innerHTML = '&#9654;'; }
  });

  if (bar) {
    bar.addEventListener('click', (e) => {
      if (!mixAudio!.duration) return;
      const rect = bar.getBoundingClientRect();
      mixAudio!.currentTime = ((e.clientX - rect.left) / rect.width) * mixAudio!.duration;
    });
  }
}

function renderTrackList(tracks: TrackInfo[]): string {
  return tracks.map((t) => {
    const safeId = CSS.escape(t.path);
    const dur    = t.durationSec ? fmtTime(t.durationSec) : '—';
    const size   = t.size ? fmtBytes(t.size) : '';
    const waveHtml = miniWaveform(t.objectId ?? t.path, false);
    return `
    <div class="track-row" id="track-row-${safeId}">
      <button class="track-play-btn" id="track-btn-${safeId}"
              onclick="window._listenPlayTrack(${JSON.stringify(t.path)}, ${JSON.stringify(t.url)}, 'track-btn-${safeId}', 'track-row-${safeId}')">&#9654;</button>
      <div class="track-info">
        <div class="track-name">${window.escHtml ? window.escHtml(t.name) : t.name}</div>
        <div class="track-path">${window.escHtml ? window.escHtml(t.path) : t.path}</div>
      </div>
      <div class="track-waveform">${waveHtml}</div>
      <div class="track-meta">${dur}${size ? ' · ' + size : ''}</div>
      <div class="track-row-actions">
        <a class="btn btn-secondary btn-sm" href="${t.url}" download title="Download">&#8595;</a>
      </div>
    </div>`;
  }).join('');
}

export function playTrack(path: string, url: string, playBtnId: string, rowId: string): void {
  if (mixAudio && !mixAudio.paused) {
    mixAudio.pause();
    const btn = document.getElementById('mix-play-btn');
    if (btn) (btn as HTMLElement).innerHTML = '&#9654;';
  }
  Object.keys(trackAudios).forEach((p) => {
    if (p !== path && !trackAudios[p].paused) {
      trackAudios[p].pause();
      const oldRow = document.getElementById('track-row-' + CSS.escape(p));
      if (oldRow) oldRow.classList.remove('is-playing');
      const oldBtn = document.getElementById('track-btn-' + CSS.escape(p));
      if (oldBtn) { (oldBtn as HTMLElement).innerHTML = '&#9654;'; oldBtn.classList.remove('is-playing'); }
    }
  });

  if (!trackAudios[path]) { trackAudios[path] = new Audio(); trackAudios[path].preload = 'metadata'; }
  const audio = trackAudios[path];
  const btn   = document.getElementById(playBtnId);
  const row   = document.getElementById(rowId);

  if (audio.paused) {
    audio.src = url; audio.play();
    if (btn) { (btn as HTMLElement).innerHTML = '&#9646;&#9646;'; btn.classList.add('is-playing'); }
    if (row) row.classList.add('is-playing');
    audio.addEventListener('ended', () => {
      if (btn) { (btn as HTMLElement).innerHTML = '&#9654;'; btn.classList.remove('is-playing'); }
      if (row) row.classList.remove('is-playing');
    }, { once: true });
  } else {
    audio.pause();
    if (btn) { (btn as HTMLElement).innerHTML = '&#9654;'; btn.classList.remove('is-playing'); }
    if (row) row.classList.remove('is-playing');
  }
}

export async function initListen(data: ListenPageData): Promise<void> {
  initRepoPage(data);

  const repoId  = String(data.repo_id ?? '');
  const ref     = data.ref ?? 'main';
  const apiBase = data.api_base ?? `/api/v1/musehub/repos/${encodeURIComponent(repoId)}`;

  // Expose playTrack for template onclick handlers
  (window as unknown as Record<string, unknown>)['_listenPlayTrack'] = playTrack;

  const content = document.getElementById('content');
  if (!content) return;
  content.innerHTML = '<p class="loading">Loading audio tracks…</p>';

  try {
    const apiFetch = window.apiFetch;
    if (!apiFetch) return;

    let listing: ListingResponse;
    try {
      listing = await apiFetch(apiBase.replace('/api/v1/musehub', '') + '/listen/' + encodeURIComponent(ref) + '/tracks') as ListingResponse;
    } catch (_) {
      listing = { hasRenders: false, tracks: [], fullMixUrl: null, ref, repoId };
    }

    if (!listing.hasRenders || listing.tracks.length === 0) {
      content.innerHTML = `
      <div class="no-renders-card">
        <span class="no-renders-icon">🎵</span>
        <div class="no-renders-title">No audio renders yet</div>
        <div class="no-renders-sub">Push a commit with .wav, .mp3, .flac, or .ogg files to see them here.</div>
      </div>`;
      return;
    }

    let html = '';
    if (listing.fullMixUrl) {
      html += renderMixPlayer(listing.fullMixUrl, 'Full Mix');
    }
    html += `<div class="card"><div class="track-list">${renderTrackList(listing.tracks)}</div></div>`;
    content.innerHTML = html;

    if (listing.fullMixUrl) initMixPlayer(listing.fullMixUrl);
  } catch (e) {
    content.innerHTML = `<p class="error">Failed to load: ${e instanceof Error ? e.message : String(e)}</p>`;
  }
}
