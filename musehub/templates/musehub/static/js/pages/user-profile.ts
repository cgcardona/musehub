/**
 * user-profile.ts — Multi-domain MuseHub profile page.
 *
 * Renders: hero, domain stats bar, multi-domain heatmap, pinned repos,
 * achievements, and tabbed repo/stars/followers/activity sections.
 *
 * All data fetched client-side from:
 *  - /api/v1/users/{username}          → ProfileData
 *  - /{username}?format=json           → EnhancedData (badges, heatmap, domain_stats)
 */

export interface UserProfileData { page?: string; username?: string; [key: string]: unknown; }

// ── Utilities ─────────────────────────────────────────────────────────────────

function esc(s: unknown): string {
  if (!s && s !== 0) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function $(id: string): HTMLElement | null { return document.getElementById(id); }

function timeAgo(ts: string | null | undefined): string {
  if (!ts) return '';
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

// Domain viewer type → accent color
function domainColor(viewerType: string): string {
  if (viewerType === 'symbol_graph') return '#58a6ff';  // code — blue
  if (viewerType === 'piano_roll')   return '#bc8cff';  // MIDI — purple
  return '#8b949e';  // generic
}
function domainIcon(viewerType: string): string {
  if (viewerType === 'symbol_graph') return '⬡';
  if (viewerType === 'piano_roll')   return '♪';
  return '◈';
}
function domainLabel(viewerType: string, name: string): string {
  if (name && name !== 'Unknown') return name;
  if (viewerType === 'symbol_graph') return 'Code';
  if (viewerType === 'piano_roll')   return 'MIDI';
  return 'Generic';
}

// Derive avatar background from username hash
function avatarColor(username: string): string {
  const COLORS = ['#1f6feb','#238636','#da3633','#9e6a03','#7d3a8a','#1a7f74','#cf5c37','#206c8f'];
  let h = 0;
  for (let i = 0; i < username.length; i++) h = (h * 31 + username.charCodeAt(i)) | 0;
  return COLORS[Math.abs(h) % COLORS.length];
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface HeatmapDay {
  date: string; count: number; intensity: number;
  domainCounts?: Record<string, number>;
  dominantDomain?: string | null;
}
interface HeatmapStats {
  days: HeatmapDay[];
  totalContributions: number;
  longestStreak: number;
  currentStreak: number;
}
interface DomainStat {
  domainId: string | null;
  domainName: string;
  scopedId: string | null;
  viewerType: string;
  repoCount: number;
  commitCount: number;
}
interface Badge { id: string; name: string; description: string; icon: string; earned: boolean; }
interface PinnedRepo {
  owner: string; slug: string; name: string; description?: string;
  starCount?: number; forkCount?: number; commitCount?: number;
  domainId?: string; domainName?: string; domainViewerType?: string;
  language?: string; primaryGenre?: string; tags?: string[];
}
interface ProfileData {
  username: string; displayName?: string; bio?: string; location?: string;
  websiteUrl?: string; avatarUrl?: string; avatarColor?: string;
  followersCount?: number; followingCount?: number; starsCount?: number;
  publicReposCount?: number; createdAt?: string; isFollowing?: boolean;
  repos?: RepoData[];
}
interface EnhancedData {
  heatmap?: HeatmapStats;
  domainStats?: DomainStat[];
  badges?: Badge[];
  pinnedRepos?: PinnedRepo[];
}
interface RepoData {
  owner: string; slug: string; name: string; description?: string;
  primaryGenre?: string; language?: string;
  starsCount?: number; forksCount?: number; updatedAt?: string;
  isPrivate?: boolean;
  domainId?: string; domainViewerType?: string; domainName?: string;
}

// ── Module state ──────────────────────────────────────────────────────────────

let _username = '';
let _cachedRepos: RepoData[] = [];
let _domainStats: DomainStat[] = [];
let _currentTab = 'repos';

// ── Hero section ──────────────────────────────────────────────────────────────

function renderHero(profile: ProfileData, enhanced: EnhancedData): void {
  const color = profile.avatarColor || avatarColor(profile.username);

  // Avatar
  const avatarEl = $('prof-avatar');
  const glowEl   = $('prof-avatar-glow');
  const initialEl = $('prof-avatar-initial');
  if (avatarEl) {
    if (profile.avatarUrl) {
      avatarEl.innerHTML = `<img src="${esc(profile.avatarUrl)}" alt="${esc(profile.username)}" />`;
    } else {
      avatarEl.style.background = color;
      if (initialEl) initialEl.textContent = (profile.displayName || profile.username)[0].toUpperCase();
    }
  }
  if (glowEl) glowEl.style.background = color;

  // Name
  const nameEl = $('prof-display-name');
  const userEl = $('prof-username');
  if (nameEl) nameEl.textContent = profile.displayName || profile.username;
  if (userEl) userEl.textContent = profile.displayName ? `@${profile.username}` : '';

  const verifiedEl = $('prof-verified');
  if (verifiedEl && (profile as any).isVerified) verifiedEl.style.display = 'inline';

  // Bio
  const bioEl = $('prof-bio');
  if (bioEl && profile.bio) { bioEl.textContent = profile.bio; bioEl.style.display = 'block'; }

  // Meta
  const locationEl = $('prof-location');
  if (locationEl && profile.location) {
    locationEl.querySelector('span')!.textContent = profile.location;
    locationEl.style.display = 'inline-flex';
  }
  const websiteEl = $('prof-website');
  const websiteLinkEl = $('prof-website-link') as HTMLAnchorElement | null;
  if (websiteEl && websiteLinkEl && profile.websiteUrl) {
    websiteLinkEl.href = profile.websiteUrl;
    websiteLinkEl.textContent = profile.websiteUrl.replace(/^https?:\/\//, '');
    websiteEl.style.display = 'inline-flex';
  }

  // Social stats
  const followersCountEl = $('prof-followers-count');
  const followingCountEl = $('prof-following-count');
  const reposCountEl     = $('prof-repos-count');
  if (followersCountEl) followersCountEl.textContent = String(profile.followersCount ?? 0);
  if (followingCountEl) followingCountEl.textContent = String(profile.followingCount ?? 0);
  if (reposCountEl)     reposCountEl.textContent     = String(profile.publicReposCount ?? profile.repos?.length ?? 0);

  // Domain pills
  const pillsEl = $('prof-domain-pills');
  if (pillsEl && enhanced.domainStats?.length) {
    pillsEl.innerHTML = enhanced.domainStats.map(ds => {
      const col   = domainColor(ds.viewerType);
      const icon  = domainIcon(ds.viewerType);
      const label = domainLabel(ds.viewerType, ds.domainName);
      const scopedId = ds.scopedId ?? `@unknown/${ds.domainId?.slice(0, 8)}`;
      return `<a class="prof-domain-pill" href="/domains/${esc(scopedId)}"
        style="--dpill-color:${col}" title="${esc(scopedId)}">
        <span class="prof-domain-pill__icon">${icon}</span>
        <span class="prof-domain-pill__name">${esc(label)}</span>
      </a>`;
    }).join('');
  }
}

// ── Domain stats bar ──────────────────────────────────────────────────────────

function renderDomainBar(domainStats: DomainStat[]): void {
  const el = $('prof-domain-bar');
  if (!el || !domainStats.length) return;
  const totalCommits = domainStats.reduce((s, d) => s + d.commitCount, 0) || 1;
  el.innerHTML = domainStats.map(ds => {
    const col   = domainColor(ds.viewerType);
    const icon  = domainIcon(ds.viewerType);
    const label = domainLabel(ds.viewerType, ds.domainName);
    const pct   = Math.round(ds.commitCount / totalCommits * 100);
    const scoped = ds.scopedId ?? ds.domainId ?? '';
    return `<div class="prof-dstat-card" style="--dstat-color:${col}">
      <div class="prof-dstat-icon">${icon}</div>
      <div class="prof-dstat-body">
        <div class="prof-dstat-name">
          <span class="prof-dstat-label">${esc(label)}</span>
          ${scoped ? `<code class="prof-dstat-scoped">${esc(scoped)}</code>` : ''}
        </div>
        <div class="prof-dstat-nums">
          <span><strong>${ds.repoCount}</strong> repo${ds.repoCount !== 1 ? 's' : ''}</span>
          <span class="prof-dstat-dot">·</span>
          <span><strong>${ds.commitCount.toLocaleString()}</strong> commits</span>
          <span class="prof-dstat-dot">·</span>
          <span class="prof-dstat-pct">${pct}% of activity</span>
        </div>
        <div class="prof-dstat-bar-track">
          <div class="prof-dstat-bar" style="width:${pct}%;background:${col}"></div>
        </div>
      </div>
    </div>`;
  }).join('');
  el.style.display = 'grid';
}

// ── Multi-domain heatmap ──────────────────────────────────────────────────────

// Build a mapping from domain_id → color using the domain stats
let _domainColorMap: Record<string, string> = {};

function renderHeatmap(stats: HeatmapStats, domainStats: DomainStat[]): void {
  // Build domain color map
  _domainColorMap = {};
  for (const ds of domainStats) {
    if (ds.domainId) _domainColorMap[ds.domainId] = domainColor(ds.viewerType);
  }

  const days = stats.days ?? [];

  // Group days into 7-day columns (Sun–Sat)
  const cols: HeatmapDay[][] = [];
  let col: HeatmapDay[] = [];
  for (const day of days) {
    col.push(day);
    if (col.length === 7) { cols.push(col); col = []; }
  }
  if (col.length) cols.push(col);

  // Month labels
  const monthsEl = $('prof-heatmap-months');
  if (monthsEl) {
    const months: { name: string; colIdx: number }[] = [];
    let lastMonth = '';
    cols.forEach((c, ci) => {
      const m = new Date(c[0]?.date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short' });
      if (m !== lastMonth) { months.push({ name: m, colIdx: ci }); lastMonth = m; }
    });
    monthsEl.innerHTML = months.map(m =>
      `<span class="prof-heatmap-month" style="left:${m.colIdx * 14}px">${esc(m.name)}</span>`
    ).join('');
  }

  // Day labels (left side — Mon/Wed/Fri)
  const dayLabels = ['', 'Mon', '', 'Wed', '', 'Fri', ''].map((lbl, i) =>
    `<span class="prof-heatmap-daylbl">${lbl}</span>`
  ).join('');

  // Grid cells
  const colsHtml = cols.map(c => {
    const cells = c.map(d => {
      const bg = cellColor(d);
      const tip = buildTooltip(d, domainStats);
      return `<div class="prof-heatmap-cell" style="background:${bg}" title="${esc(tip)}" data-date="${esc(d.date)}" data-count="${d.count}"></div>`;
    }).join('');
    return `<div class="prof-heatmap-col">${cells}</div>`;
  }).join('');

  const gridEl = $('prof-heatmap-grid');
  if (gridEl) {
    gridEl.innerHTML = `<div class="prof-heatmap-days">${dayLabels}</div><div class="prof-heatmap-cols">${colsHtml}</div>`;
  }

  // Legend
  const legendEl = $('prof-heatmap-legend');
  if (legendEl) {
    // Show a domain color swatch per domain
    const swatches = domainStats.map(ds => {
      const col   = domainColor(ds.viewerType);
      const label = domainLabel(ds.viewerType, ds.domainName);
      return `<span class="prof-heatmap-legend-item">
        <span class="prof-heatmap-swatch" style="background:${col}"></span>
        <span>${esc(label)}</span>
      </span>`;
    }).join('');
    legendEl.innerHTML = swatches;
  }

  // Stats bar
  const statsEl = $('prof-heatmap-stats');
  if (statsEl) {
    statsEl.innerHTML = `
      <span><strong>${stats.totalContributions.toLocaleString()}</strong> contributions in the last year</span>
      <span class="prof-hm-stat-dot">·</span>
      <span>🔥 Longest streak: <strong>${stats.longestStreak}</strong> days</span>
      <span class="prof-hm-stat-dot">·</span>
      <span>Current streak: <strong>${stats.currentStreak}</strong> days</span>
    `;
  }
}

function cellColor(d: HeatmapDay): string {
  if (d.count === 0) return 'var(--bg-overlay)';
  // Color by dominant domain
  const domColor = d.dominantDomain ? (_domainColorMap[d.dominantDomain] ?? '#39d353') : '#39d353';
  // Vary intensity
  const intensities = ['', '33', '66', 'bb', 'ff'];
  const alpha = intensities[Math.min(4, d.intensity + 1)] ?? 'ff';
  // If it's a hex color like #58a6ff, append alpha
  if (domColor.startsWith('#') && domColor.length === 7) {
    return domColor + alpha;
  }
  return domColor;
}

function buildTooltip(d: HeatmapDay, domainStats: DomainStat[]): string {
  const dateStr = new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  if (d.count === 0) return `No contributions on ${dateStr}`;
  const dc = d.domainCounts ?? {};
  const parts = Object.entries(dc).map(([did, cnt]) => {
    const ds = domainStats.find(s => s.domainId === did);
    const label = ds ? domainLabel(ds.viewerType, ds.domainName) : 'Unknown';
    return `${cnt} ${label}`;
  });
  const detail = parts.length ? ` (${parts.join(', ')})` : '';
  return `${d.count} contribution${d.count !== 1 ? 's' : ''}${detail} on ${dateStr}`;
}

// ── Pinned repos ──────────────────────────────────────────────────────────────

function renderPinned(pinnedRepos: PinnedRepo[]): void {
  const section = $('prof-pinned-section');
  const grid    = $('prof-pinned-grid');
  const meta    = $('prof-pinned-meta');
  if (!section || !grid || !pinnedRepos?.length) return;

  if (meta) meta.textContent = `${pinnedRepos.length} of 6`;

  grid.innerHTML = pinnedRepos.map(r => {
    const col   = domainColor(r.domainViewerType ?? 'generic');
    const icon  = domainIcon(r.domainViewerType ?? 'generic');
    const label = domainLabel(r.domainViewerType ?? 'generic', r.domainName ?? '');

    // Tag pills (first 4, strip prefix)
    const tagPills = (r.tags ?? []).slice(0, 4).map(t => {
      const display = t.includes(':') ? t.split(':').slice(1).join(':') : t;
      return `<span class="prof-repo-tag">${esc(display)}</span>`;
    }).join('');

    return `<a class="prof-pinned-card" href="/${esc(r.owner)}/${esc(r.slug)}" style="--card-accent:${col}">
      <div class="prof-pinned-card__header">
        <span class="prof-pinned-domain-badge" style="background:color-mix(in srgb,${col} 15%,transparent);color:${col};border-color:color-mix(in srgb,${col} 30%,transparent)">
          ${icon} ${esc(label)}
        </span>
        <span class="prof-pinned-privacy"></span>
      </div>
      <div class="prof-pinned-card__body">
        <h3 class="prof-pinned-name">${esc(r.name)}</h3>
        <p class="prof-pinned-desc">${esc(r.description ?? '')}</p>
      </div>
      ${tagPills ? `<div class="prof-pinned-tags">${tagPills}</div>` : ''}
      <div class="prof-pinned-card__footer">
        <span class="prof-pinned-stat" title="Stars">
          <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          ${r.starCount ?? 0}
        </span>
        <span class="prof-pinned-stat" title="Forks">
          <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>
          ${r.forkCount ?? 0}
        </span>
        <span class="prof-pinned-stat" title="Commits">
          <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><line x1="3" y1="12" x2="9" y2="12"/><line x1="15" y1="12" x2="21" y2="12"/></svg>
          ${(r.commitCount ?? 0).toLocaleString()}
        </span>
        <span class="prof-pinned-view-arrow">→</span>
      </div>
    </a>`;
  }).join('');

  section.style.display = '';
}

// ── Achievements ──────────────────────────────────────────────────────────────

const BADGE_COLORS: Record<string, string> = {
  first_commit:    '#58a6ff',
  century:         '#f0883e',
  domain_explorer: '#bc8cff',
  polymath:        '#d2a8ff',
  collaborator:    '#3fb950',
  pioneer:         '#2dd4bf',
  release_engineer:'#fbbf24',
  community_star:  '#ff9492',
};

function renderAchievements(badges: Badge[]): void {
  const section = $('prof-achievements-section');
  const row     = $('prof-achievements-row');
  const metaEl  = $('prof-achievements-meta');
  if (!section || !row) return;

  const earned = badges.filter(b => b.earned).length;
  if (metaEl) metaEl.textContent = `${earned} / ${badges.length} unlocked`;

  row.innerHTML = badges.map(b => {
    const col  = BADGE_COLORS[b.id] ?? '#8b949e';
    const cls  = b.earned ? 'prof-badge--earned' : 'prof-badge--locked';
    return `<div class="prof-badge ${cls}" title="${esc(b.description)}" style="--badge-color:${col}">
      <div class="prof-badge__icon">${esc(b.icon)}</div>
      <div class="prof-badge__body">
        <span class="prof-badge__name">${esc(b.name)}</span>
        <span class="prof-badge__desc">${esc(b.description)}</span>
      </div>
      ${b.earned ? '<span class="prof-badge__check">✓</span>' : '<span class="prof-badge__lock">🔒</span>'}
    </div>`;
  }).join('');

  section.style.display = '';
}

// ── Repo list tab ─────────────────────────────────────────────────────────────

function renderReposTab(repos: RepoData[]): void {
  const el = $('prof-tab-content');
  if (!el) return;
  if (!repos.length) {
    el.innerHTML = '<div class="prof-tab-empty">No repositories yet.</div>';
    return;
  }
  el.innerHTML = repos.map(r => {
    const col   = domainColor(r.domainViewerType ?? 'generic');
    const icon  = domainIcon(r.domainViewerType ?? 'generic');
    const label = domainLabel(r.domainViewerType ?? 'generic', r.domainName ?? '');
    return `<div class="prof-repo-row">
      <div class="prof-repo-row__main">
        <a class="prof-repo-row__name" href="/${esc(r.owner)}/${esc(r.slug)}">${esc(r.name)}</a>
        ${r.isPrivate ? '<span class="prof-repo-private">Private</span>' : ''}
        <span class="prof-repo-domain-pill" style="background:color-mix(in srgb,${col} 15%,transparent);color:${col}">
          ${icon} ${esc(label)}
        </span>
      </div>
      ${r.description ? `<p class="prof-repo-row__desc">${esc(r.description)}</p>` : ''}
      <div class="prof-repo-row__meta">
        <span>⭐ ${r.starsCount ?? 0}</span>
        <span>⑂ ${r.forksCount ?? 0}</span>
        ${r.updatedAt ? `<span>Updated ${timeAgo(r.updatedAt)}</span>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ── Stars tab ─────────────────────────────────────────────────────────────────

async function loadStarsTab(): Promise<void> {
  const el = $('prof-tab-content');
  if (!el) return;
  el.innerHTML = '<div class="prof-loading">Loading starred repos…</div>';
  try {
    const data = await fetch(`/api/v1/users/${_username}/starred`).then(r => r.json()) as RepoData[];
    if (!data.length) { el.innerHTML = '<div class="prof-tab-empty">No starred repos yet.</div>'; return; }
    renderReposTab(data);
  } catch { el.innerHTML = '<div class="prof-tab-error">Failed to load starred repos.</div>'; }
}

// ── Social tab ────────────────────────────────────────────────────────────────

async function loadSocialTab(type: 'followers' | 'following'): Promise<void> {
  const el = $('prof-tab-content');
  if (!el) return;
  el.innerHTML = `<div class="prof-loading">Loading ${type}…</div>`;
  try {
    const url  = type === 'followers'
      ? `/api/v1/users/${_username}/followers-list`
      : `/api/v1/users/${_username}/following-list`;
    const data = await fetch(url).then(r => r.json()) as Array<{ username: string; displayName?: string; bio?: string; avatarColor?: string }>;
    if (!data.length) { el.innerHTML = `<div class="prof-tab-empty">No ${type} yet.</div>`; return; }
    el.innerHTML = data.map(u => {
      const col  = u.avatarColor || avatarColor(u.username);
      const init = (u.displayName || u.username)[0].toUpperCase();
      return `<div class="prof-social-row-item">
        <a href="/${esc(u.username)}" class="prof-social-avatar" style="background:${col}">${esc(init)}</a>
        <div class="prof-social-info">
          <a href="/${esc(u.username)}" class="prof-social-name">${esc(u.displayName || u.username)}</a>
          <span class="prof-social-handle">@${esc(u.username)}</span>
          ${u.bio ? `<p class="prof-social-bio">${esc(u.bio)}</p>` : ''}
        </div>
      </div>`;
    }).join('');
  } catch { el.innerHTML = `<div class="prof-tab-error">Failed to load ${type}.</div>`; }
}

// ── Activity tab ──────────────────────────────────────────────────────────────

const EVENT_ICONS: Record<string, string> = {
  commit_pushed:'◎', pr_opened:'⑂', pr_merged:'✓', pr_closed:'✕',
  issue_opened:'!', issue_closed:'✓', branch_created:'⑂', tag_pushed:'⬡',
  session_started:'▶', session_ended:'⏹',
};

async function loadActivityTab(filter = 'all', page = 1): Promise<void> {
  const el = $('prof-tab-content');
  if (!el) return;
  el.innerHTML = '<div class="prof-loading">Loading activity…</div>';
  try {
    const data = await fetch(`/api/v1/users/${_username}/activity?filter=${filter}&page=${page}&limit=20`)
      .then(r => r.json()) as { events: Array<{ type: string; timestamp: string; description?: string; repo?: string }>; total: number };
    const events = data.events ?? [];
    if (!events.length) { el.innerHTML = '<div class="prof-tab-empty">No activity yet.</div>'; return; }
    const rows = events.map(e => {
      const icon = EVENT_ICONS[e.type] ?? '◈';
      return `<div class="prof-activity-row">
        <span class="prof-activity-icon">${icon}</span>
        <div class="prof-activity-body">
          <span class="prof-activity-desc">${esc(e.description ?? e.type)}</span>
          <span class="prof-activity-meta">${timeAgo(e.timestamp)}${e.repo ? ` · <a href="/${esc(e.repo)}">${esc(e.repo)}</a>` : ''}</span>
        </div>
      </div>`;
    }).join('');
    const totalPages = Math.ceil((data.total ?? 0) / 20);
    const pager = totalPages > 1 ? `<div class="prof-pager">
      ${page > 1 ? `<button class="btn btn-secondary btn-sm" data-apage="${page-1}" data-afilter="${filter}">← Prev</button>` : ''}
      <span class="prof-pager-label">Page ${page} / ${totalPages}</span>
      ${page < totalPages ? `<button class="btn btn-secondary btn-sm" data-apage="${page+1}" data-afilter="${filter}">Next →</button>` : ''}
    </div>` : '';
    el.innerHTML = rows + pager;
    el.querySelectorAll<HTMLButtonElement>('[data-apage]').forEach(btn => {
      btn.addEventListener('click', () => void loadActivityTab(btn.dataset.afilter ?? 'all', Number(btn.dataset.apage)));
    });
  } catch { el.innerHTML = '<div class="prof-tab-error">Failed to load activity.</div>'; }
}

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(tab: string): void {
  _currentTab = tab;
  document.querySelectorAll<HTMLElement>('.prof-tab-btn').forEach(btn => {
    btn.classList.toggle('prof-tab-btn--active', btn.dataset.tab === tab);
  });
  switch (tab) {
    case 'repos':     renderReposTab(_cachedRepos); break;
    case 'stars':     void loadStarsTab(); break;
    case 'followers': void loadSocialTab('followers'); break;
    case 'following': void loadSocialTab('following'); break;
    case 'activity':  void loadActivityTab(); break;
  }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

export async function initUserProfile(data: UserProfileData): Promise<void> {
  const username = data.username ?? '';
  if (!username) return;
  _username = username;

  // Tab count badges
  const tabCountEl = $('tab-count-repos');

  try {
    const [profileData, enhancedData] = await Promise.all([
      fetch(`/api/v1/users/${username}`).then(r => { if (!r.ok) throw new Error(r.status.toString()); return r.json(); }) as Promise<ProfileData>,
      fetch(`/${username}?format=json`).then(r => { if (!r.ok) throw new Error(r.status.toString()); return r.json(); }) as Promise<EnhancedData>,
    ]);

    _domainStats  = enhancedData.domainStats ?? [];
    _cachedRepos  = profileData.repos ?? [];

    // Render sections
    renderHero(profileData, enhancedData);
    renderDomainBar(_domainStats);
    renderHeatmap(
      enhancedData.heatmap ?? { days: [], totalContributions: 0, longestStreak: 0, currentStreak: 0 },
      _domainStats,
    );
    renderPinned(enhancedData.pinnedRepos ?? []);
    renderAchievements(enhancedData.badges ?? []);

    // Tabs
    const tabsEl = $('prof-tabs');
    if (tabsEl) {
      tabsEl.style.display = '';
      tabsEl.querySelectorAll<HTMLElement>('.prof-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab ?? 'repos'));
      });
      // Wire follower/following links to tabs
      $('prof-followers')?.addEventListener('click', e => { e.preventDefault(); switchTab('followers'); tabsEl.scrollIntoView({ behavior: 'smooth' }); });
      $('prof-following')?.addEventListener('click', e => { e.preventDefault(); switchTab('following'); tabsEl.scrollIntoView({ behavior: 'smooth' }); });
    }

    if (tabCountEl && _cachedRepos.length) tabCountEl.textContent = String(_cachedRepos.length);
    renderReposTab(_cachedRepos);

  } catch (err) {
    const heroEl = $('prof-hero');
    if (heroEl) heroEl.innerHTML = `<div class="prof-error">✕ Could not load profile for @${esc(username)}: ${esc(err instanceof Error ? err.message : String(err))}</div>`;
  }
}
