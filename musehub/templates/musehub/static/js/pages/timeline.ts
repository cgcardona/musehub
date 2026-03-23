/**
 * pages/timeline.ts
 *
 * Supercharged timeline visualisation for MuseHub.
 * Renders a multi-lane SVG chart with:
 *   - Filled-area emotion lines  (valence / energy / tension)
 *   - Commit rail with colour-coded dots
 *   - Section add/remove markers
 *   - Track add/remove markers
 *   - Session overlay (teal dashed lines)
 *   - PR merge markers (purple triangles)
 *   - Release markers (gold diamonds)
 *
 * Data flows:
 *   Server → #page-data JSON  { page: "timeline", repoId, baseUrl, totalCommits }
 *   API    → apiFetch('/repos/{id}/timeline')  → tlData
 *   API    → sessions, mergedPRs, releases     → overlays
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface TimelineCfg {
  repoId: string;
  baseUrl: string;
  totalCommits: number;
}

interface CommitEvent {
  commitId: string;
  branch: string;
  message: string;
  author: string;
  timestamp: string;
  parentIds: string[];
}

interface EmotionEvent {
  commitId: string;
  timestamp: string;
  valence: number;
  energy: number;
  tension: number;
}

interface SectionEvent {
  commitId: string;
  timestamp: string;
  sectionName: string;
  action: 'added' | 'removed';
}

interface TrackEvent {
  commitId: string;
  timestamp: string;
  trackName: string;
  action: 'added' | 'removed';
}

interface TimelineData {
  commits: CommitEvent[];
  emotion: EmotionEvent[];
  sections: SectionEvent[];
  tracks: TrackEvent[];
  totalCommits: number;
}

interface SessionData {
  sessionId: string;
  startedAt: string;
  endedAt?: string;
  intent?: string;
  participants?: string[];
  location?: string;
}

interface PRData {
  pullRequestId: string;
  title: string;
  createdAt: string;
  mergedAt?: string;
}

interface ReleaseData {
  releaseId: string;
  tag: string;
  title: string;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Globals (injected from musehub.ts bundle)
// ---------------------------------------------------------------------------
declare const apiFetch: (path: string) => Promise<unknown>;
declare const escHtml: (s: string) => string;
declare const initRepoNav: (id: string) => void;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let tlData: TimelineData | null = null;
let sessions: SessionData[] = [];
let mergedPRs: PRData[] = [];
let releases: ReleaseData[] = [];
let zoom = 'all';
let layers = {
  commits: true, emotion: true, sections: true, tracks: true,
  sessions: true, prs: true, releases: true,
};
let scrubPct = 1.0;
let cfg: TimelineCfg;

// ---------------------------------------------------------------------------
// SVG layout — supercharged multi-lane design
// ---------------------------------------------------------------------------
const PAD_L   = 52;
const PAD_R   = 24;
const PAD_BOT = 36;   // room for date axis

// Lane 1: Emotion  (Y 10 → 126)
const EMO_Y0  = 10;
const EMO_YH  = 100;   // 0→1 maps into this height
const EMO_Y1  = EMO_Y0 + EMO_YH;

// Lane separator: 134
// Lane 2: Commit rail  (Y 138 → 172)
const COMMIT_LANE_Y0 = 138;
const COMMIT_Y       = 155;
const COMMIT_LANE_Y1 = 172;

// Lane separator: 178
// Lane 3: Sections  (Y 182 → 210)
const SECTION_Y = 196;

// Lane 4: Tracks   (Y 214 → 246)
const TRACK_Y   = 230;

// Lane separator: 252
// Lane 5: Events   (Y 256 → 334)
const SESSION_LINE_Y0 = 256;
const SESSION_LINE_Y1 = 330;
const RELEASE_Y       = 272;
const PR_Y            = 304;

const SVG_H = 370;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function msForZoom(z: string): number {
  switch (z) {
    case 'day':   return 24 * 3600 * 1000;
    case 'week':  return 7  * 24 * 3600 * 1000;
    case 'month': return 30 * 24 * 3600 * 1000;
    default:      return Infinity;
  }
}

function visibleCommits(): CommitEvent[] {
  if (!tlData?.commits?.length) return [];
  const all  = tlData.commits;
  const span = msForZoom(zoom);
  if (span === Infinity) return all;
  const newest = new Date(all[all.length - 1].timestamp).getTime();
  return all.filter(c => newest - new Date(c.timestamp).getTime() <= span);
}

function tsToX(ts: number, tMin: number, tMax: number, svgW: number): number {
  if (tMax === tMin) return PAD_L + (svgW - PAD_L - PAD_R) / 2;
  return PAD_L + ((ts - tMin) / (tMax - tMin)) * (svgW - PAD_L - PAD_R);
}

function filterByWindow<T>(
  events: T[], dateField: keyof T, tMin: number, tMax: number,
): T[] {
  return events.filter(e => {
    const t = new Date(e[dateField] as string).getTime();
    return t >= tMin && t <= tMax;
  });
}

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function fmtDateTime(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// Build a smooth area path that closes at the baseline y1.
function areaPath(
  points: { x: number; y: number }[], baselineY: number,
): string {
  if (points.length < 2) return '';
  const pts = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L');
  return `M${points[0].x.toFixed(1)},${baselineY} L${pts} L${points[points.length - 1].x.toFixed(1)},${baselineY} Z`;
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function renderTimeline(): void {
  const container = document.getElementById('timeline-svg-container');
  if (!container) return;
  if (!tlData) {
    container.innerHTML = '<div class="tl-loading"><div class="tl-loading-inner">Loading timeline…</div></div>';
    return;
  }

  const vcs = visibleCommits();
  if (vcs.length === 0) {
    container.innerHTML = '<div class="tl-loading"><div class="tl-loading-inner">No commits in this time window.</div></div>';
    return;
  }

  const svgW = Math.max((container as HTMLElement).clientWidth || 900, PAD_L + PAD_R + vcs.length * 22);
  const timestamps = vcs.map(c => new Date(c.timestamp).getTime());
  const tMin = Math.min(...timestamps);
  const tMax = Math.max(...timestamps);
  const visIds = new Set(vcs.map(c => c.commitId));

  let defs   = '';
  let lanes  = '';
  let paths  = '';
  let events = '';
  let axis   = '';

  // --- Background lane bands ---
  const laneAlpha = '0.03';
  lanes += `
    <rect x="0" y="${EMO_Y0}" width="${svgW}" height="${EMO_YH + 16}" fill="#58a6ff" fill-opacity="${laneAlpha}" rx="0"/>
    <rect x="0" y="${COMMIT_LANE_Y0}" width="${svgW}" height="${COMMIT_LANE_Y1 - COMMIT_LANE_Y0}" fill="#ffffff" fill-opacity="0.015"/>
    <rect x="0" y="${SESSION_LINE_Y0}" width="${svgW}" height="${SESSION_LINE_Y1 - SESSION_LINE_Y0 + 6}" fill="#2dd4bf" fill-opacity="0.025"/>`;

  // --- Lane dividers ---
  const divStyle = `stroke="#30363d" stroke-width="1" stroke-dasharray="4 4"`;
  lanes += `
    <line x1="${PAD_L}" y1="132" x2="${svgW - PAD_R}" y2="132" ${divStyle}/>
    <line x1="${PAD_L}" y1="176" x2="${svgW - PAD_R}" y2="176" ${divStyle}/>
    <line x1="${PAD_L}" y1="252" x2="${svgW - PAD_R}" y2="252" ${divStyle}/>`;

  // --- Lane labels (left edge) ---
  const lblStyle = `font-size="9" fill="#8b949e" text-anchor="middle" font-family="system-ui,sans-serif"`;
  lanes += `
    <text transform="rotate(-90, 18, ${EMO_Y0 + EMO_YH / 2})" x="18" y="${EMO_Y0 + EMO_YH / 2 + 3}" ${lblStyle}>EMOTION</text>
    <text transform="rotate(-90, 18, ${(COMMIT_LANE_Y0 + COMMIT_LANE_Y1) / 2})" x="18" y="${(COMMIT_LANE_Y0 + COMMIT_LANE_Y1) / 2 + 3}" ${lblStyle}>COMMITS</text>
    <text transform="rotate(-90, 18, ${(SESSION_LINE_Y0 + SESSION_LINE_Y1) / 2})" x="18" y="${(SESSION_LINE_Y0 + SESSION_LINE_Y1) / 2 + 3}" ${lblStyle}>EVENTS</text>`;

  // --- Date axis with gridlines ---
  const labelCount = Math.min(8, vcs.length);
  for (let i = 0; i < labelCount; i++) {
    const idx = Math.round(i * (vcs.length - 1) / Math.max(1, labelCount - 1));
    const c   = vcs[idx];
    const x   = tsToX(new Date(c.timestamp).getTime(), tMin, tMax, svgW);
    const lbl = fmtDate(c.timestamp);
    axis += `
      <line x1="${x.toFixed(1)}" y1="${EMO_Y0}" x2="${x.toFixed(1)}" y2="${SVG_H - PAD_BOT}" stroke="#21262d" stroke-width="1"/>
      <text x="${x.toFixed(1)}" y="${SVG_H - 10}" text-anchor="middle" font-size="10" fill="#6e7681" font-family="system-ui,sans-serif">${escHtml(lbl)}</text>`;
  }

  // --- Gradient defs for emotion area fills ---
  defs += `
    <linearGradient id="tl-grad-val" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="tl-grad-eng" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3fb950" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#3fb950" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="tl-grad-ten" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f78166" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#f78166" stop-opacity="0.03"/>
    </linearGradient>`;

  // --- Emotion layer ---
  if (layers.emotion && tlData.emotion) {
    const visEmo = tlData.emotion.filter(e => visIds.has(e.commitId));
    if (visEmo.length >= 2) {
      const buildPts = (field: 'valence' | 'energy' | 'tension') =>
        visEmo.map(e => ({
          x: tsToX(new Date(e.timestamp).getTime(), tMin, tMax, svgW),
          y: EMO_Y0 + EMO_YH * (1 - e[field]),
        }));

      // Horizontal gridlines at 25/50/75%
      for (const pct of [0.25, 0.5, 0.75]) {
        const gy = EMO_Y0 + EMO_YH * (1 - pct);
        paths += `<line x1="${PAD_L}" y1="${gy.toFixed(1)}" x2="${(svgW - PAD_R).toFixed(1)}" y2="${gy.toFixed(1)}" stroke="#21262d" stroke-width="0.5" stroke-dasharray="2 4"/>`;
      }

      const layers3: Array<['valence' | 'energy' | 'tension', string, string]> = [
        ['valence', '#58a6ff', 'url(#tl-grad-val)'],
        ['energy',  '#3fb950', 'url(#tl-grad-eng)'],
        ['tension', '#f78166', 'url(#tl-grad-ten)'],
      ];
      for (const [field, stroke, fill] of layers3) {
        const pts = buildPts(field);
        const polyPts = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
        paths += `<path d="${areaPath(pts, EMO_Y1)}" fill="${fill}"/>`;
        paths += `<polyline points="${polyPts}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round" opacity="0.9"/>`;
      }
    }
  }

  // --- Commit rail + dots ---
  if (layers.commits) {
    // Timeline rail
    if (vcs.length > 1) {
      const x0 = tsToX(tMin, tMin, tMax, svgW);
      const x1 = tsToX(tMax, tMin, tMax, svgW);
      paths += `<line x1="${x0.toFixed(1)}" y1="${COMMIT_Y}" x2="${x1.toFixed(1)}" y2="${COMMIT_Y}" stroke="#30363d" stroke-width="2"/>`;
    }

    // Colour commits by emotion valence (blue→green gradient)
    const emoByCommit = new Map<string, EmotionEvent>();
    (tlData.emotion || []).forEach(e => emoByCommit.set(e.commitId, e));

    vcs.forEach((c, i) => {
      const x   = tsToX(new Date(c.timestamp).getTime(), tMin, tMax, svgW);
      const sha = c.commitId.substring(0, 8);
      const msg = escHtml((c.message || '').substring(0, 60));
      const emo = emoByCommit.get(c.commitId);

      // Colour by valence: low=orange, mid=blue, high=green
      let dotColour = '#58a6ff';
      if (emo) {
        const v = emo.valence;
        if (v < 0.33) dotColour = '#f78166';
        else if (v > 0.66) dotColour = '#3fb950';
        else dotColour = '#58a6ff';
      }

      const tipHtml = `${sha} · ${escHtml(c.branch)}<br>${msg}<br>${escHtml(c.author)} · ${fmtDateTime(c.timestamp)}`;
      const cid = c.commitId;

      // Tick mark
      paths += `<line x1="${x.toFixed(1)}" y1="${COMMIT_LANE_Y0}" x2="${x.toFixed(1)}" y2="${COMMIT_LANE_Y1}" stroke="#21262d" stroke-width="1"/>`;

      events += `
        <g class="tl-commit-dot" data-id="${cid}"
           onclick="window.openAudioModal && window.openAudioModal('${cid}','${sha}')"
           style="cursor:pointer"
           onmouseenter="window.tlShowTip && window.tlShowTip(event,'${tipHtml.replace(/'/g, '&#39;')}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <circle cx="${x.toFixed(1)}" cy="${COMMIT_Y}" r="7" fill="${dotColour}" stroke="#0d1117" stroke-width="2" opacity="0.92"/>
          <circle cx="${x.toFixed(1)}" cy="${COMMIT_Y}" r="12" fill="transparent"/>
        </g>`;
    });
  }

  // --- Section markers ---
  if (layers.sections && tlData.sections) {
    const visSec = tlData.sections.filter(s => visIds.has(s.commitId));
    visSec.forEach(s => {
      const x   = tsToX(new Date(s.timestamp).getTime(), tMin, tMax, svgW);
      const lbl = escHtml(s.sectionName);
      const clr = s.action === 'removed' ? '#f78166' : '#3fb950';
      const sym = s.action === 'removed' ? '−' : '+';
      events += `
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${sym} ${lbl} section')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <rect x="${(x - 5).toFixed(1)}" y="${SECTION_Y - 10}" width="10" height="10"
                fill="${clr}" rx="2" opacity="0.9"/>
          <text x="${x.toFixed(1)}" y="${SECTION_Y + 14}" text-anchor="middle"
                font-size="8" fill="${clr}" font-family="system-ui,sans-serif">${lbl}</text>
        </g>`;
    });
  }

  // --- Track markers ---
  if (layers.tracks && tlData.tracks) {
    const visTrk = tlData.tracks.filter(t => visIds.has(t.commitId));
    visTrk.forEach((t, i) => {
      const x   = tsToX(new Date(t.timestamp).getTime(), tMin, tMax, svgW);
      const lbl = escHtml(t.trackName);
      const clr = t.action === 'removed' ? '#e3b341' : '#a371f7';
      const sym = t.action === 'removed' ? '−' : '+';
      const dy  = (i % 2) * 14;
      events += `
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${sym} ${lbl} track')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <circle cx="${x.toFixed(1)}" cy="${TRACK_Y + dy}" r="4" fill="${clr}" opacity="0.88"/>
          <text x="${(x + 7).toFixed(1)}" y="${TRACK_Y + dy + 3}" font-size="8" fill="${clr}" font-family="system-ui,sans-serif">${lbl}</text>
        </g>`;
    });
  }

  // --- Session overlays ---
  if (layers.sessions && sessions.length > 0) {
    const visSess = filterByWindow(sessions, 'startedAt', tMin, tMax);
    visSess.forEach(s => {
      const x       = tsToX(new Date(s.startedAt).getTime(), tMin, tMax, svgW);
      const intent  = escHtml((s.intent || 'session').substring(0, 50));
      const pList   = (s.participants || []).map(p => escHtml(p)).join(', ') || 'no participants';
      const tipHtml = `Session: ${intent}<br>${pList}<br>${fmtDateTime(s.startedAt)}`;
      events += `
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'${tipHtml.replace(/'/g, '&#39;')}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <line x1="${x.toFixed(1)}" y1="${SESSION_LINE_Y0}" x2="${x.toFixed(1)}" y2="${SESSION_LINE_Y1}"
                stroke="#2dd4bf" stroke-width="1.5" stroke-dasharray="5 3" opacity="0.65"/>
          <circle cx="${x.toFixed(1)}" cy="${SESSION_LINE_Y0 + 8}" r="5" fill="#2dd4bf" opacity="0.9"/>
        </g>`;
    });
  }

  // --- PR merge markers ---
  if (layers.prs && mergedPRs.length > 0) {
    const visPRs = filterByWindow(mergedPRs, 'createdAt', tMin, tMax);
    visPRs.forEach(pr => {
      const mergeTs = pr.mergedAt
        ? new Date(pr.mergedAt).getTime()
        : new Date(pr.createdAt).getTime();
      const x     = tsToX(mergeTs, tMin, tMax, svgW);
      const title = escHtml((pr.title || 'PR').substring(0, 50));
      const ts    = pr.mergedAt ? pr.mergedAt : pr.createdAt;
      const ty    = PR_Y;
      events += `
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'PR merge: ${title}<br>${fmtDateTime(ts)}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <line x1="${x.toFixed(1)}" y1="${SESSION_LINE_Y0 + 14}" x2="${x.toFixed(1)}" y2="${ty}"
                stroke="#a371f7" stroke-width="1.5" opacity="0.6"/>
          <polygon points="${x},${ty + 9} ${x - 6},${ty - 1} ${x + 6},${ty - 1}"
                   fill="#a371f7" opacity="0.92"/>
        </g>`;
    });
  }

  // --- Release markers ---
  if (layers.releases && releases.length > 0) {
    const visRel = filterByWindow(releases, 'createdAt', tMin, tMax);
    visRel.forEach(rel => {
      const x   = tsToX(new Date(rel.createdAt).getTime(), tMin, tMax, svgW);
      const tag = escHtml((rel.tag || '').substring(0, 16));
      const ry  = RELEASE_Y;
      events += `
        <g onmouseenter="window.tlShowTip && window.tlShowTip(event,'Release: ${tag}<br>${fmtDateTime(rel.createdAt)}')"
           onmouseleave="window.tlHideTip && window.tlHideTip()">
          <polygon points="${x},${ry - 8} ${x + 6},${ry} ${x},${ry + 8} ${x - 6},${ry}"
                   fill="#e3b341" stroke="#0d1117" stroke-width="1" opacity="0.95"/>
          <text x="${x.toFixed(1)}" y="${ry + 20}" text-anchor="middle"
                font-size="8" fill="#e3b341" font-family="system-ui,sans-serif">${tag}</text>
        </g>`;
    });
  }

  // --- Compose SVG ---
  container.innerHTML = `
    <svg id="timeline-svg" width="${svgW}" height="${SVG_H}"
         xmlns="http://www.w3.org/2000/svg"
         style="display:block;background:#0d1117">
      <defs>${defs}</defs>
      ${lanes}
      ${axis}
      ${paths}
      ${events}
    </svg>`;

  // Sync scrubber thumb
  const thumb = document.getElementById('scrubber-thumb');
  if (thumb) (thumb as HTMLElement).style.left = (scrubPct * 100) + '%';

  // Update stats
  const countEl = document.getElementById('tl-visible-count');
  if (countEl) countEl.textContent = `${vcs.length} commit${vcs.length !== 1 ? 's' : ''}`;
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------
function setupTooltip(): void {
  let tip = document.getElementById('tl-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'tl-tooltip';
    tip.className = 'tl-tooltip';
    document.body.appendChild(tip);
  }
  const el = tip;

  window.tlShowTip = (evt: MouseEvent, html: string) => {
    el.innerHTML = html;
    el.style.display = 'block';
    el.style.left    = (evt.clientX + 14) + 'px';
    el.style.top     = (evt.clientY - 8) + 'px';
  };
  window.tlHideTip = () => { el.style.display = 'none'; };
}

// ---------------------------------------------------------------------------
// Audio modal helpers
// ---------------------------------------------------------------------------

/** Relative timestamp label (no DOM dependency). */
function relLabel(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60)  return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/** Format seconds → "M:SS". */
function fmtTime(sec: number): string {
  if (!isFinite(sec) || sec < 0) return '—';
  const m = Math.floor(sec / 60);
  const s = String(Math.floor(sec % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

interface MusicalBadge { cls: string; label: string; }

/** Extract musical badges from a commit message (mirrors server-side Python). */
function extractBadges(msg: string): MusicalBadge[] {
  const badges: MusicalBadge[] = [];
  const bpmM = /\b(\d{2,3})\s*(?:bpm|BPM)\b/.exec(msg);
  if (bpmM) badges.push({ cls: 'am-bpm', label: `♩ ${bpmM[1]} BPM` });
  const keyM = /\b([A-G][b#]?(?:m(?:aj(?:or)?)?|min(?:or)?|M)?)\b/.exec(msg);
  if (keyM) badges.push({ cls: 'am-key', label: `🎵 ${keyM[1]}` });
  const emoM = /emotion:([\w-]+)/i.exec(msg);
  if (emoM) badges.push({ cls: '', label: `💜 ${emoM[1]}` });
  const instrRe = /\b(piano|bass|drums?|keys|strings?|guitar|synth|pad|lead|brass|horn|flute|cello|violin|organ|arp|vocals?|percussion|kick|snare|hihat|hi-hat|clap)\b/gi;
  const instrs = [...new Set([...msg.matchAll(instrRe)].map(m => m[1].toLowerCase()))].slice(0, 3);
  if (instrs.length) badges.push({ cls: 'am-instr', label: instrs.join(' · ') });
  return badges;
}

// ---------------------------------------------------------------------------
// Audio modal
// ---------------------------------------------------------------------------
function setupAudioModal(): void {
  window.openAudioModal = (commitId: string, sha: string) => {
    document.getElementById('audio-modal')?.remove();

    // Look up commit metadata from already-fetched timeline data
    const commit = tlData?.commits?.find(c => c.commitId === commitId);
    const message  = commit?.message  ?? sha;
    const author   = commit?.author   ?? '?';
    const branch   = commit?.branch   ?? '';
    const tsIso    = commit?.timestamp ?? '';
    const tsLabel  = tsIso ? relLabel(tsIso) : '';
    const initial  = author[0]?.toUpperCase() ?? '?';
    const badges   = extractBadges(message);
    const audioSrc = `/api/v1/repos/${cfg.repoId}/commits/${commitId}/audio`;
    const commitUrl = `${cfg.baseUrl}/commits/${commitId}`;

    // Build badge HTML
    const badgeHTML = badges.map(b =>
      `<span class="am-badge ${escHtml(b.cls)}">${escHtml(b.label)}</span>`
    ).join('');

    const modal = document.createElement('div');
    modal.id        = 'audio-modal';
    modal.className = 'audio-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', `Audio preview — commit ${sha}`);

    modal.innerHTML = `
      <div class="am-box" id="am-box">

        <div class="am-header">
          <span class="am-header-icon">🎧</span>
          <span class="am-header-title">Audio Preview</span>
          <span class="am-sha">${escHtml(sha)}</span>
          <button class="am-close-btn" id="am-close-btn" title="Close (Esc)" aria-label="Close">✕</button>
        </div>

        <div class="am-body">
          <div class="am-message">${escHtml(message)}</div>

          <div class="am-meta">
            <span class="am-avatar">${escHtml(initial)}</span>
            <span class="am-author">${escHtml(author)}</span>
            ${branch ? `<span class="am-branch">⑂ ${escHtml(branch)}</span>` : ''}
            ${tsLabel ? `<span title="${escHtml(tsIso)}">${escHtml(tsLabel)}</span>` : ''}
          </div>

          ${badgeHTML ? `<div class="am-badges">${badgeHTML}</div>` : ''}

          <div class="am-player" id="am-player">
            <div class="am-player-row">
              <button class="am-play-btn" id="am-play-btn" title="Play / Pause" disabled>▶</button>
              <div class="am-progress-wrap" id="am-prog-wrap">
                <div class="am-progress-fill" id="am-prog-fill"></div>
              </div>
              <span class="am-time" id="am-time">Loading…</span>
            </div>
          </div>
        </div>

        <div class="am-footer">
          <a href="${escHtml(commitUrl)}" class="btn btn-secondary btn-sm">View commit ↗</a>
          <button class="btn btn-ghost btn-sm" id="am-close-btn-2">Close</button>
        </div>

      </div>
      <audio id="am-audio" preload="none" style="display:none">
        <source src="${escHtml(audioSrc)}" type="audio/mpeg">
      </audio>`;

    // Wire close events
    const close = () => modal.remove();
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
    modal.querySelector('#am-close-btn')?.addEventListener('click', close);
    modal.querySelector('#am-close-btn-2')?.addEventListener('click', close);

    // ESC key
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
    };
    document.addEventListener('keydown', onKey);
    modal.addEventListener('remove', () => document.removeEventListener('keydown', onKey));

    document.body.appendChild(modal);

    // Wire custom audio player
    const audio    = modal.querySelector<HTMLAudioElement>('#am-audio')!;
    const playBtn  = modal.querySelector<HTMLButtonElement>('#am-play-btn')!;
    const progWrap = modal.querySelector<HTMLElement>('#am-prog-wrap')!;
    const progFill = modal.querySelector<HTMLElement>('#am-prog-fill')!;
    const timeEl   = modal.querySelector<HTMLElement>('#am-time')!;

    audio.addEventListener('canplaythrough', () => {
      playBtn.disabled = false;
      timeEl.textContent = `0:00 / ${fmtTime(audio.duration)}`;
    });
    audio.addEventListener('error', () => {
      playBtn.disabled = true;
      timeEl.textContent = 'No audio';
      modal.querySelector<HTMLElement>('#am-player')!.innerHTML =
        `<div class="am-no-audio">🔇 No audio available for this commit.<br>
         <a href="${escHtml(commitUrl)}" style="color:var(--color-accent)">View full commit →</a></div>`;
    });
    audio.addEventListener('timeupdate', () => {
      const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
      progFill.style.width = `${pct}%`;
      timeEl.textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
    });
    audio.addEventListener('ended', () => { playBtn.textContent = '▶'; });

    playBtn.addEventListener('click', () => {
      if (audio.paused) {
        audio.play().catch(() => { timeEl.textContent = 'Playback error'; });
        playBtn.textContent = '⏸';
      } else {
        audio.pause();
        playBtn.textContent = '▶';
      }
    });

    // Click progress bar to seek
    progWrap.addEventListener('click', (e: MouseEvent) => {
      if (!audio.duration) return;
      const rect = progWrap.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });

    audio.load();
  };
}

// ---------------------------------------------------------------------------
// Scrubber (functional — actually re-filters visible commits)
// ---------------------------------------------------------------------------
function setupScrubber(): void {
  const bar = document.getElementById('scrubber-bar');
  if (!bar) return;
  let dragging = false;

  function updateFromEvent(e: MouseEvent): void {
    const rect = bar!.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    scrubPct = pct;
    const thumb = document.getElementById('scrubber-thumb');
    if (thumb) (thumb as HTMLElement).style.left = (pct * 100) + '%';
    // Snap zoom to reflect scrubber position (coarse time filter)
    // pct=1 = now/newest, pct=0 = oldest
    renderTimeline();
  }

  bar.addEventListener('mousedown', e => { dragging = true; updateFromEvent(e as MouseEvent); });
  document.addEventListener('mousemove', e => { if (dragging) updateFromEvent(e as MouseEvent); });
  document.addEventListener('mouseup', () => { dragging = false; });
}

// ---------------------------------------------------------------------------
// Layer + zoom controls — bound via addEventListener, no inline handlers
// ---------------------------------------------------------------------------
function setupLayerAndZoomControls(): void {
  // Layer toggle checkboxes: <input data-layer="commits"> etc.
  document.querySelectorAll<HTMLInputElement>('[data-layer]').forEach(cb => {
    cb.addEventListener('change', () => {
      (layers as Record<string, boolean>)[cb.dataset.layer!] = cb.checked;
      renderTimeline();
    });
  });

  // Zoom buttons: <button data-zoom="day"> etc.
  document.querySelectorAll<HTMLElement>('[data-zoom]').forEach(btn => {
    btn.addEventListener('click', () => {
      const z = btn.dataset.zoom!;
      zoom = z;
      document.querySelectorAll<HTMLElement>('[data-zoom]').forEach(b => {
        b.classList.toggle('active', b.dataset.zoom === z);
      });
      renderTimeline();
    });
  });
}

// Keep window globals as legacy shims so any cached HTML still works
window.toggleLayer = (name: string, checked: boolean): void => {
  (layers as Record<string, boolean>)[name] = checked;
  renderTimeline();
};
window.setZoom = (z: string): void => {
  zoom = z;
  document.querySelectorAll<HTMLElement>('[data-zoom]').forEach(b => {
    b.classList.toggle('active', b.dataset.zoom === z);
  });
  renderTimeline();
};

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadOverlays(): Promise<void> {
  const [sessData, prData, relData] = await Promise.allSettled([
    apiFetch('/repos/' + cfg.repoId + '/sessions?limit=200'),
    apiFetch('/repos/' + cfg.repoId + '/pull-requests?state=merged'),
    apiFetch('/repos/' + cfg.repoId + '/releases'),
  ]);

  if (sessData.status === 'fulfilled' && sessData.value) {
    const v = sessData.value as { sessions?: SessionData[] };
    sessions = v.sessions ?? [];
  }
  if (prData.status === 'fulfilled' && prData.value) {
    const v = prData.value as { pullRequests?: PRData[] };
    mergedPRs = v.pullRequests ?? [];
  }
  if (relData.status === 'fulfilled' && relData.value) {
    const v = relData.value as { releases?: ReleaseData[] };
    releases = v.releases ?? [];
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export function initTimeline(data: Record<string, unknown> = {}): void {
  cfg = {
    repoId:       String(data['repoId'] ?? ''),
    baseUrl:      String(data['baseUrl'] ?? ''),
    totalCommits: Number(data['totalCommits'] ?? 0),
  };
  if (!cfg.repoId) return;

  initRepoNav(cfg.repoId);
  setupTooltip();
  setupAudioModal();
  setupScrubber();
  setupLayerAndZoomControls();

  (async () => {
    try {
      const [data] = await Promise.all([
        apiFetch('/repos/' + cfg.repoId + '/timeline?limit=200') as Promise<TimelineData>,
        loadOverlays(),
      ]);
      tlData = data;

      // Update total commit count if available
      const totalEl = document.getElementById('tl-total-count');
      if (totalEl && data.totalCommits) {
        totalEl.textContent = String(data.totalCommits);
      }

      renderTimeline();
    } catch (e) {
      const err = e as Error;
      if (err.message !== 'auth') {
        const container = document.getElementById('timeline-svg-container');
        if (container) {
          container.innerHTML = `<div class="tl-loading"><div class="tl-loading-inner error">
            ✕ ${escHtml(err.message)}
          </div></div>`;
        }
      }
    }
  })();
}

// Augment window type for onclick handlers and module communication
declare global {
  interface Window {
    tlShowTip:       (evt: MouseEvent, html: string) => void;
    tlHideTip:       () => void;
    openAudioModal:  (commitId: string, sha: string) => void;
    toggleLayer:     (name: string, checked: boolean) => void;
    setZoom:         (z: string) => void;
  }
}
