/**
 * commit.ts — Commit liner-notes page.
 *
 * All page behaviour previously in commit.html's page_script block is here.
 * Config is read from the #page-data JSON element.
 *
 * Registered as: window.MusePages['commit']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

// ── Types ─────────────────────────────────────────────────────────────────────

interface CommitPageCfg {
  repoId:    string;
  commitId:  string;
  base:      string;
  listenUrl: string;
  embedUrl:  string;
  shortId:   string;
}

interface Track { name: string; url: string; }

interface CommitObj { objectId: string; path: string; }

interface CommitData {
  commitId:  string;
  message:   string;
  author:    string;
  timestamp: string;
  branch:    string;
  parentIds?: string[];
  tags?:     string[];
}

interface DimData { dimension: string; score: number; color: string; label: string; }

interface AnalysisKey     { tonic: string; mode: string; keyConfidence: number; }
interface AnalysisTempo   { bpm: number; timeFeel?: string; }
interface AnalysisMeter   { timeSignature: string; }
interface AnalysisEmotion { primaryEmotion: string; confidence: number; valence?: number; }

interface WaveSurferInstance {
  load(url: string): void;
  playPause(): void;
  getDuration(): number;
  getCurrentTime(): number;
  seekTo(pct: number): void;
  setVolume(v: number): void;
  destroy(): void;
  on(event: string, cb: (...args: unknown[]) => void): void;
}

declare global {
  interface Window {
    WaveSurfer?: { create(opts: Record<string, unknown>): WaveSurferInstance };
    ABCJS?: { renderAbc(el: Element, text: string, opts: Record<string, unknown>): void };
    queueAudio?: (url: string, name: string, repo: string) => void;
    downloadArtifact?: (url: string, name: string) => void;
    loadReactions?: (type: string, id: string, elId: string) => void;
    initRepoNav?: (repoId: string) => void;
    escHtml: (s: string) => string;
    apiFetch: (path: string, init?: RequestInit) => Promise<unknown>;
    authHeaders: () => Record<string, string>;
    fmtDate: (d: string) => string;
    fmtRelative: (d: string) => string;
    parseCommitMessage: (msg: string) => { type: string; scope: string; subject: string };
    parseCommitMeta: (msg: string) => Record<string, string>;
    commitTypeBadge: (type: string) => string;
    commitScopeBadge: (scope: string) => string;
    getToken: () => string | null;
    _fetchBlobUrl: (url: string) => Promise<string>;
  }
}

export interface CommitPageData extends RepoPageData {
  commit_id?: string;
}

// ── Module state ──────────────────────────────────────────────────────────────

let _cfg: CommitPageCfg;
let _playerWs:      WaveSurferInstance | null = null;
let _playerAudioEl: HTMLAudioElement   | null = null;
let _playerTracks:  Track[] = [];
let _playerIdx     = 0;
let _playerPlaying = false;

const AUDIO_EXTS    = new Set(['mp3','ogg','wav','flac','m4a']);
const IMAGE_EXTS    = new Set(['webp','png','jpg','jpeg','gif']);
const MIDI_EXTS     = new Set(['mid','midi']);
const SCORE_EXTS    = new Set(['abc','musicxml','xml','mxl']);
const METADATA_EXTS = new Set(['json','yaml','yml','toml']);

const DIM_ICONS: Record<string, string> = {
  harmonic:   '🎵',
  rhythmic:   '🥁',
  melodic:    '🎼',
  structural: '🏗️',
  dynamic:    '📢',
};

// ── Utility shorthand ─────────────────────────────────────────────────────────

function esc(s: string): string          { return window.escHtml(s); }
function apiFetch(path: string, init?: RequestInit): Promise<unknown> {
  return window.apiFetch(path, init);
}
function fmtDate(d: string):     string  { return window.fmtDate(d); }
function fmtRelative(d: string): string  { return window.fmtRelative(d); }

// ── General helpers ───────────────────────────────────────────────────────────

function copyToClipboard(text: string, btn: HTMLElement): void {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent ?? '';
    btn.textContent = '✓';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
}

function currentUsername(): string | null {
  const tok = window.getToken();
  if (!tok) return null;
  try {
    const payload = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return (payload as Record<string, string>).sub || null;
  } catch { return null; }
}

function avatarColor(username: string): string {
  let hash = 0;
  for (let i = 0; i < username.length; i++) hash = username.charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360},55%,45%)`;
}

function avatarHtml(username: string): string {
  const initial = esc((username || '?').charAt(0).toUpperCase());
  const color   = avatarColor(username || '');
  return `<span class="comment-avatar" style="background:${color}">${initial}</span>`;
}

function iapFmtTime(s: number): string {
  if (!isFinite(s)) return '—';
  const m   = Math.floor(s / 60);
  const sec = String(Math.floor(s % 60)).padStart(2, '0');
  return `${m}:${sec}`;
}

// ── Inline audio player ───────────────────────────────────────────────────────

function iapLoad(idx: number): void {
  _playerIdx     = idx;
  _playerPlaying = false;
  const t       = _playerTracks[idx];
  const wrapEl  = document.getElementById('iap-waveform');
  const playBtn = document.getElementById('iap-play-btn');
  const title   = document.querySelector('#inline-player-root .iap-title');
  if (title) title.textContent = t.name;
  if (playBtn) playBtn.textContent = '▶';

  if (_playerWs) { try { _playerWs.destroy(); } catch(_) {} _playerWs = null; }
  if (_playerAudioEl) { _playerAudioEl.pause(); _playerAudioEl = null; }

  if (wrapEl) wrapEl.innerHTML = '<div class="iap-waveform-placeholder">🎵 Loading…</div>';

  if (window.WaveSurfer) {
    if (wrapEl) wrapEl.innerHTML = '<div id="iap-ws-container" style="height:72px;width:100%"></div>';
    _playerWs = window.WaveSurfer.create({
      container:     '#iap-ws-container',
      waveColor:     '#30363d',
      progressColor: '#1f6feb',
      height:        72,
      normalize:     true,
      backend:       'MediaElement',
      fetchParams:   { headers: window.authHeaders() },
    });
    _playerWs.load(t.url);
    _playerWs.on('ready', () => {
      const dur = document.getElementById('iap-duration');
      if (dur) dur.textContent = iapFmtTime(_playerWs!.getDuration());
    });
    _playerWs.on('audioprocess', () => {
      const cur  = document.getElementById('iap-current-time');
      const fill = document.getElementById('iap-progress-fill') as HTMLElement | null;
      const pct  = (_playerWs!.getCurrentTime() / (_playerWs!.getDuration() || 1)) * 100;
      if (cur)  cur.textContent = iapFmtTime(_playerWs!.getCurrentTime());
      if (fill) fill.style.width = pct + '%';
    });
    _playerWs.on('finish', () => {
      _playerPlaying = false;
      const btn = document.getElementById('iap-play-btn');
      if (btn) btn.textContent = '▶';
    });
    _playerWs.on('error', () => {
      if (wrapEl) wrapEl.innerHTML = '<div class="iap-waveform-placeholder" style="color:var(--color-danger)">⚠ Could not load audio.</div>';
    });
    const vol = document.getElementById('iap-volume') as HTMLInputElement | null;
    if (vol) _playerWs.setVolume(parseFloat(vol.value));
  } else {
    if (wrapEl) wrapEl.innerHTML = `
      <audio id="iap-audio-fallback" controls preload="none" style="width:100%;margin:var(--space-2) 0">
        <source src="${t.url}" />
      </audio>`;
    _playerAudioEl = document.getElementById('iap-audio-fallback') as HTMLAudioElement | null;
  }
}

function buildInlinePlayer(tracks: Track[]): void {
  _playerTracks = tracks;
  _playerIdx    = 0;
  const el = document.getElementById('inline-player-root');
  if (!el || !tracks.length) {
    if (el) el.innerHTML = '<p class="text-muted text-sm" style="text-align:center;padding:var(--space-4)">No audio renders attached to this commit.</p>';
    return;
  }

  const trackOpts = tracks.map((t, i) =>
    `<option value="${i}">${esc(t.name)}</option>`).join('');

  el.innerHTML = `
    <div class="iap-title">${esc(tracks[0].name)}</div>
    <div id="iap-waveform" class="iap-waveform-wrap">
      <div class="iap-waveform-placeholder">🎵 Loading waveform…</div>
    </div>
    <div class="iap-controls">
      <button id="iap-play-btn" class="iap-play-btn" title="Play / Pause" data-action="iap-play">▶</button>
      <div style="flex:1;min-width:0">
        <div id="iap-progress-bar" class="iap-progress-bar" data-action="iap-seek">
          <div id="iap-progress-fill" class="iap-progress-fill"></div>
        </div>
        <div class="iap-time-row">
          <span id="iap-current-time">0:00</span>
          <span id="iap-duration">—</span>
        </div>
      </div>
      <div class="iap-volume-wrap">
        🔊
        <input id="iap-volume" type="range" min="0" max="1" step="0.05" value="0.8"
               class="iap-volume-slider" data-action="iap-volume" />
      </div>
    </div>
    ${tracks.length > 1 ? `
    <div class="iap-track-selector">
      <label class="iap-track-label">Track</label>
      <select id="iap-track-sel" class="iap-track-select" data-action="iap-track">
        ${trackOpts}
      </select>
    </div>` : ''}`;

  iapLoad(0);
}

function iapTogglePlay(): void {
  const btn = document.getElementById('iap-play-btn');
  if (_playerWs) {
    _playerWs.playPause();
    _playerPlaying = !_playerPlaying;
    if (btn) btn.textContent = _playerPlaying ? '⏸' : '▶';
  } else if (_playerAudioEl) {
    if (_playerAudioEl.paused) { _playerAudioEl.play(); if (btn) btn.textContent = '⏸'; }
    else { _playerAudioEl.pause(); if (btn) btn.textContent = '▶'; }
  }
}

function iapSeek(event: MouseEvent): void {
  const bar = document.getElementById('iap-progress-bar');
  if (!bar || !_playerWs) return;
  const rect = bar.getBoundingClientRect();
  const pct  = (event.clientX - rect.left) / rect.width;
  _playerWs.seekTo(Math.max(0, Math.min(1, pct)));
}

function iapSetVolume(v: string): void {
  if (_playerWs) _playerWs.setVolume(parseFloat(v));
  else if (_playerAudioEl) _playerAudioEl.volume = parseFloat(v);
}

function iapSwitchTrack(idx: string): void {
  iapLoad(parseInt(idx, 10));
}

// ── Dimension badge helper ────────────────────────────────────────────────────

function dimBadge(dim: DimData): string {
  const icon  = DIM_ICONS[dim.dimension] || '◆';
  const pct   = Math.round(dim.score * 100);
  return `<span class="badge badge-dim-${dim.color}" title="${esc(dim.dimension)}: ${pct}% change">
    ${icon} ${esc(dim.dimension)} <span class="dim-pct">${dim.label}</span>
  </span>`;
}

// ── Artifact helpers ──────────────────────────────────────────────────────────

function artifactHtml(obj: CommitObj, repoName: string): string {
  const ext  = obj.path.split('.').pop()!.toLowerCase();
  const url  = `/api/v1/repos/${_cfg.repoId}/objects/${obj.objectId}/content`;
  const name = obj.path.split('/').pop()!;

  if (IMAGE_EXTS.has(ext)) {
    return `<div class="artifact-card">
      <img data-content-url="${url}" alt="${esc(obj.path)}" loading="lazy" />
      <span class="path">${esc(name)}</span>
    </div>`;
  }

  if (AUDIO_EXTS.has(ext)) {
    return `<div class="artifact-card">
      <audio controls preload="none" style="width:100%;margin-bottom:var(--space-1)">
        <source src="${url}" />
      </audio>
      <button class="btn btn-primary btn-sm" style="width:100%;justify-content:center"
              data-action="queue-audio" data-url="${url}" data-name="${esc(name)}" data-repo="${esc(repoName)}">
        ▶ Queue in Player
      </button>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-1)"
              data-action="download-artifact" data-url="${url}" data-name="${esc(name)}">
        ⬇ Download
      </button>
      <span class="path icon-mp3">${esc(name)}</span>
    </div>`;
  }

  if (MIDI_EXTS.has(ext)) {
    return `<div class="artifact-card">
      <div class="midi-preview" id="midi-${esc(obj.objectId)}" data-url="${url}">
        <div class="midi-roll-placeholder">🎹 MIDI — ${esc(name)}</div>
      </div>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
              data-action="download-artifact" data-url="${url}" data-name="${esc(name)}">
        ⬇ Download MIDI
      </button>
      <a class="btn btn-ghost btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-1)"
         href="${_cfg.base}/objects/${esc(obj.objectId)}/piano-roll" target="_blank">
        🎹 View in Piano Roll
      </a>
      <span class="path icon-mid">${esc(name)}</span>
    </div>`;
  }

  if (SCORE_EXTS.has(ext)) {
    return `<div class="artifact-card">
      <div class="score-preview" id="score-${esc(obj.objectId)}" data-url="${url}" data-ext="${ext}">
        <p class="text-muted text-sm" style="padding:var(--space-2)">🎶 ${esc(ext.toUpperCase())} Score — loading…</p>
      </div>
      <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
              data-action="download-artifact" data-url="${url}" data-name="${esc(name)}">
        ⬇ Download Score
      </button>
      <span class="path">${esc(name)}</span>
    </div>`;
  }

  if (METADATA_EXTS.has(ext)) {
    return `<div class="artifact-card artifact-card--meta">
      <div class="meta-file-icon">{ }</div>
      <span class="path">${esc(name)}</span>
      <a class="btn btn-secondary btn-sm" style="width:100%;justify-content:center;margin-top:var(--space-2)"
         href="${url}" target="_blank">
        👁 View JSON
      </a>
    </div>`;
  }

  return `<div class="artifact-card">
    <button class="btn btn-secondary btn-sm" style="width:100%;justify-content:center"
            data-action="download-artifact" data-url="${url}" data-name="${esc(name)}">
      ⬇ Download
    </button>
    <span class="path">${esc(name)}</span>
  </div>`;
}

function buildArtifactSections(objects: CommitObj[], repoName: string): string {
  const getExt = (o: CommitObj) => o.path.split('.').pop()!.toLowerCase();
  const images   = objects.filter(o => IMAGE_EXTS.has(getExt(o)));
  const audio    = objects.filter(o => AUDIO_EXTS.has(getExt(o)));
  const midi     = objects.filter(o => MIDI_EXTS.has(getExt(o)));
  const scores   = objects.filter(o => SCORE_EXTS.has(getExt(o)));
  const metadata = objects.filter(o => METADATA_EXTS.has(getExt(o)));
  const other    = objects.filter(o => {
    const ext = getExt(o);
    return !IMAGE_EXTS.has(ext) && !AUDIO_EXTS.has(ext) && !MIDI_EXTS.has(ext)
        && !SCORE_EXTS.has(ext) && !METADATA_EXTS.has(ext);
  });

  const section = (title: string, icon: string, items: CommitObj[]) => {
    if (!items.length) return '';
    return `<div class="artifact-section">
      <h3 class="artifact-section-title">${icon} ${title} <span class="artifact-count">(${items.length})</span></h3>
      <div class="artifact-grid">${items.map(o => artifactHtml(o, repoName)).join('')}</div>
    </div>`;
  };

  const parts = [
    section('Piano Rolls', '🎹', images),
    section('Audio', '🎵', audio),
    section('MIDI', '🎻', midi),
    section('Scores', '🎼', scores),
    section('Metadata', '📄', metadata),
    section('Other', '📎', other),
  ].filter(Boolean);

  if (!parts.length) {
    return `<div class="empty-state" style="padding:var(--space-6)">
      <div class="empty-icon">💾</div>
      <p class="empty-title">No artifacts</p>
      <p class="empty-desc">Push audio files and MIDI via <code>muse push</code> to see them here.</p>
    </div>`;
  }
  return parts.join('');
}

async function hydrateImages(): Promise<void> {
  document.querySelectorAll<HTMLImageElement>('img[data-content-url]').forEach(async img => {
    const url = img.dataset.contentUrl!;
    try {
      img.src = await window._fetchBlobUrl(url);
    } catch (_) {
      img.alt = 'Preview unavailable';
    }
  });
}

function parseInstruments(message: string): string[] {
  const tracks: string[] = [];
  const trackRe = /\b(bass|keys|drums?|strings?|horn|trumpet|sax(?:ophone)?|guitar|piano|synth|pad|lead|percussion|vox|vocals?)\b/gi;
  let m: RegExpExecArray | null;
  while ((m = trackRe.exec(message)) !== null) {
    const t = m[1].toLowerCase();
    if (!tracks.includes(t)) tracks.push(t);
  }
  return tracks;
}

function renderCommitBody(message: string): string {
  const lines = message.split('\n');
  if (lines.length <= 1) return '';
  const body = lines.slice(1).join('\n').trim();
  if (!body) return '';
  const escaped = body.split('\n').map(l => `<span class="commit-body-line">${esc(l) || '&nbsp;'}</span>`).join('');
  return `<div class="commit-body">${escaped}</div>`;
}

function buildBeforeAfterAudio(currentAudio: CommitObj[], parentAudio: CommitObj[], repoId: string): string {
  if (!currentAudio.length && !parentAudio.length) return '';
  const playerCard = (title: string, files: CommitObj[], idSuffix: string) => {
    if (!files.length) return '';
    const f    = files[0];
    const url  = `/api/v1/repos/${repoId}/objects/${f.objectId}/content`;
    const name = f.path.split('/').pop()!;
    return `<div class="ab-player" id="ab-${idSuffix}">
      <div class="ab-label">${title}</div>
      <audio controls preload="none" style="width:100%">
        <source src="${url}" />
      </audio>
      <span class="path text-sm">${esc(name)}</span>
    </div>`;
  };
  return `<div class="card">
    <h2 style="margin-bottom:var(--space-3)">🔊 Before / After</h2>
    <p class="text-sm text-muted" style="margin-bottom:var(--space-3)">
      Compare the primary audio render of this commit against its parent.
    </p>
    <div class="ab-container">
      ${playerCard('After (this commit)', currentAudio, 'after')}
      ${playerCard('Before (parent)', parentAudio, 'before')}
    </div>
  </div>`;
}

function tagBadges(tags: string[]): string {
  if (!tags || !tags.length) return '';
  return tags.map(t => `<span class="badge badge-tag" title="Tag: ${esc(t)}">🏷 ${esc(t)}</span>`).join('');
}

function buildChildLinks(allCommits: CommitData[], thisId: string, base: string): string {
  const children = allCommits.filter(c => (c.parentIds || []).includes(thisId));
  if (!children.length) return '<span class="text-muted text-sm">none (HEAD or branch tip)</span>';
  return children.map(c =>
    `<a href="${base}/commits/${c.commitId}" class="text-mono text-sm" title="View child commit">${c.commitId.substring(0,8)}</a>`
  ).join(' ');
}

function tagPill(tag: string): string {
  const colonIdx = tag.indexOf(':');
  const ns  = colonIdx >= 0 ? tag.slice(0, colonIdx).toLowerCase() : '';
  const val = colonIdx >= 0 ? tag.slice(colonIdx + 1) : tag;
  const colourMap: Record<string, string> = {
    emotion: 'pill-emotion', stage: 'pill-stage', ref: 'pill-ref',
    key: 'pill-key', tempo: 'pill-tempo', time: 'pill-time', meter: 'pill-time',
  };
  const colourClass = colourMap[ns] || 'pill-generic';
  const isRefUrl = ns === 'ref' && /^https?:\/\//.test(val);
  const href   = isRefUrl ? val : (ns ? `${_cfg.base}/tags?namespace=${encodeURIComponent(ns)}` : null);
  const target = isRefUrl ? ' target="_blank" rel="noopener noreferrer"' : '';
  const inner  = ns
    ? `<span class="pill-ns">${esc(ns)}</span><span class="pill-sep">:</span>${esc(val)}`
    : esc(tag);
  return href
    ? `<a class="muse-pill ${colourClass}"${target} href="${esc(href)}">${inner}</a>`
    : `<span class="muse-pill ${colourClass}">${inner}</span>`;
}

function buildProseSummary(
  key:       AnalysisKey    | null,
  tempo:     AnalysisTempo  | null,
  meter:     AnalysisMeter  | null,
  emotion:   AnalysisEmotion | null,
  diffData:  { dimensions?: DimData[] } | null,
  numObjects: number,
): string {
  const parts1: string[] = [];
  if (key)   parts1.push(`in ${esc(key.tonic)} ${esc(key.mode)}`);
  if (tempo) parts1.push(`at ${esc(String(tempo.bpm))} BPM`);
  if (meter) parts1.push(`in ${esc(meter.timeSignature)}`);

  const sentence1 = numObjects > 0
    ? `This commit contains ${numObjects} artifact${numObjects !== 1 ? 's' : ''}${parts1.length ? ' ' + parts1.join(', ') : ''}.`
    : parts1.length ? `This commit records musical content ${parts1.join(', ')}.` : '';

  const dims       = (diffData?.dimensions || []).filter(d => d.score >= 0.15).map(d => esc(d.dimension));
  const emotionStr = emotion ? esc(emotion.primaryEmotion) : '';
  let sentence2    = '';
  if (dims.length && emotionStr) {
    sentence2 = `The primary musical changes are ${dims.join(' and ')}, carrying a ${emotionStr} character.`;
  } else if (dims.length) {
    sentence2 = `The primary musical changes are ${dims.join(' and ')}.`;
  } else if (emotionStr) {
    sentence2 = `The musical character is ${emotionStr}.`;
  }

  if (!sentence1 && !sentence2) return '';
  return `<p class="commit-prose-summary text-sm">${[sentence1, sentence2].filter(Boolean).join(' ')}</p>`;
}

async function loadMuseTagsPanel(
  commitTags: string[],
  diffData:   { dimensions?: DimData[] } | null,
  numObjects: number,
): Promise<void> {
  const el = document.getElementById('muse-tags-panel');
  if (!el) return;

  const [keyRes, tempoRes, meterRes, emotionRes] = await Promise.allSettled([
    apiFetch(`/repos/${_cfg.repoId}/analysis/${encodeURIComponent(_cfg.commitId)}/key`),
    apiFetch(`/repos/${_cfg.repoId}/analysis/${encodeURIComponent(_cfg.commitId)}/tempo`),
    apiFetch(`/repos/${_cfg.repoId}/analysis/${encodeURIComponent(_cfg.commitId)}/meter`),
    apiFetch(`/repos/${_cfg.repoId}/analysis/${encodeURIComponent(_cfg.commitId)}/emotion`),
  ]);

  const key     = keyRes.status     === 'fulfilled' ? keyRes.value     as AnalysisKey     : null;
  const tempo   = tempoRes.status   === 'fulfilled' ? tempoRes.value   as AnalysisTempo   : null;
  const meter   = meterRes.status   === 'fulfilled' ? meterRes.value   as AnalysisMeter   : null;
  const emotion = emotionRes.status === 'fulfilled' ? emotionRes.value as AnalysisEmotion : null;

  const analysisPills: string[] = [];
  if (key)     analysisPills.push(tagPill(`key:${key.tonic} ${key.mode}`));
  if (tempo)   analysisPills.push(tagPill(`tempo:${tempo.bpm}bpm`));
  if (meter)   analysisPills.push(tagPill(`time:${meter.timeSignature}`));
  if (emotion) analysisPills.push(tagPill(`emotion:${emotion.primaryEmotion}`));
  if (emotion && emotion.valence != null) {
    const v     = parseFloat(String(emotion.valence));
    const stage = v > 0.6 ? 'positive' : v < 0.4 ? 'tense' : 'neutral';
    analysisPills.push(tagPill(`stage:${stage}`));
  }

  const dbPills  = (commitTags || []).map(t => tagPill(t));
  const allPills = [...dbPills, ...analysisPills];

  const cells: string[] = [];
  if (key) cells.push(`
    <div class="meta-item">
      <span class="meta-label">Key</span>
      <span class="meta-value text-sm">
        ♭ ${esc(key.tonic)} ${esc(key.mode)}
        <span class="text-muted">${(key.keyConfidence * 100).toFixed(0)}%</span>
      </span>
    </div>`);
  if (tempo) cells.push(`
    <div class="meta-item">
      <span class="meta-label">Tempo</span>
      <span class="meta-value text-sm">⏱ ${esc(String(tempo.bpm))} BPM
        ${tempo.timeFeel ? `<span class="text-muted">${esc(tempo.timeFeel)}</span>` : ''}
      </span>
    </div>`);
  if (meter) cells.push(`
    <div class="meta-item">
      <span class="meta-label">Time sig.</span>
      <span class="meta-value text-sm">${esc(meter.timeSignature)}</span>
    </div>`);
  if (emotion) cells.push(`
    <div class="meta-item">
      <span class="meta-label">Emotion</span>
      <span class="meta-value text-sm">
        ${esc(emotion.primaryEmotion)}
        <span class="text-muted">${(emotion.confidence * 100).toFixed(0)}%</span>
      </span>
    </div>`);

  const proseSummary = buildProseSummary(key, tempo, meter, emotion, diffData, numObjects);

  if (!cells.length && !allPills.length && !proseSummary) {
    el.innerHTML = '<p class="text-muted text-sm">No analysis data available for this commit.</p>';
    return;
  }

  el.innerHTML = `
    ${proseSummary}
    ${cells.length ? `<div class="meta-row muse-tags-meta-row" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr));margin-bottom:var(--space-3)">${cells.join('')}</div>` : ''}
    ${allPills.length ? `<div class="muse-pills-row">${allPills.join('')}</div>` : ''}`;
}

async function loadCrossReferences(): Promise<void> {
  const el = document.getElementById('xrefs-body');
  if (!el) return;

  const shortHash = _cfg.commitId.substring(0, 8);
  const [prsRes, issuesRes, sessionsRes] = await Promise.allSettled([
    apiFetch(`/repos/${_cfg.repoId}/pull-requests?limit=100`),
    apiFetch(`/repos/${_cfg.repoId}/issues?limit=100`),
    apiFetch(`/repos/${_cfg.repoId}/sessions?limit=50`),
  ]);

  type PR      = { state: string; prId: string; title: string; fromBranch: string; toBranch: string; description?: string };
  type Issue   = { state: string; number: string; title: string; body?: string };
  type Session = { sessionId: string; commitIds?: string[]; description?: string; title?: string; startedAt?: string; createdAt?: string };

  const prs      = ((prsRes.status      === 'fulfilled' ? (prsRes.value      as { pullRequests?: PR[] }).pullRequests      : null) || []) as PR[];
  const issues   = ((issuesRes.status   === 'fulfilled' ? (issuesRes.value   as { issues?: Issue[] }).issues               : null) || []) as Issue[];
  const sessions = ((sessionsRes.status === 'fulfilled' ? (sessionsRes.value as { sessions?: Session[] }).sessions         : null) || []) as Session[];

  const refPrs = prs.filter(pr =>
    (pr.description || '').includes(_cfg.commitId.substring(0, 7)) ||
    (pr.description || '').includes(shortHash) ||
    (pr.fromBranch || '').includes(shortHash)
  );
  const refIssues = issues.filter(i =>
    (i.body || '').includes(_cfg.commitId.substring(0, 7)) ||
    (i.body || '').includes(shortHash) ||
    (i.title || '').includes(shortHash)
  );
  const refSessions = sessions.filter(s =>
    (s.commitIds || []).includes(_cfg.commitId) ||
    (s.description || '').includes(shortHash)
  );

  if (!refPrs.length && !refIssues.length && !refSessions.length) {
    el.innerHTML = '<p class="text-muted text-sm" style="margin:0">No cross-references found for this commit.</p>';
    return;
  }

  let html = '';
  if (refPrs.length) {
    html += `<div class="xref-group">
      <div class="xref-group-label">Pull Requests (${refPrs.length})</div>
      <div class="xref-list">
        ${refPrs.map(pr => `
          <div class="xref-item">
            <span class="xref-icon ${pr.state === 'open' ? 'xref-open' : 'xref-closed'}">⊕</span>
            <a href="${_cfg.base}/pulls/${encodeURIComponent(pr.prId)}" class="xref-link">
              ${esc(pr.title)}
            </a>
            <span class="xref-meta">#${esc(String(pr.prId))} · ${esc(pr.fromBranch || '')} → ${esc(pr.toBranch || '')}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }
  if (refIssues.length) {
    html += `<div class="xref-group">
      <div class="xref-group-label">Issues (${refIssues.length})</div>
      <div class="xref-list">
        ${refIssues.map(i => `
          <div class="xref-item">
            <span class="xref-icon ${i.state === 'open' ? 'xref-open' : 'xref-closed'}">●</span>
            <a href="${_cfg.base}/issues/${encodeURIComponent(i.number)}" class="xref-link">
              ${esc(i.title)}
            </a>
            <span class="xref-meta">#${esc(String(i.number))}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }
  if (refSessions.length) {
    html += `<div class="xref-group">
      <div class="xref-group-label">Sessions (${refSessions.length})</div>
      <div class="xref-list">
        ${refSessions.map(s => `
          <div class="xref-item">
            <span class="xref-icon xref-session">🎙</span>
            <a href="${_cfg.base}/sessions/${encodeURIComponent(s.sessionId)}" class="xref-link">
              ${esc(s.title || s.sessionId.substring(0, 8))}
            </a>
            <span class="xref-meta">${fmtDate(s.startedAt || s.createdAt || '')}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }

  el.innerHTML = html;
}

function renderScorePreviews(): void {
  document.querySelectorAll<HTMLElement>('.score-preview[data-ext="abc"]').forEach(async el => {
    try {
      const url  = el.dataset.url!;
      const text = await fetch(url, { headers: window.authHeaders() }).then(r => r.text());
      if (window.ABCJS) {
        el.innerHTML = '';
        window.ABCJS.renderAbc(el, text, { responsive: 'resize', staffwidth: el.offsetWidth || 400 });
      } else {
        el.innerHTML = '<pre style="font-size:11px;overflow-x:auto">' + esc(text.substring(0, 400)) + '</pre>';
      }
    } catch(_) { /* non-fatal */ }
  });
}

// ── AI summary ────────────────────────────────────────────────────────────────

async function loadAiSummary(): Promise<void> {
  const panel = document.getElementById('ai-summary-panel');
  const body  = document.getElementById('ai-summary-body');
  if (!panel || !body) return;
  try {
    type CtxData = { missingElements?: string[]; suggestions?: Record<string, string> };
    const ctx      = await apiFetch(`/repos/${_cfg.repoId}/context/${_cfg.commitId}`) as CtxData;
    const missing  = ctx.missingElements || [];
    const suggests = ctx.suggestions || {};
    const suggKeys = Object.keys(suggests);
    let html = '';
    if (missing.length > 0) {
      html += '<p class="text-sm text-muted" style="margin-bottom:var(--space-2)">Missing elements:</p>';
      html += '<ul style="padding-left:var(--space-4);font-size:var(--font-size-sm);color:var(--color-warning)">';
      html += missing.map(m => '<li>' + esc(m) + '</li>').join('');
      html += '</ul>';
    }
    if (suggKeys.length > 0) {
      html += '<p class="text-sm text-muted" style="margin-top:var(--space-3);margin-bottom:var(--space-2)">Suggestions:</p>';
      html += suggKeys.map(k =>
        '<div style="margin-bottom:var(--space-2);font-size:var(--font-size-sm)">'
        + '<strong>' + esc(k) + '</strong>: ' + esc(suggests[k])
        + '</div>'
      ).join('');
    }
    if (!html) html = '<p class="text-sm text-muted">All musical dimensions look complete.</p>';
    body.innerHTML = html;
    panel.style.display = '';
  } catch(_) { /* non-critical */ }
}

// ── Compose modal ─────────────────────────────────────────────────────────────

function openCompose(): void {
  const modal = document.getElementById('compose-modal');
  if (modal) {
    modal.style.display = 'flex';
    const out    = document.getElementById('compose-output');
    const stream = document.getElementById('compose-stream');
    if (out)    out.style.display = 'none';
    if (stream) stream.textContent = '';
  }
}

function closeCompose(): void {
  const modal = document.getElementById('compose-modal');
  if (modal) modal.style.display = 'none';
}

async function sendCompose(): Promise<void> {
  const promptEl = document.getElementById('compose-prompt') as HTMLTextAreaElement | null;
  const prompt   = promptEl?.value.trim();
  if (!prompt) return;
  const btn    = document.getElementById('compose-send-btn') as HTMLButtonElement | null;
  const output = document.getElementById('compose-output');
  const stream = document.getElementById('compose-stream');
  if (btn)    { btn.disabled = true; btn.textContent = '⏳ Generating…'; }
  if (output) output.style.display = '';
  if (stream) stream.textContent = '';

  try {
    const res = await fetch('/api/v1/muse/stream', {
      method:  'POST',
      headers: { ...window.authHeaders(), 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: prompt, mode: 'compose', repo_id: _cfg.repoId, commit_id: _cfg.commitId }),
    });
    if (!res.ok) {
      if (stream) stream.textContent = `❌ ${res.status}: ${await res.text()}`;
      return;
    }
    const reader  = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') break;
          try {
            const obj = JSON.parse(data) as { content?: string; text?: string } | string;
            if (typeof obj === 'string')  { if (stream) stream.textContent += obj; }
            else if (obj.content)         { if (stream) stream.textContent += obj.content; }
            else if (obj.text)            { if (stream) stream.textContent += obj.text; }
          } catch { if (stream) stream.textContent += data; }
          if (stream) stream.scrollTop = stream.scrollHeight;
        }
      }
    }
  } catch(e) {
    if (stream) stream.textContent += `\n\n❌ ${(e as Error).message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '♪ Re-generate'; }
  }
}

// ── Comments ──────────────────────────────────────────────────────────────────

interface Comment {
  comment_id: string;
  author:     string;
  body:       string;
  created_at: string;
  parent_id:  string | null;
}

function renderComments(comments: Comment[], me: string | null): string {
  const topLevel = comments.filter(c => !c.parent_id);
  const replies  = comments.filter(c =>  c.parent_id);
  if (topLevel.length === 0 && !me) return '<p class="text-sm text-muted" style="margin:0">No comments yet.</p>';
  if (topLevel.length === 0)        return '<p class="text-sm text-muted" style="margin:0">Be the first to comment.</p>';
  return topLevel.map(c => commentHtml(c, replies, me)).join('');
}

function commentHtml(c: Comment, allReplies: Comment[], me: string | null): string {
  const isOwn         = me && c.author === me;
  const threadReplies = allReplies.filter(r => r.parent_id === c.comment_id);
  return `
<div class="comment-thread" id="comment-${esc(c.comment_id)}">
  <div class="comment-row">
    ${avatarHtml(c.author)}
    <div class="comment-body-col">
      <div class="comment-meta">
        <a href="/${encodeURIComponent(c.author)}" class="comment-author">${esc(c.author)}</a>
        <span class="comment-ts" title="${esc(c.created_at)}">${fmtRelative(c.created_at)}</span>
      </div>
      <div class="comment-text">${esc(c.body)}</div>
      <div class="comment-actions">
        ${me ? `<button class="btn btn-ghost btn-xs" data-action="show-reply" data-comment-id="${esc(c.comment_id)}">↩ Reply</button>` : ''}
        ${isOwn ? `<button class="btn btn-ghost btn-xs comment-delete-btn" data-action="delete-comment" data-comment-id="${esc(c.comment_id)}">🗑</button>` : ''}
      </div>
      <div class="reply-form-slot" id="reply-slot-${esc(c.comment_id)}"></div>
      ${threadReplies.length > 0 ? `<div class="comment-replies">${threadReplies.map(r => replyHtml(r, me)).join('')}</div>` : ''}
    </div>
  </div>
</div>`;
}

function replyHtml(c: Comment, me: string | null): string {
  const isOwn = me && c.author === me;
  return `
<div class="comment-row comment-reply-row" id="comment-${esc(c.comment_id)}">
  ${avatarHtml(c.author)}
  <div class="comment-body-col">
    <div class="comment-meta">
      <a href="/${encodeURIComponent(c.author)}" class="comment-author">${esc(c.author)}</a>
      <span class="comment-ts" title="${esc(c.created_at)}">${fmtRelative(c.created_at)}</span>
    </div>
    <div class="comment-text">${esc(c.body)}</div>
    ${isOwn ? `<div class="comment-actions"><button class="btn btn-ghost btn-xs comment-delete-btn" data-action="delete-comment" data-comment-id="${esc(c.comment_id)}">🗑</button></div>` : ''}
  </div>
</div>`;
}

async function loadComments(): Promise<void> {
  if (!document.getElementById('comments-section')) return;
  try {
    const comments = await apiFetch(`/repos/${_cfg.repoId}/comments?target_type=commit&target_id=${encodeURIComponent(_cfg.commitId)}`) as Comment[];
    const me       = currentUsername();
    const listEl   = document.getElementById('comments-list');
    if (listEl) listEl.innerHTML = renderComments(comments, me);
    if (me) {
      const form   = document.getElementById('new-comment-form');
      const avatar = document.getElementById('new-comment-avatar') as HTMLElement | null;
      if (form) form.style.display = '';
      if (avatar) {
        avatar.textContent        = me.charAt(0).toUpperCase();
        avatar.style.background   = avatarColor(me);
        avatar.style.color        = '#fff';
      }
    }
  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') {
      const listEl = document.getElementById('comments-list');
      if (listEl) listEl.innerHTML = `<p class="error text-sm">✕ ${esc(err.message)}</p>`;
    }
  }
}

async function submitComment(parentId: string | null): Promise<void> {
  const textareaId = parentId ? `reply-body-${parentId}` : 'new-comment-body';
  const textarea   = document.getElementById(textareaId) as HTMLTextAreaElement | null;
  if (!textarea) return;
  const body = textarea.value.trim();
  if (!body) return;

  const btn = parentId
    ? document.querySelector<HTMLButtonElement>(`#reply-slot-${parentId} .comment-submit-btn`)
    : document.getElementById('comment-submit-btn') as HTMLButtonElement | null;
  if (btn) { btn.disabled = true; btn.textContent = 'Posting…'; }

  try {
    await apiFetch(`/repos/${_cfg.repoId}/comments`, {
      method: 'POST',
      body:   JSON.stringify({ target_type: 'commit', target_id: _cfg.commitId, body, parent_id: parentId || null }),
    });
    textarea.value = '';
    if (parentId) {
      const slot = document.getElementById(`reply-slot-${parentId}`);
      if (slot) slot.innerHTML = '';
    }
    await loadComments();
  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') alert('Failed to post comment: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Comment'; }
  }
}

async function deleteComment(commentId: string): Promise<void> {
  if (!confirm('Delete this comment?')) return;
  try {
    await apiFetch(`/repos/${_cfg.repoId}/comments/${commentId}`, { method: 'DELETE' });
    await loadComments();
  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') alert('Failed to delete: ' + err.message);
  }
}

function showReplyForm(parentId: string): void {
  const slot = document.getElementById(`reply-slot-${parentId}`);
  if (!slot) return;
  if (slot.innerHTML.trim()) { slot.innerHTML = ''; return; }
  slot.innerHTML = `
<div class="reply-form">
  <textarea id="reply-body-${esc(parentId)}" class="form-input comment-textarea" rows="2"
            placeholder="Write a reply…" style="resize:vertical"></textarea>
  <div class="comment-form-actions">
    <button class="btn btn-primary btn-sm comment-submit-btn" data-action="comment-submit" data-parent-id="${esc(parentId)}">Comment</button>
    <button class="btn btn-ghost btn-sm" data-action="cancel-reply" data-parent-id="${esc(parentId)}">Cancel</button>
  </div>
</div>`;
  const ta = document.getElementById(`reply-body-${parentId}`) as HTMLTextAreaElement | null;
  if (ta) ta.focus();
}

// ── Event delegation ──────────────────────────────────────────────────────────

function setupEventDelegation(): void {
  document.addEventListener('click', (e) => {
    const target = (e.target as Element).closest<HTMLElement>('[data-action]');
    if (!target) return;
    switch (target.dataset.action) {
      case 'iap-play':  iapTogglePlay(); break;
      case 'iap-seek':  iapSeek(e as MouseEvent); break;
      case 'queue-audio': {
        const { url, name, repo } = target.dataset;
        if (url && typeof window.queueAudio === 'function') window.queueAudio(url, name ?? '', repo ?? '');
        break;
      }
      case 'download-artifact': {
        const { url, name } = target.dataset;
        if (url && typeof window.downloadArtifact === 'function') window.downloadArtifact(url, name ?? '');
        break;
      }
      case 'copy-sha':
        copyToClipboard(target.dataset.sha ?? '', target);
        break;
      case 'open-compose':  openCompose(); break;
      case 'compose-close': closeCompose(); break;
      case 'compose-send':  void sendCompose(); break;
      case 'compose-modal-backdrop':
        if (e.target === target) closeCompose();
        break;
      case 'comment-submit':
        void submitComment(target.dataset.parentId || null);
        break;
      case 'cancel-reply': {
        const slot = document.getElementById(`reply-slot-${target.dataset.parentId}`);
        if (slot) slot.innerHTML = '';
        break;
      }
      case 'show-reply':
        showReplyForm(target.dataset.commentId ?? '');
        break;
      case 'delete-comment':
        void deleteComment(target.dataset.commentId ?? '');
        break;
    }
  });

  document.addEventListener('input', (e) => {
    const target = e.target as HTMLElement;
    if (target.dataset.action === 'iap-volume') {
      iapSetVolume((target as HTMLInputElement).value);
    }
  });

  document.addEventListener('change', (e) => {
    const target = e.target as HTMLElement;
    if (target.dataset.action === 'iap-track') {
      iapSwitchTrack((target as HTMLSelectElement).value);
    }
  });
}

// ── Main page load ────────────────────────────────────────────────────────────

async function load(): Promise<void> {
  try {
    const [commitsData, objectsData, diffData] = await Promise.all([
      apiFetch(`/repos/${_cfg.repoId}/commits?limit=200`),
      apiFetch(`/repos/${_cfg.repoId}/objects`),
      apiFetch(`/repos/${_cfg.repoId}/commits/${_cfg.commitId}/diff-summary`).catch(() => null),
    ]) as [{ commits?: CommitData[] }, { objects?: CommitObj[] }, { dimensions?: DimData[] } | null];

    const allCommits = commitsData.commits || [];
    const commit     = allCommits.find(c => c.commitId === _cfg.commitId);
    const objects    = objectsData.objects || [];
    const repoName   = _cfg.repoId;

    if (!commit) {
      const content = document.getElementById('content');
      if (content) content.innerHTML =
        `<div class="card"><p class="error">Commit ${esc(_cfg.commitId)} not found in recent history.</p></div>`;
      return;
    }

    const parsed      = window.parseCommitMessage(commit.message);
    const meta        = window.parseCommitMeta(commit.message);
    const instruments = parseInstruments(commit.message);

    const typeBadge  = window.commitTypeBadge(parsed.type);
    const scopeBadge = window.commitScopeBadge(parsed.scope);
    const dimBadges  = diffData
      ? (diffData.dimensions || []).filter(d => d.score >= 0.15).map(dimBadge).join('')
      : '';

    const parentLinks = (commit.parentIds || []).length > 0
      ? commit.parentIds!.map(p =>
          `<a href="${_cfg.base}/commits/${p}" class="text-mono text-sm" title="View parent commit">${p.substring(0,8)}</a>`
        ).join(' ')
      : '<span class="text-muted text-sm">none (root commit)</span>';

    const childLinks = buildChildLinks(allCommits, commit.commitId, _cfg.base);

    const instTags = instruments.length > 0
      ? instruments.map(i => `<span class="nav-meta-tag">🎸 ${esc(i)}</span>`).join('')
      : '';

    const tagSection = tagBadges(commit.tags || []);

    const parentId = (commit.parentIds || [])[0] || null;
    let parentObjects: CommitObj[] = [];
    if (parentId) {
      try {
        const parentData = await apiFetch(`/repos/${_cfg.repoId}/objects?commit_id=${parentId}`) as { objects?: CommitObj[] };
        parentObjects = parentData.objects || [];
      } catch(_) { /* non-fatal */ }
    }

    const currentAudio = objects.filter(o => AUDIO_EXTS.has(o.path.split('.').pop()!.toLowerCase()));
    const parentAudio  = parentObjects.filter(o => AUDIO_EXTS.has(o.path.split('.').pop()!.toLowerCase()));
    const audioFiles   = currentAudio;

    const stemBrowser = audioFiles.length > 1
      ? `<div class="card">
          <h2 style="margin-bottom:var(--space-3)">🎙 Stem Browser</h2>
          <p class="text-sm text-muted" style="margin-bottom:var(--space-3)">Solo individual instrument stems.</p>
          <div class="stem-browser" id="stem-browser">
            ${audioFiles.map((obj, i) => {
              const name = obj.path.split('/').pop()!.replace(/\.[^.]+$/, '');
              const url  = `/api/v1/repos/${_cfg.repoId}/objects/${obj.objectId}/content`;
              return `<div class="stem-row" id="stem-row-${i}">
                <button class="player-btn" data-action="queue-audio" data-url="${url}" data-name="${esc(name)}" data-repo="" title="Play stem">▶</button>
                <span class="stem-label">${esc(name)}</span>
                <div class="waveform-bar" style="flex:1;height:32px;cursor:pointer" data-action="queue-audio" data-url="${url}" data-name="${esc(name)}" data-repo="">
                  ${Array.from({length: 48}, (_, j) => {
                    const seed = (name.charCodeAt(j % name.length) + j) * 1103515245;
                    const h = 20 + (Math.abs(seed) % 70);
                    return `<div class="wave-col" style="height:${h}%"></div>`;
                  }).join('')}
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>`
      : '';

    const artifactSection = buildArtifactSections(objects, repoName);

    const musicalMeta = [
      meta['key']              ? `<div class="meta-item"><span class="meta-label">Key</span><span class="meta-value text-sm">♭ ${esc(meta['key'])}</span></div>` : '',
      (meta['tempo']||meta['bpm']) ? `<div class="meta-item"><span class="meta-label">Tempo</span><span class="meta-value text-sm">⏱ ${esc(meta['tempo']||meta['bpm'])} BPM</span></div>` : '',
      meta['section']          ? `<div class="meta-item"><span class="meta-label">Section</span><span class="meta-value badge badge-dim-structural">${esc(meta['section'])}</span></div>` : '',
      meta['meter']            ? `<div class="meta-item"><span class="meta-label">Meter</span><span class="meta-value text-sm">${esc(meta['meter'])}</span></div>` : '',
    ].filter(Boolean).join('');

    const firstChild = allCommits.filter(c => (c.parentIds || []).includes(_cfg.commitId))[0];

    const content = document.getElementById('content');
    if (content) content.innerHTML = `
      <div class="commit-liner-notes">

        <div class="commit-header-row">
          <div class="commit-header-left">
            ${typeBadge}${scopeBadge}
            ${instTags}
            ${tagSection}
          </div>
          <div class="commit-header-right">
            <a href="${_cfg.base}/commits/${_cfg.commitId}/diff" class="btn btn-secondary btn-sm">
              ⊕ Musical Diff
            </a>
            <a href="${_cfg.base}/context/${_cfg.commitId}" class="btn btn-secondary btn-sm">
              🧠 AI Context
            </a>
            <button class="btn btn-primary btn-sm" data-action="open-compose">
              🎵 Compose Variation
            </button>
          </div>
        </div>

        ${dimBadges ? `<div class="card dim-badges-card">
          <div class="dim-badges-label">Musical Changes</div>
          <div class="dim-badges-row">${dimBadges}</div>
        </div>` : ''}

        <div class="card commit-message-card">
          <h1 class="commit-subject">${esc(parsed.subject || commit.message)}</h1>
          ${parsed.type || parsed.scope ? `
          <div style="margin-top:var(--space-2);font-size:var(--font-size-sm);color:var(--text-muted)">
            ${parsed.type ? `<strong>${esc(parsed.type)}</strong>` : ''}
            ${parsed.scope ? ` in <strong>${esc(parsed.scope)}</strong>` : ''}
          </div>` : ''}
          ${renderCommitBody(commit.message)}
        </div>

        <div class="card iap-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">🎧 Listen</h2>
            <a href="${_cfg.listenUrl}" class="btn btn-secondary btn-sm" target="_blank">
              Open Full Listen Page ↗
            </a>
          </div>
          <div id="inline-player-root">
            <p class="text-muted text-sm">Loading audio…</p>
          </div>
        </div>

        <div class="card">
          <h2 style="margin:0 0 var(--space-3) 0">🏷 Muse Tags &amp; Metadata</h2>
          <div id="muse-tags-panel"><p class="loading text-sm">Loading analysis…</p></div>
        </div>

        <div class="card">
          <div class="meta-row" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
            <div class="meta-item">
              <span class="meta-label">Author</span>
              <span class="meta-value">
                <a href="/${esc(commit.author)}" class="text-sm">${esc(commit.author)}</a>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Date</span>
              <span class="meta-value text-sm">${fmtDate(commit.timestamp)}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Branch</span>
              <span class="meta-value text-mono text-sm">${esc(commit.branch || '—')}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">SHA</span>
              <span class="meta-value" style="display:flex;align-items:center;gap:var(--space-1)">
                <span class="text-mono text-sm sha-full" title="${esc(_cfg.commitId)}">${esc(_cfg.commitId)}</span>
                <button class="btn btn-ghost btn-xs copy-btn" data-action="copy-sha" data-sha="${esc(_cfg.commitId)}" title="Copy full SHA">⧉</button>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Parents</span>
              <span class="meta-value">${parentLinks}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Children</span>
              <span class="meta-value">${childLinks}</span>
            </div>
            ${musicalMeta}
          </div>
        </div>

        ${buildBeforeAfterAudio(currentAudio, parentAudio, _cfg.repoId)}

        ${stemBrowser}

        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">Artifacts (${objects.length})</h2>
            ${audioFiles.length > 0 ? `
            <button class="btn btn-primary btn-sm"
                    data-action="queue-audio"
                    data-url="/api/v1/repos/${_cfg.repoId}/objects/${audioFiles[0].objectId}/content"
                    data-name="${esc(audioFiles[0].path.split('/').pop()!)}"
                    data-repo="${esc(_cfg.repoId)}">
              ▶ Play Latest
            </button>` : ''}
          </div>
          ${artifactSection}
        </div>

        <div class="card" style="padding:var(--space-3) var(--space-4)">
          <div id="commit-reactions"><p class="text-muted text-sm">Loading reactions…</p></div>
        </div>

        <div class="card" id="ai-summary-panel" style="display:none;border-color:var(--color-accent)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">🧠 What changed musically?</h2>
            <button class="btn btn-secondary btn-sm" data-action="open-compose">
              🎵 Compose Variation
            </button>
          </div>
          <div id="ai-summary-body"><p class="loading text-sm">Analyzing…</p></div>
        </div>

        <div class="card" id="comments-section">
          <h2 style="margin:0 0 var(--space-3) 0">💬 Discussion</h2>
          <div id="comments-list"><p class="loading text-sm">Loading comments…</p></div>
          <div id="new-comment-form" style="display:none;margin-top:var(--space-4)">
            <div class="comment-row" style="align-items:flex-start">
              <span class="comment-avatar" id="new-comment-avatar" style="background:var(--bg-overlay);color:var(--text-muted)">?</span>
              <div style="flex:1">
                <textarea id="new-comment-body" class="form-input comment-textarea" rows="3"
                          placeholder="Leave a comment…" style="resize:vertical"></textarea>
                <div class="comment-form-actions" style="margin-top:var(--space-2)">
                  <button id="comment-submit-btn" class="btn btn-primary btn-sm"
                          data-action="comment-submit" data-parent-id="">Comment</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
            <h2 style="margin:0">🔗 Mentioned In</h2>
          </div>
          <div id="xrefs-body"><p class="loading text-sm">Loading cross-references…</p></div>
        </div>

        <div style="display:flex;gap:var(--space-3);margin-top:var(--space-2);flex-wrap:wrap">
          ${commit.parentIds && commit.parentIds.length > 0
            ? `<a href="${_cfg.base}/commits/${commit.parentIds[0]}" class="btn btn-secondary btn-sm">← Parent Commit</a>`
            : ''}
          ${firstChild
            ? `<a href="${_cfg.base}/commits/${firstChild.commitId}" class="btn btn-secondary btn-sm">Child Commit →</a>`
            : ''}
          <a href="${_cfg.base}" class="btn btn-ghost btn-sm">← Back to commits</a>
        </div>
      </div>`;

    renderScorePreviews();
    void hydrateImages();
    if (typeof window.loadReactions === 'function') {
      window.loadReactions('commit', _cfg.commitId, 'commit-reactions');
    }

    const playerTracks = currentAudio.map(obj => ({
      name: obj.path.split('/').pop()!.replace(/\.[^.]+$/, ''),
      url:  `/api/v1/repos/${_cfg.repoId}/objects/${obj.objectId}/content`,
    }));
    buildInlinePlayer(playerTracks);

    void loadMuseTagsPanel(commit.tags || [], diffData, objects.length);
    void loadCrossReferences();

  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') {
      const content = document.getElementById('content');
      if (content) content.innerHTML = `<p class="error">✕ ${esc(err.message)}</p>`;
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initCommit(data: CommitPageData): void {
  _cfg = {
    repoId:    String(data['repoId']    ?? ''),
    commitId:  String(data['commitId']  ?? ''),
    base:      String(data['base']      ?? ''),
    listenUrl: String(data['listenUrl'] ?? ''),
    embedUrl:  String(data['embedUrl']  ?? ''),
    shortId:   String(data['shortId']   ?? ''),
  };
  if (!_cfg.repoId) return;
  initRepoPage({ repo_id: _cfg.repoId });
  setupEventDelegation();
  void load();
  void loadAiSummary();
  void loadComments();
}
