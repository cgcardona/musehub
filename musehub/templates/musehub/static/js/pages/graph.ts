/**
 * graph.ts — Git DAG graph renderer for the commits graph page.
 *
 * Config is read from window.__graphCfg (set by the page_data block).
 * Registered as: window.MusePages['graph']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface GraphCfg {
  repoId:  string;
  baseUrl: string;
}

interface DagNode {
  commitId:     string;
  message:      string;
  author:       string;
  timestamp:    string;
  branch:       string;
  parentIds?:   string[];
  branchLabels?: string[];
  isHead?:      boolean;
}

interface DagEdge {
  source: string;
  target: string;
}

interface DagData {
  nodes:        DagNode[];
  edges:        DagEdge[];
  headCommitId: string;
}

interface SessionEntry {
  sessionId: string;
  intent?:   string;
  startedAt: string;
  commits?:  string[];
}

interface SessionMap {
  [commitId: string]: { intent: string; sessionId: string };
}

declare global {
  interface Window {
    __graphCfg?: GraphCfg;
    escHtml:  (s: string) => string;
    apiFetch: (path: string, init?: RequestInit) => Promise<unknown>;
    fmtDate:  (d: string) => string;
    initRepoNav?: (repoId: string) => void;
  }
}

// ── Design constants ──────────────────────────────────────────────────────────

const BRANCH_PALETTE = [
  '#58a6ff','#3fb950','#f0883e','#bc8cff',
  '#ff7b72','#79c0ff','#56d364','#ffa657',
  '#d2a8ff','#ff9492','#2dd4bf','#fbbf24',
];
const AUTHOR_PALETTE = [
  '#58a6ff','#3fb950','#bc8cff','#fbbf24',
  '#f0883e','#2dd4bf','#ff9492','#a78bfa',
];
const COMMIT_TYPE_COLORS: Record<string, string> = {
  feat: '#3fb950', fix: '#f85149', refactor: '#bc8cff',
  init: '#58a6ff', docs: '#8b949e', style:   '#fbbf24',
  test: '#2dd4bf', chore: '#484f58', perf:   '#f0883e',
};
const SESSION_COLOR = '#2dd4bf';
const HEAD_COLOR    = '#f0883e';

const NODE_R     = 11;
const ROW_H      = 44;
const COL_W      = 28;
const PAD_L      = 24;
const PAD_T      = 20;
const MSG_OFFSET = 16;

// ── Module state (for zoom/pan controls) ─────────────────────────────────────

let _scale = 1;
let _tx    = 0;
let _ty    = 0;
let _dagG: SVGGElement | null = null;

// ── Color helpers ─────────────────────────────────────────────────────────────

const _branchColors: Record<string, string> = {};
const _authorColors: Record<string, string> = {};

function colorFor(name: string, palette: string[], cache: Record<string, string>): string {
  if (cache[name]) return cache[name];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  const c = palette[Math.abs(h) % palette.length];
  cache[name] = c;
  return c;
}
function branchColor(b: string): string { return colorFor(b, BRANCH_PALETTE, _branchColors); }
function authorColor(a: string): string { return colorFor(a, AUTHOR_PALETTE, _authorColors); }

function commitType(msg: string): string | null {
  const m = msg.match(/^(\w+)[\(!\:]/);
  return m ? m[1].toLowerCase() : null;
}
function typeColor(type: string): string | null { return COMMIT_TYPE_COLORS[type] || null; }

// ── Layout ────────────────────────────────────────────────────────────────────

interface LayoutResult {
  pos:       Record<string, { col: number; row: number }>;
  maxCol:    number;
  branchCol: Record<string, number>;
}

function layoutNodes(nodes: DagNode[]): LayoutResult {
  const branchCol: Record<string, number> = {};
  let nextCol = 0;
  nodes.forEach(n => {
    if (branchCol[n.branch] === undefined) branchCol[n.branch] = nextCol++;
  });
  const pos: Record<string, { col: number; row: number }> = {};
  nodes.forEach((n, row) => { pos[n.commitId] = { col: branchCol[n.branch], row }; });
  return { pos, maxCol: nextCol, branchCol };
}

// ── Transform helper ──────────────────────────────────────────────────────────

function applyXform(): void {
  if (_dagG) _dagG.setAttribute('transform', `translate(${_tx},${_ty}) scale(${_scale})`);
}

// ── SVG renderer ──────────────────────────────────────────────────────────────

function renderGraph(data: DagData, sessionMap: SessionMap, baseUrl: string): void {
  const { nodes, edges, headCommitId } = data;
  const loading = document.getElementById('dag-loading');
  const svgEl   = document.getElementById('dag-svg') as SVGSVGElement | null;
  if (loading) loading.style.display = 'none';

  if (!nodes.length || !svgEl) {
    if (svgEl) svgEl.style.display = 'none';
    const vp = document.getElementById('dag-viewport');
    if (vp) vp.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">No commits yet.</div>';
    return;
  }

  const { pos, maxCol, branchCol } = layoutNodes(nodes);
  const nodeMap: Record<string, DagNode> = {};
  nodes.forEach(n => { nodeMap[n.commitId] = n; });

  const authorCounts: Record<string, number> = {};
  nodes.forEach(n => { authorCounts[n.author] = (authorCounts[n.author] || 0) + 1; });
  const authors = Object.entries(authorCounts).sort((a, b) => b[1] - a[1]);
  const mergeCount = nodes.filter(n => (n.parentIds || []).length > 1).length;

  const statAuthors = document.getElementById('stat-authors');
  const statMerges  = document.getElementById('stat-merges');
  if (statAuthors) statAuthors.textContent = String(authors.length);
  if (statMerges)  statMerges.textContent  = String(mergeCount);

  const branches      = Object.keys(branchCol).sort((a, b) => branchCol[a] - branchCol[b]);
  const legendBranches = document.getElementById('legend-branches');
  if (legendBranches) {
    legendBranches.innerHTML = branches.map(b =>
      `<span class="graph-legend-branch">
        <span class="graph-legend-dot" style="background:${branchColor(b)}"></span>
        ${window.escHtml(b)}
      </span>`
    ).join('');
  }

  const branchCommitCounts: Record<string, number> = {};
  nodes.forEach(n => { branchCommitCounts[n.branch] = (branchCommitCounts[n.branch] || 0) + 1; });
  const sidebarBranches = document.getElementById('sidebar-branch-list');
  if (sidebarBranches) {
    sidebarBranches.innerHTML = branches.map(b =>
      `<div class="branch-legend-item">
        <span class="branch-legend-pill" style="background:${branchColor(b)}"></span>
        <span style="font-size:12px;color:var(--text-secondary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${window.escHtml(b)}</span>
        <span class="branch-legend-count">${branchCommitCounts[b] || 0}</span>
      </div>`
    ).join('');
  }

  const maxCommits    = authors[0] ? authors[0][1] : 1;
  const sidebarContribs = document.getElementById('sidebar-contributor-list');
  if (sidebarContribs) {
    sidebarContribs.innerHTML = authors.map(([author, count]) => {
      const pct    = Math.round((count / maxCommits) * 100);
      const acolor = authorColor(author);
      return `<div class="contributor-item">
        <span class="contributor-avatar-sm" style="background:${acolor}">${window.escHtml(author[0].toUpperCase())}</span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:4px">
            <span class="contributor-name">${window.escHtml(author)}</span>
            <span class="contributor-count">${count}</span>
          </div>
          <div class="contributor-bar">
            <div class="contributor-bar-fill" style="width:${pct}%;background:${acolor}"></div>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  const svgW = PAD_L + maxCol * COL_W + MSG_OFFSET + 520;
  const svgH = PAD_T * 2 + nodes.length * ROW_H;
  svgEl.setAttribute('width',  String(svgW));
  svgEl.setAttribute('height', String(svgH));
  svgEl.style.display = 'block';

  const defs = `<defs>
    <style>
      @keyframes spin { to { transform: rotate(360deg); } }
      .dag-node { cursor: pointer; }
      .dag-edge  { transition: opacity 0.15s; }
    </style>
  </defs>`;

  let edgesHtml = '';
  edges.forEach(e => {
    const src = pos[e.source];
    const tgt = pos[e.target];
    if (!src || !tgt) return;
    const x1   = PAD_L + src.col * COL_W;
    const y1   = PAD_T + src.row * ROW_H;
    const x2   = PAD_L + tgt.col * COL_W;
    const y2   = PAD_T + tgt.row * ROW_H;
    const node = nodeMap[e.source];
    const col  = node ? branchColor(node.branch) : '#8b949e';
    const midY = (y1 + y2) / 2;
    edgesHtml += `<path d="M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}"
      stroke="${col}" stroke-width="2" fill="none" opacity="0.55" class="dag-edge"/>`;
  });

  let nodesHtml  = '';
  let labelsHtml = '';
  const labelX   = PAD_L + maxCol * COL_W + MSG_OFFSET;

  nodes.forEach(n => {
    const p      = pos[n.commitId];
    const cx     = PAD_L + p.col * COL_W;
    const cy     = PAD_T + p.row * ROW_H;
    const bc     = branchColor(n.branch);
    const ac     = authorColor(n.author);
    const isHead  = n.commitId === headCommitId || n.isHead;
    const isMerge = (n.parentIds || []).length > 1;
    const inSess  = Boolean(sessionMap[n.commitId]);
    const initial = (n.author || '?')[0].toUpperCase();

    if (inSess) {
      nodesHtml += `<circle cx="${cx}" cy="${cy}" r="${NODE_R + 5}"
        fill="none" stroke="${SESSION_COLOR}" stroke-width="2" opacity="0.8"/>`;
    }
    if (isHead) {
      nodesHtml += `<circle cx="${cx}" cy="${cy}" r="${NODE_R + (inSess ? 9 : 4)}"
        fill="none" stroke="${HEAD_COLOR}" stroke-width="2" opacity="0.9"/>`;
    }

    if (isMerge) {
      const d = NODE_R * 0.9;
      nodesHtml += `<rect x="${cx - d}" y="${cy - d}" width="${d * 2}" height="${d * 2}"
        rx="3" fill="${bc}" stroke="${ac}" stroke-width="1.5"
        transform="rotate(45 ${cx} ${cy})"
        class="dag-node" data-id="${n.commitId}"/>`;
    } else {
      nodesHtml += `<circle cx="${cx}" cy="${cy}" r="${NODE_R}"
        fill="${bc}" stroke="${ac}" stroke-width="2"
        class="dag-node" data-id="${n.commitId}"/>`;
    }

    nodesHtml += `<text x="${cx}" y="${cy + 4}" text-anchor="middle"
      font-size="10" font-weight="700" fill="#0d1117"
      style="pointer-events:none;user-select:none">${window.escHtml(initial)}</text>`;

    const ctype     = commitType(n.message);
    const ctypeStr  = ctype && COMMIT_TYPE_COLORS[ctype]
      ? `<tspan fill="${COMMIT_TYPE_COLORS[ctype]}" font-weight="600">${window.escHtml(ctype)}</tspan><tspan fill="#8b949e">: </tspan>`
      : '';
    const fullMsg   = n.message || '';
    const bodyMsg   = ctype ? fullMsg.replace(/^\w+[^\:]*:\s*/, '') : fullMsg;
    const displayMsg = bodyMsg.length > 56 ? bodyMsg.substring(0, 53) + '…' : bodyMsg;

    let branchBadges = '';
    let badgeX = labelX;
    (n.branchLabels || []).forEach(lbl => {
      const bw     = lbl.length * 6.5 + 14;
      const bcolor = branchColor(lbl);
      branchBadges += `<rect x="${badgeX}" y="${cy - 20}" width="${bw}" height="13"
        rx="6" fill="${bcolor}" opacity="0.2"/>
      <text x="${badgeX + 7}" y="${cy - 10}" font-size="10" fill="${bcolor}"
        font-weight="600">${window.escHtml(lbl)}</text>`;
      badgeX += bw + 5;
    });
    if (isHead) {
      branchBadges += `<rect x="${badgeX}" y="${cy - 20}" width="34" height="13"
        rx="6" fill="${HEAD_COLOR}" opacity="0.25"/>
      <text x="${badgeX + 7}" y="${cy - 10}" font-size="10" fill="${HEAD_COLOR}"
        font-weight="700">HEAD</text>`;
    }

    const sha7 = n.commitId.substring(0, 7);
    labelsHtml += `
      ${branchBadges}
      <text x="${labelX}" y="${cy + 4}" class="dag-node" data-id="${n.commitId}"
        style="pointer-events:all">
        <tspan font-family="monospace" font-size="11" fill="#58a6ff">${sha7}</tspan>
        <tspan dx="8" font-size="13" fill="#c9d1d9">${ctypeStr}${window.escHtml(displayMsg)}</tspan>
      </text>`;
  });

  svgEl.innerHTML = defs + `<g id="dag-g">${edgesHtml}${nodesHtml}${labelsHtml}</g>`;
  _dagG = document.getElementById('dag-g') as SVGGElement | null;

  // ── Pan/zoom interaction ──────────────────────────────────────────────────
  const viewport = document.getElementById('dag-viewport')!;
  _scale = 1; _tx = 0; _ty = 0;
  let dragging = false;
  let dragSX   = 0;
  let dragSY   = 0;

  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    const rect   = viewport.getBoundingClientRect();
    const mx     = e.clientX - rect.left;
    const my     = e.clientY - rect.top;
    const factor = e.deltaY > 0 ? 0.85 : 1.18;
    const ns     = Math.max(0.15, Math.min(4, _scale * factor));
    _tx = mx - (mx - _tx) * (ns / _scale);
    _ty = my - (my - _ty) * (ns / _scale);
    _scale = ns;
    applyXform();
  }, { passive: false });

  viewport.addEventListener('mousedown', e => {
    dragging = true; dragSX = e.clientX; dragSY = e.clientY;
  });
  window.addEventListener('mouseup',   () => { dragging = false; });
  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    _tx += e.clientX - dragSX; _ty += e.clientY - dragSY;
    dragSX = e.clientX; dragSY = e.clientY;
    applyXform();
  });

  // ── Popover ───────────────────────────────────────────────────────────────
  const popover   = document.getElementById('dag-popover')!;
  const popSha    = document.getElementById('pop-sha')!;
  const popBranch = document.getElementById('pop-branch-badge') as HTMLElement;
  const popMsg    = document.getElementById('pop-msg')!;
  const popAuthor = document.getElementById('pop-author')!;
  const popAvatar = document.getElementById('pop-avatar') as HTMLElement;
  const popTime   = document.getElementById('pop-time')!;
  const popSession = document.getElementById('pop-session') as HTMLElement;

  svgEl.addEventListener('mousemove', e => {
    const t = (e.target as Element).closest<Element>('[data-id]');
    if (!t) { popover.style.display = 'none'; return; }
    const cid  = t.getAttribute('data-id')!;
    const node = nodeMap[cid];
    if (!node) { popover.style.display = 'none'; return; }

    popSha.textContent = node.commitId.substring(0, 12);

    const bc = branchColor(node.branch);
    popBranch.textContent        = node.branch;
    popBranch.style.background   = bc + '22';
    popBranch.style.color        = bc;
    popBranch.style.border       = `1px solid ${bc}44`;

    const ctype   = commitType(node.message);
    const bodyMsg = ctype ? node.message.replace(/^\w+[^\:]*:\s*/, '') : node.message;
    const tc      = ctype ? typeColor(ctype) : null;
    popMsg.innerHTML = tc
      ? `<span class="dag-pop-type dag-pop-type-${ctype}" style="background:${tc}22;color:${tc};border:1px solid ${tc}44">${window.escHtml(ctype!)}</span>${window.escHtml(bodyMsg)}`
      : window.escHtml(node.message);

    const ac = authorColor(node.author);
    popAvatar.textContent      = (node.author || '?')[0].toUpperCase();
    popAvatar.style.background = ac;
    popAuthor.textContent      = node.author;
    popTime.textContent        = window.fmtDate(node.timestamp);

    const sess = sessionMap[cid];
    if (sess && sess.intent) {
      popSession.textContent    = '◯ Session: ' + sess.intent;
      popSession.style.display  = 'block';
    } else {
      popSession.style.display  = 'none';
    }

    popover.style.display = 'block';
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let px = e.clientX + 18;
    let py = e.clientY + 14;
    if (px + 460 > vw) px = e.clientX - 460;
    if (py + 220 > vh) py = e.clientY - 220;
    popover.style.left = px + 'px';
    popover.style.top  = py + 'px';
  });

  svgEl.addEventListener('mouseleave', () => { popover.style.display = 'none'; });

  svgEl.addEventListener('click', e => {
    const t = (e.target as Element).closest<Element>('[data-id]');
    if (!t) return;
    const cid = t.getAttribute('data-id');
    if (cid) window.location.href = baseUrl + '/commits/' + cid;
  });
}

// ── Session map ───────────────────────────────────────────────────────────────

function buildSessionMap(sessions: SessionEntry[]): SessionMap {
  const map: SessionMap = {};
  const sorted = [...sessions].sort((a, b) =>
    new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  );
  sorted.forEach(s => {
    (s.commits || []).forEach(cid => {
      if (!map[cid]) map[cid] = { intent: s.intent || '', sessionId: s.sessionId };
    });
  });
  return map;
}

// ── Zoom/pan control handlers ─────────────────────────────────────────────────

function setupControls(): void {
  document.addEventListener('click', e => {
    const target = (e.target as Element).closest<HTMLElement>('[data-action]');
    if (!target) return;
    switch (target.dataset.action) {
      case 'zoom-in':    _scale = Math.max(0.15, Math.min(4, _scale * 1.25)); applyXform(); break;
      case 'zoom-out':   _scale = Math.max(0.15, Math.min(4, _scale * 0.8));  applyXform(); break;
      case 'zoom-reset': _scale = 1; _tx = 0; _ty = 0; applyXform(); break;
    }
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

async function load(cfg: GraphCfg): Promise<void> {
  if (typeof window.initRepoNav === 'function') window.initRepoNav(cfg.repoId);
  try {
    const [dagData, sessionsData] = await Promise.all([
      window.apiFetch('/repos/' + cfg.repoId + '/dag'),
      window.apiFetch('/repos/' + cfg.repoId + '/sessions?limit=200').catch(() => ({ sessions: [] })),
    ]) as [DagData, { sessions?: SessionEntry[] }];
    const sessionMap = buildSessionMap(sessionsData.sessions || []);
    renderGraph(dagData, sessionMap, cfg.baseUrl);
  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') {
      const loading = document.getElementById('dag-loading');
      if (loading) loading.innerHTML =
        `<span style="color:var(--color-danger)">✕ ${window.escHtml(err.message)}</span>`;
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initGraph(): void {
  const cfg = window.__graphCfg;
  if (!cfg) return;
  setupControls();
  void load(cfg);
}
