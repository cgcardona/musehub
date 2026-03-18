/**
 * musehub.ts — shared utilities for all MuseHub web pages.
 *
 * Sections:
 *  1. Auth helpers (token storage, apiFetch, token form)
 *  2. Formatting helpers (dates, SHA, durations)
 *  3. Repo nav (header card population, tab count badges, star toggle)
 *  4. Audio player (persistent bottom bar, playback controls)
 *  5. Commit message parser (liner-notes display helpers)
 *  6. Reactions bar
 *  7. HTMX integration hooks
 */

/* ═══════════════════════════════════════════════════════════════
 * 1. Auth helpers
 * ═══════════════════════════════════════════════════════════════ */

const API = '/api/v1';

export function getToken(): string {
  return localStorage.getItem('musehub_token') ?? '';
}

export function setToken(t: string): void {
  localStorage.setItem('musehub_token', t);
}

export function clearToken(): void {
  localStorage.removeItem('musehub_token');
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t
    ? { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }
    : {};
}

export async function apiFetch(path: string, opts: RequestInit = {}): Promise<unknown> {
  const res = await fetch(API + path, {
    ...opts,
    headers: { ...authHeaders(), ...((opts.headers as Record<string, string>) ?? {}) },
  });
  if (res.status === 401 || res.status === 403) {
    showTokenForm('Session expired or invalid token — please re-enter your JWT.');
    throw new Error('auth');
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(res.status + ': ' + body);
  }
  return res.json() as unknown;
}

export function showTokenForm(msg?: string): void {
  const tf = document.getElementById('token-form');
  const content = document.getElementById('content');
  if (tf) tf.style.display = 'block';
  if (content) content.innerHTML = '';
  if (msg) {
    const msgEl = document.getElementById('token-msg');
    if (msgEl) msgEl.textContent = msg;
  }
}

export function saveToken(): void {
  const input = document.getElementById('token-input') as HTMLInputElement | null;
  const t = input?.value.trim() ?? '';
  if (t) { setToken(t); location.reload(); }
}

/* ═══════════════════════════════════════════════════════════════
 * 2. Formatting helpers
 * ═══════════════════════════════════════════════════════════════ */

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '--';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
  return fmtDate(iso);
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.substring(0, 8) : '--';
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds || isNaN(seconds)) return '--';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function fmtSeconds(t: number): string {
  if (isNaN(t)) return '0:00';
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function escHtml(s: unknown): string {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ═══════════════════════════════════════════════════════════════
 * 3. Repo nav — header card + tab count badges
 * ═══════════════════════════════════════════════════════════════ */

interface RepoMeta {
  visibility: string;
  keySignature?: string;
  tempoBpm?: number;
  tags?: string[];
}

interface PrListResponse { pull_requests?: unknown[] }
interface IssueListResponse { issues?: unknown[] }

export async function initRepoNav(repoId: string): Promise<void> {
  try {
    const repo = await fetch(API + '/repos/' + repoId, { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : null) as Promise<RepoMeta | null>)
      .catch(() => null);

    if (repo) {
      const badge = document.getElementById('nav-visibility-badge');
      if (badge) {
        badge.textContent = repo.visibility;
        badge.className =
          'badge repo-visibility-badge badge-' +
          (repo.visibility === 'public' ? 'clean' : 'neutral');
      }
      const keyEl = document.getElementById('nav-key');
      if (keyEl && repo.keySignature) {
        keyEl.textContent = '♩ ' + repo.keySignature;
        keyEl.style.display = '';
      }
      const bpmEl = document.getElementById('nav-bpm');
      if (bpmEl && repo.tempoBpm) {
        bpmEl.textContent = repo.tempoBpm + ' BPM';
        bpmEl.style.display = '';
      }
      const tagsEl = document.getElementById('nav-tags');
      if (tagsEl && repo.tags && repo.tags.length > 0) {
        tagsEl.innerHTML = repo.tags
          .map(t => '<span class="nav-meta-tag">' + escHtml(t) + '</span>')
          .join('');
      }
    }

    if (getToken()) {
      const starBtn = document.getElementById('nav-star-btn');
      if (starBtn) starBtn.style.display = '';
    }

    void Promise.all([
      fetch(API + '/repos/' + repoId + '/pull-requests?state=open', { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : { pull_requests: [] }) as Promise<PrListResponse>)
        .catch(() => ({ pull_requests: [] as unknown[] })),
      fetch(API + '/repos/' + repoId + '/issues?state=open', { headers: authHeaders() })
        .then(r => (r.ok ? r.json() : { issues: [] }) as Promise<IssueListResponse>)
        .catch(() => ({ issues: [] as unknown[] })),
    ]).then(([prData, issueData]) => {
      const prCount = (prData.pull_requests ?? []).length;
      const issueCount = (issueData.issues ?? []).length;
      const prBadge = document.getElementById('nav-pr-count');
      if (prBadge && prCount > 0) { prBadge.textContent = String(prCount); prBadge.style.display = ''; }
      const issueBadge = document.getElementById('nav-issue-count');
      if (issueBadge && issueCount > 0) { issueBadge.textContent = String(issueCount); issueBadge.style.display = ''; }
    });
  } catch {
    // Nav enrichment is non-critical — page still works without it
  }
}

export async function toggleStar(): Promise<void> {
  const icon = document.getElementById('nav-star-icon');
  if (icon) icon.textContent = icon.textContent === '☆' ? '★' : '☆';
}

/* ═══════════════════════════════════════════════════════════════
 * 4. Audio player
 * ═══════════════════════════════════════════════════════════════ */

interface PlayerState { playing: boolean }
const _player: PlayerState = { playing: false };

function _audioEl(): HTMLAudioElement | null {
  return document.getElementById('player-audio') as HTMLAudioElement | null;
}
function _playerBar(): HTMLElement | null {
  return document.getElementById('audio-player');
}

async function _fetchBlobUrl(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: { Authorization: 'Bearer ' + getToken() },
  });
  if (!res.ok) throw new Error(String(res.status));
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function queueAudio(
  url: string,
  title: string,
  repoName: string,
): Promise<void> {
  const bar = _playerBar();
  const audio = _audioEl();
  if (!bar || !audio) return;

  bar.style.display = 'flex';
  document.body.classList.add('player-open');
  const t = document.getElementById('player-title');
  const r = document.getElementById('player-repo');
  if (t) t.textContent = title || 'Now Playing';
  if (r) r.textContent = repoName || '';

  try {
    const blobUrl = await _fetchBlobUrl(url);
    const extAudio = audio as HTMLAudioElement & { _blobUrl?: string };
    if (extAudio._blobUrl) URL.revokeObjectURL(extAudio._blobUrl);
    extAudio._blobUrl = blobUrl;
    audio.src = blobUrl;
  } catch {
    audio.src = url;
  }
  audio.load();
  void audio.play().catch(() => {});
  _player.playing = true;
  _updatePlayBtn();
}

export function togglePlay(): void {
  const audio = _audioEl();
  if (!audio?.src) return;
  if (_player.playing) { audio.pause(); _player.playing = false; }
  else { void audio.play().catch(() => {}); _player.playing = true; }
  _updatePlayBtn();
}

export function seekAudio(value: number): void {
  const audio = _audioEl();
  if (!audio || !audio.duration) return;
  audio.currentTime = (value / 100) * audio.duration;
}

export function closePlayer(): void {
  const bar = _playerBar();
  const audio = _audioEl();
  if (bar) bar.style.display = 'none';
  document.body.classList.remove('player-open');
  if (audio) {
    audio.pause();
    const extAudio = audio as HTMLAudioElement & { _blobUrl?: string };
    if (extAudio._blobUrl) { URL.revokeObjectURL(extAudio._blobUrl); extAudio._blobUrl = undefined; }
    audio.src = '';
  }
  _player.playing = false;
  _updatePlayBtn();
}

export async function downloadArtifact(url: string, filename: string): Promise<void> {
  const res = await fetch(url, {
    headers: { Authorization: 'Bearer ' + getToken() },
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

export function onTimeUpdate(): void {
  const audio = _audioEl();
  if (!audio?.duration) return;
  const pct = (audio.currentTime / audio.duration) * 100;
  const seek = document.getElementById('player-seek') as HTMLInputElement | null;
  const cur = document.getElementById('player-current');
  if (seek) seek.value = String(pct);
  if (cur) cur.textContent = fmtSeconds(audio.currentTime);
}

export function onMetadata(): void {
  const audio = _audioEl();
  const dur = document.getElementById('player-duration');
  if (audio && dur) dur.textContent = fmtSeconds(audio.duration);
}

export function onAudioEnded(): void {
  _player.playing = false;
  _updatePlayBtn();
  const seek = document.getElementById('player-seek') as HTMLInputElement | null;
  if (seek) seek.value = '0';
  const cur = document.getElementById('player-current');
  if (cur) cur.textContent = '0:00';
}

function _updatePlayBtn(): void {
  const btn = document.getElementById('player-toggle');
  if (btn) btn.innerHTML = _player.playing ? '&#9646;&#9646;' : '&#9654;';
}

/* ═══════════════════════════════════════════════════════════════
 * 5. Commit message parser
 * ═══════════════════════════════════════════════════════════════ */

interface CommitType { label: string; color: string }

const _COMMIT_TYPES: Record<string, CommitType> = {
  feat:     { label: 'feat',     color: 'var(--color-success)' },
  fix:      { label: 'fix',      color: 'var(--color-danger)' },
  refactor: { label: 'refactor', color: 'var(--color-accent)' },
  style:    { label: 'style',    color: 'var(--color-purple)' },
  docs:     { label: 'docs',     color: 'var(--text-muted)' },
  chore:    { label: 'chore',    color: 'var(--color-neutral)' },
  init:     { label: 'init',     color: 'var(--color-warning)' },
  perf:     { label: 'perf',     color: 'var(--color-orange)' },
};

interface ParsedCommit { type: string | null; scope: string | null; subject: string }

export function parseCommitMessage(msg: string | null | undefined): ParsedCommit {
  if (!msg) return { type: null, scope: null, subject: msg ?? '' };
  const m = msg.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.*)/s);
  if (!m) return { type: null, scope: null, subject: msg };
  return { type: m[1].toLowerCase(), scope: m[2] ?? null, subject: m[3] };
}

export function commitTypeBadge(type: string | null | undefined): string {
  if (!type) return '';
  const t = _COMMIT_TYPES[type] ?? { label: type, color: 'var(--text-muted)' };
  return `<span class="badge" style="background:${t.color}20;color:${t.color};border:1px solid ${t.color}40">${escHtml(t.label)}</span>`;
}

export function commitScopeBadge(scope: string | null | undefined): string {
  if (!scope) return '';
  return `<span class="badge" style="background:var(--bg-overlay);color:var(--color-purple);border:1px solid var(--color-purple-bg)">${escHtml(scope)}</span>`;
}

export function parseCommitMeta(message: string): Record<string, string> {
  const meta: Record<string, string> = {};
  const patterns = [
    /section:([\w-]+)/i,
    /track:([\w-]+)/i,
    /key:([\w#b]+\s*(?:major|minor|maj|min)?)/i,
    /tempo:(\d+)/i,
    /bpm:(\d+)/i,
  ];
  const keys = ['section', 'track', 'key', 'tempo', 'bpm'];
  patterns.forEach((re, i) => {
    const m = message.match(re);
    if (m) meta[keys[i]] = m[1];
  });
  return meta;
}

/* ═══════════════════════════════════════════════════════════════
 * 6. Reactions bar
 * ═══════════════════════════════════════════════════════════════ */

const REACTION_BAR_EMOJIS = ['🔥', '❤️', '👏', '✨', '🎵', '🎸', '🎹', '🥁'];

interface ReactionEntry { emoji: string; count: number; reacted_by_me: boolean }

export async function loadReactions(
  targetType: string,
  targetId: string,
  containerId: string,
): Promise<void> {
  const container = document.getElementById(containerId);
  if (!container) return;

  const repoId = (window as Window & { __repoId?: string }).__repoId;
  let reactions: ReactionEntry[] = [];
  try {
    reactions = (await apiFetch(
      '/repos/' + repoId + '/reactions?target_type=' +
        encodeURIComponent(targetType) +
        '&target_id=' +
        encodeURIComponent(targetId),
    )) as ReactionEntry[];
  } catch {
    reactions = [];
  }

  const countMap: Record<string, number> = {};
  const reactedMap: Record<string, boolean> = {};
  (Array.isArray(reactions) ? reactions : []).forEach(r => {
    countMap[r.emoji] = r.count;
    reactedMap[r.emoji] = r.reacted_by_me;
  });

  const safeTT = targetType.replace(/'/g, '');
  const safeTI = String(targetId).replace(/'/g, '');
  const safeCID = containerId.replace(/'/g, '');

  container.innerHTML =
    '<div class="reaction-bar">' +
    REACTION_BAR_EMOJIS.map(emoji => {
      const count = countMap[emoji] ?? 0;
      const active = reactedMap[emoji] ? ' reaction-btn--active' : '';
      const countHtml =
        count > 0 ? '<span class="reaction-count">' + count + '</span>' : '';
      return (
        '<button class="reaction-btn' +
        active +
        '" ' +
        'onclick="toggleReaction(\'' +
        safeTT +
        "','" +
        safeTI +
        "','" +
        emoji +
        "','" +
        safeCID +
        '\')" ' +
        'title="' +
        emoji +
        '">' +
        emoji +
        countHtml +
        '</button>'
      );
    }).join('') +
    '</div>';
}

export async function toggleReaction(
  targetType: string,
  targetId: string,
  emoji: string,
  containerId: string,
): Promise<void> {
  if (!getToken()) { showTokenForm('Sign in to react'); return; }
  const repoId = (window as Window & { __repoId?: string }).__repoId;
  try {
    await apiFetch('/repos/' + repoId + '/reactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_type: targetType, target_id: String(targetId), emoji }),
    });
    await loadReactions(targetType, targetId, containerId);
  } catch { /* reaction toggle is non-critical */ }
}

/* ═══════════════════════════════════════════════════════════════
 * 7. HTMX integration hooks
 * ═══════════════════════════════════════════════════════════════ */

document.addEventListener('htmx:configRequest', (evt: Event) => {
  const token = getToken();
  if (token) (evt as CustomEvent).detail.headers['Authorization'] = 'Bearer ' + token;
});

/** Read repo_id from the DOM — repo_nav.html embeds it as a data-repo-id attribute. */
function _repoIdFromDom(): string | null {
  return document.getElementById('repo-header')?.getAttribute('data-repo-id') ?? null;
}

/* ═══════════════════════════════════════════════════════════════
 * Global surface — attach exports to window for inline handlers
 * ═══════════════════════════════════════════════════════════════ */

declare global {
  interface Window {
    __repoId?: string;
    getToken: () => string;
    setToken: (t: string) => void;
    clearToken: () => void;
    saveToken: () => void;
    showTokenForm: (msg?: string) => void;
    apiFetch: (path: string, opts?: RequestInit) => Promise<unknown>;
    authHeaders: () => Record<string, string>;
    fmtDate: (iso: string | null | undefined) => string;
    fmtRelative: (iso: string | null | undefined) => string;
    shortSha: (sha: string | null | undefined) => string;
    fmtDuration: (seconds: number | null | undefined) => string;
    fmtSeconds: (t: number) => string;
    escHtml: (s: unknown) => string;
    initRepoNav: (repoId: string) => Promise<void>;
    toggleStar: () => Promise<void>;
    queueAudio: (url: string, title: string, repoName: string) => Promise<void>;
    togglePlay: () => void;
    seekAudio: (value: number) => void;
    closePlayer: () => void;
    downloadArtifact: (url: string, filename: string) => Promise<void>;
    onTimeUpdate: () => void;
    onMetadata: () => void;
    onAudioEnded: () => void;
    parseCommitMessage: (msg: string | null | undefined) => ParsedCommit;
    commitTypeBadge: (type: string | null | undefined) => string;
    commitScopeBadge: (scope: string | null | undefined) => string;
    parseCommitMeta: (message: string) => Record<string, string>;
    loadReactions: (targetType: string, targetId: string, containerId: string) => Promise<void>;
    toggleReaction: (targetType: string, targetId: string, emoji: string, containerId: string) => Promise<void>;
    // Page-module helpers exposed for inline onclick handlers
    showTemplatePicker?: () => void;
    selectTemplate?: (tplId: string) => void;
    toggleIssueSelect?: (issueId: string, checked: boolean) => void;
    deselectAll?: () => void;
    bulkClose?: () => void;
    bulkReopen?: () => void;
    bulkAssignLabel?: () => void;
    bulkAssignMilestone?: () => void;
    bodyPreview?: (text: string, maxLen?: number) => string;
    switchTab?: (tab: string, filter?: string, page?: number) => void;
    renderFromObjectId?: (repoId: string, objectId: string, container: HTMLElement | null) => void;
    renderFromUrl?: (url: string, container: HTMLElement | null) => void;
    // Lucide global (loaded from CDN)
    lucide?: { createIcons: () => void };
    // WaveSurfer global (loaded from CDN)
    WaveSurfer?: { create: (opts: Record<string, unknown>) => unknown };
  }
}

/* ═══════════════════════════════════════════════════════════════
 * 8. Global page initialisation (replaces base.html inline script)
 * ═══════════════════════════════════════════════════════════════ */

async function loadNotifBadge(): Promise<void> {
  if (!getToken()) return;
  try {
    const data = await apiFetch('/notifications') as Array<{ is_read: boolean }>;
    const unread = Array.isArray(data) ? data.filter((n) => !n.is_read).length : 0;
    const badge = document.getElementById('nav-notif-badge');
    if (badge) {
      badge.textContent = unread > 99 ? '99+' : String(unread);
      (badge as HTMLElement).style.display = unread > 0 ? 'flex' : 'none';
    }
  } catch (_) { /* silent fail */ }
}

function initPageGlobals(): void {
  // Show sign-out button when JWT is present
  if (getToken()) {
    const btn = document.getElementById('signout-btn');
    if (btn) (btn as HTMLElement).style.display = '';
  }
  // Refresh notification badge
  loadNotifBadge();
  // Hydrate Lucide icons (CDN global)
  if (typeof (window as unknown as Record<string, unknown>).lucide === 'object') {
    (window as unknown as { lucide: { createIcons: () => void } }).lucide.createIcons();
  }
  // Initialize repo nav if the repo header card is present on this page
  const repoId = _repoIdFromDom();
  if (repoId) void initRepoNav(repoId);
  // Dispatch to the active page module via the #page-data JSON element
  const pageDataEl = document.getElementById('page-data');
  if (pageDataEl) {
    try {
      const pageData = JSON.parse(pageDataEl.textContent ?? '{}') as Record<string, unknown>;
      dispatchPageModule(pageData);
    } catch (_) { /* malformed JSON — ignore */ }
  }
}

function dispatchPageModule(data: Record<string, unknown>): void {
  const page = data['page'] as string | undefined;
  if (!page) return;
  // Page modules register themselves on window.MusePages
  const pages = (window as unknown as { MusePages?: Record<string, (d: Record<string, unknown>) => void> }).MusePages;
  if (pages && typeof pages[page] === 'function') {
    pages[page](data);
  }
}

// Run on initial hard load
document.addEventListener('DOMContentLoaded', initPageGlobals);
// Re-run after every HTMX navigation — htmx:afterSettle fires after scripts
// in the swapped content have run, so page modules and DOM data are ready.
document.addEventListener('htmx:afterSettle', initPageGlobals);

window.getToken = getToken;
window.setToken = setToken;
window.clearToken = clearToken;
window.saveToken = saveToken;
window.showTokenForm = showTokenForm;
window.apiFetch = apiFetch;
window.authHeaders = authHeaders;
window.fmtDate = fmtDate;
window.fmtRelative = fmtRelative;
window.shortSha = shortSha;
window.fmtDuration = fmtDuration;
window.fmtSeconds = fmtSeconds;
window.escHtml = escHtml;
window.initRepoNav = initRepoNav;
window.toggleStar = toggleStar;
window.queueAudio = queueAudio;
window.togglePlay = togglePlay;
window.seekAudio = seekAudio;
window.closePlayer = closePlayer;
window.downloadArtifact = downloadArtifact;
window.onTimeUpdate = onTimeUpdate;
window.onMetadata = onMetadata;
window.onAudioEnded = onAudioEnded;
window.parseCommitMessage = parseCommitMessage;
window.commitTypeBadge = commitTypeBadge;
window.commitScopeBadge = commitScopeBadge;
window.parseCommitMeta = parseCommitMeta;
window.loadReactions = loadReactions;
window.toggleReaction = toggleReaction;
