/**
 * user-profile.ts — MuseHub user profile page module.
 *
 * Fetches and renders the full user profile from the JSON API.
 * Handles: profile header, heatmap, badges, pinned repos, tabs
 * (repos, stars, followers, following, activity).
 *
 * Data expected in #page-data:
 *   { "page": "user-profile", "username": "..." }
 *
 * Registered as: window.MusePages['user-profile']
 */

export interface UserProfileData {
  page?: string;
  username?: string;
  [key: string]: unknown;
}

function esc(s: unknown): string {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtRelative(ts: string | null | undefined): string {
  if (!ts) return '';
  const d = new Date(ts);
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

interface HeatmapDay { date: string; count: number; intensity: number; }
interface HeatmapStats { days: HeatmapDay[]; totalContributions: number; longestStreak: number; currentStreak: number; }

function renderHeatmap(stats: HeatmapStats): void {
  const days = stats.days ?? [];
  const cols: HeatmapDay[][] = [];
  let col: HeatmapDay[] = [];
  for (const day of days) {
    col.push(day);
    if (col.length === 7) { cols.push(col); col = []; }
  }
  if (col.length) cols.push(col);

  const colsHtml = cols.map((c) => {
    const cells = c.map((d) =>
      `<div class="heatmap-cell" data-intensity="${d.intensity}" title="${esc(d.date)}: ${d.count} commit${d.count !== 1 ? 's' : ''}"></div>`
    ).join('');
    return `<div class="heatmap-col">${cells}</div>`;
  }).join('');

  const legend = [0, 1, 2, 3].map((n) => `<div class="heatmap-cell" data-intensity="${n}" style="display:inline-block"></div>`).join('');

  const el = document.getElementById('heatmap-section');
  if (el) el.innerHTML = `
    <div class="card">
      <h2 style="margin-bottom:12px">📈 Contribution Activity</h2>
      <div class="heatmap-grid">${colsHtml}</div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;color:var(--text-muted)">
        Less ${legend} More &nbsp;·&nbsp; ${stats.totalContributions ?? 0} contributions in the last year
        &nbsp;·&nbsp; Longest streak: ${stats.longestStreak ?? 0} days
        &nbsp;·&nbsp; Current streak: ${stats.currentStreak ?? 0} days
      </div>
    </div>`;
}

interface Badge { name: string; description: string; icon: string; earned: boolean; }

function renderBadges(badges: Badge[]): void {
  const cards = badges.map((b) => {
    const cls = b.earned ? 'earned' : 'unearned';
    return `<div class="badge-card ${cls}" title="${esc(b.description)}">
      <div class="badge-icon">${esc(b.icon)}</div>
      <div class="badge-info">
        <div class="badge-name">${esc(b.name)}</div>
        <div class="badge-desc">${esc(b.description)}</div>
      </div>
    </div>`;
  }).join('');
  const earned = badges.filter((b) => b.earned).length;
  const el = document.getElementById('badges-section');
  if (el) el.innerHTML = `<div class="card"><h2 style="margin-bottom:12px">🏆 Achievements (${earned}/${badges.length})</h2><div class="badge-grid">${cards}</div></div>`;
}

interface PinnedRepo { owner: string; slug: string; name: string; description?: string; primaryGenre?: string; language?: string; starsCount?: number; forksCount?: number; }

function renderPinned(pinnedRepos: PinnedRepo[], _isOwner: boolean): void {
  if (!pinnedRepos?.length) return;
  const cards = pinnedRepos.map((r) => {
    const genre = r.primaryGenre ? `<span>🎵 ${esc(r.primaryGenre)}</span>` : '';
    const lang  = r.language ? `<span>🔤 ${esc(r.language)}</span>` : '';
    return `<div class="pinned-card">
      <h3><a href="/${esc(r.owner)}/${esc(r.slug)}">${esc(r.name)}</a></h3>
      ${r.description ? `<p class="pinned-desc">${esc(r.description)}</p>` : ''}
      <div class="pinned-meta">${genre}${lang}<span>⭐ ${r.starsCount ?? 0}</span><span>🍴 ${r.forksCount ?? 0}</span></div>
    </div>`;
  }).join('');
  const el = document.getElementById('pinned-section');
  if (el) el.innerHTML = `<div class="card"><h2 style="margin-bottom:12px">📌 Pinned</h2><div class="pinned-grid">${cards}</div></div>`;
}

interface ProfileData {
  username: string; displayName?: string; bio?: string; location?: string;
  website?: string; avatarUrl?: string; avatarColor?: string;
  followersCount?: number; followingCount?: number; starsCount?: number;
  publicReposCount?: number; createdAt?: string; isFollowing?: boolean;
  repos?: RepoData[];
  contributionGraph?: Array<{ date: string; count: number }>;
}
interface EnhancedData { heatmap?: HeatmapStats; badges?: Badge[]; pinnedRepos?: PinnedRepo[]; }
interface RepoData { owner: string; slug: string; name: string; description?: string; primaryGenre?: string; language?: string; starsCount?: number; forksCount?: number; updatedAt?: string; isPrivate?: boolean; }

let currentUsername = '';
let currentTab = 'repos';
let cachedRepos: RepoData[] = [];

function renderProfileHeader(profile: ProfileData): boolean {
  const initial = (profile.displayName ?? profile.username ?? '?')[0].toUpperCase();
  const avatarHtml = profile.avatarUrl
    ? `<div class="avatar-lg"><img src="${esc(profile.avatarUrl)}" alt="${esc(profile.username)}" /></div>`
    : `<div class="avatar-lg" style="background:${esc(profile.avatarColor ?? '#1f6feb')}">${esc(initial)}</div>`;

  const isOwner = window.getToken ? !!window.getToken() : false;

  const el = document.getElementById('profile-hdr');
  if (el) el.innerHTML = `
    <div class="profile-hdr">
      ${avatarHtml}
      <div>
        <h1 style="margin:0 0 4px">${esc(profile.displayName ?? profile.username)}</h1>
        <div style="font-size:14px;color:var(--text-muted);margin-bottom:8px">@${esc(profile.username)}</div>
        ${profile.bio ? `<p style="font-size:14px;margin-bottom:8px">${esc(profile.bio)}</p>` : ''}
        <div style="display:flex;gap:16px;font-size:13px;color:var(--text-muted);flex-wrap:wrap">
          ${profile.location ? `<span>📍 ${esc(profile.location)}</span>` : ''}
          ${profile.website ? `<a href="${esc(profile.website)}" target="_blank" rel="noopener noreferrer">🔗 ${esc(profile.website)}</a>` : ''}
          <span>👥 <strong>${profile.followersCount ?? 0}</strong> followers · <strong>${profile.followingCount ?? 0}</strong> following</span>
          <span>⭐ ${profile.starsCount ?? 0} stars</span>
        </div>
      </div>
    </div>`;
  return isOwner;
}

function renderReposTab(repos: RepoData[]): void {
  const tabContent = document.getElementById('tab-content');
  if (!tabContent) return;
  if (!repos.length) { tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No repositories yet.</p>'; return; }
  tabContent.innerHTML = repos.map((r) => `
    <div class="repo-card" style="margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <a href="/${esc(r.owner)}/${esc(r.slug)}" style="font-weight:600;font-size:14px">${esc(r.name)}</a>
        ${r.isPrivate ? '<span class="badge badge-secondary">Private</span>' : ''}
      </div>
      ${r.description ? `<p style="font-size:13px;color:var(--text-muted);margin:4px 0 0">${esc(r.description)}</p>` : ''}
      <div style="display:flex;gap:12px;font-size:12px;color:var(--text-muted);margin-top:8px;flex-wrap:wrap">
        ${r.primaryGenre ? `<span>🎵 ${esc(r.primaryGenre)}</span>` : ''}
        ${r.language ? `<span>🔤 ${esc(r.language)}</span>` : ''}
        <span>⭐ ${r.starsCount ?? 0}</span>
        <span>🍴 ${r.forksCount ?? 0}</span>
        ${r.updatedAt ? `<span>Updated ${fmtRelative(r.updatedAt)}</span>` : ''}
      </div>
    </div>`).join('');
}

async function loadStarsTab(): Promise<void> {
  const tabContent = document.getElementById('tab-content');
  if (!tabContent) return;
  tabContent.innerHTML = '<p class="loading">Loading starred repos…</p>';
  try {
    const data = await fetch('/api/v1/users/' + currentUsername + '/starred').then((r) => r.json()) as RepoData[];
    if (!data.length) { tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No starred repos yet.</p>'; return; }
    renderReposTab(data);
  } catch (_) { tabContent.innerHTML = '<p class="error">Failed to load starred repos.</p>'; }
}

async function loadSocialTab(type: 'followers' | 'following'): Promise<void> {
  const tabContent = document.getElementById('tab-content');
  if (!tabContent) return;
  tabContent.innerHTML = `<p class="loading">Loading ${type}…</p>`;
  try {
    const url = type === 'followers' ? '/api/v1/users/' + currentUsername + '/followers-list' : '/api/v1/users/' + currentUsername + '/following-list';
    const data = await fetch(url).then((r) => r.json()) as Array<{ username: string; displayName?: string; bio?: string; avatarColor?: string }>;
    if (!data.length) { tabContent.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:24px">No ${type} yet.</p>`; return; }
    tabContent.innerHTML = data.map((u) => {
      const init = (u.displayName ?? u.username ?? '?')[0].toUpperCase();
      return `<div style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-default)">
        <div style="width:36px;height:36px;border-radius:50%;background:${esc(u.avatarColor ?? '#1f6feb')};display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;flex-shrink:0">${esc(init)}</div>
        <div><a href="/${esc(u.username)}" style="font-weight:600">${esc(u.displayName ?? u.username)}</a>
          ${u.bio ? `<p style="font-size:12px;color:var(--text-muted);margin:2px 0 0">${esc(u.bio)}</p>` : ''}</div>
      </div>`;
    }).join('');
  } catch (_) { tabContent.innerHTML = `<p class="error">Failed to load ${type}.</p>`; }
}

async function loadActivityTab(filter: string, page: number): Promise<void> {
  const tabContent = document.getElementById('tab-content');
  if (!tabContent) return;
  tabContent.innerHTML = '<p class="loading">Loading activity…</p>';
  try {
    const data = await fetch(`/api/v1/users/${currentUsername}/activity?filter=${filter}&page=${page}&limit=20`).then((r) => r.json()) as { events: Array<{ type: string; timestamp: string; description?: string; repo?: string }>; total: number };
    const events = data.events ?? [];
    if (!events.length) { tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No activity yet.</p>'; return; }
    const rows = events.map((e) => `
      <div class="activity-row">
        <span class="activity-icon">📝</span>
        <div class="activity-body">
          <div class="activity-description">${esc(e.description ?? e.type)}</div>
          <div class="activity-meta">${fmtRelative(e.timestamp)}${e.repo ? ` · <a href="/${esc(e.repo)}">${esc(e.repo)}</a>` : ''}</div>
        </div>
      </div>`).join('');
    const totalPages = Math.ceil((data.total ?? 0) / 20);
    const pageBtns = totalPages > 1 ? `
      <div class="activity-pagination">
        ${page > 1 ? `<button class="btn btn-secondary" data-activity-page="${page - 1}" data-activity-filter="${filter}">&larr; Prev</button>` : ''}
        <span class="activity-pagination-label">Page ${page} of ${totalPages}</span>
        ${page < totalPages ? `<button class="btn btn-secondary" data-activity-page="${page + 1}" data-activity-filter="${filter}">Next &rarr;</button>` : ''}
      </div>` : '';
    tabContent.innerHTML = rows + pageBtns;
    tabContent.querySelectorAll<HTMLButtonElement>('[data-activity-page]').forEach((btn) => {
      btn.addEventListener('click', () => {
        void loadActivityTab(btn.dataset.activityFilter ?? 'all', Number(btn.dataset.activityPage));
      });
    });
  } catch (_) { tabContent.innerHTML = '<p class="error">Failed to load activity.</p>'; }
}

export function switchTab(tab: string, filter = 'all', page = 1): void {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach((b) => {
    (b as HTMLElement).classList.toggle('active', (b as HTMLElement).dataset.tab === tab);
  });
  switch (tab) {
    case 'repos':     renderReposTab(cachedRepos); break;
    case 'stars':     void loadStarsTab(); break;
    case 'followers': void loadSocialTab('followers'); break;
    case 'following': void loadSocialTab('following'); break;
    case 'activity':  void loadActivityTab(filter, page); break;
  }
}

export async function initUserProfile(data: UserProfileData): Promise<void> {
  const username = data.username ?? '';
  if (!username) return;
  currentUsername = username;

  const profileHdr    = document.getElementById('profile-hdr');
  const tabsSection   = document.getElementById('tabs-section');

  if (profileHdr) profileHdr.innerHTML = '<p class="loading">Loading profile…</p>';

  try {
    const [profileData, enhancedData] = await Promise.all([
      fetch('/api/v1/users/' + username).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }) as Promise<ProfileData>,
      fetch('/' + username + '?format=json').then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); }) as Promise<EnhancedData>,
    ]);

    const isOwner = renderProfileHeader(profileData);
    renderHeatmap(enhancedData.heatmap ?? {
      days: (profileData.contributionGraph ?? []).map((d) => ({ ...d, intensity: d.count === 0 ? 0 : d.count <= 3 ? 1 : d.count <= 6 ? 2 : 3 })),
      totalContributions: 0, longestStreak: 0, currentStreak: 0,
    });
    renderBadges(enhancedData.badges ?? []);
    renderPinned(enhancedData.pinnedRepos ?? [], isOwner);

    cachedRepos = profileData.repos ?? [];
    if (tabsSection) {
      tabsSection.removeAttribute('hidden');
      tabsSection.querySelectorAll<HTMLElement>('.tab-btn').forEach((btn) => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab ?? 'repos'));
      });
    }
    renderReposTab(cachedRepos);
  } catch (e) {
    if (profileHdr) profileHdr.innerHTML = `<p class="error">✕ Could not load profile for @${esc(username)}: ${esc(e instanceof Error ? e.message : String(e))}</p>`;
  }
}
