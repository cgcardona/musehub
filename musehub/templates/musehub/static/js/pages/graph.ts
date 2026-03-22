/**
 * graph.ts — High-performance Canvas2D DAG renderer.
 *
 * Architecture:
 *  - Canvas2D renders graph (edges, nodes, labels) with device-pixel-ratio
 *    support for crisp retina output.
 *  - All pan/zoom changes are batched through requestAnimationFrame.
 *  - Hit-testing is coordinate-based (no per-node DOM elements).
 *  - A minimap canvas overlay provides always-on navigation context.
 *  - Search highlights matching commits while dimming the rest.
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface GraphCfg { repoId: string; baseUrl: string; }

interface DagNode {
  commitId:     string;
  message:      string;
  author:       string;
  timestamp:    string;
  branch:       string;
  parentIds?:   string[];
  branchLabels?: string[];
  tagLabels?:   string[];
  isHead?:      boolean;
  // Muse semantic enrichment — absent in Git
  commitType?:  string;   // feat, fix, refactor, chore, perf, …
  semVerBump?:  string;   // major, minor, patch, none
  isBreaking?:  boolean;
  isAgent?:     boolean;
  symAdded?:    number;
  symRemoved?:  number;
}
interface DagEdge  { source: string; target: string; }
interface DagData  { nodes: DagNode[]; edges: DagEdge[]; headCommitId: string; }
interface SessionEntry { sessionId: string; intent?: string; startedAt: string; commits?: string[]; }
interface SessionMap   { [cid: string]: { intent: string; sessionId: string }; }

// SSR-injected DAG shape matches the /repos/{id}/dag JSON response but uses
// snake_case keys (Python serialisation). We normalise to camelCase below.
interface SsrDagNode {
  commit_id: string; message: string; author: string; timestamp: string;
  branch: string; parent_ids: string[]; is_head: boolean;
  branch_labels: string[]; tag_labels: string[];
  commit_type: string; sem_ver_bump: string;
  is_breaking: boolean; is_agent: boolean;
  sym_added: number; sym_removed: number;
}
interface SsrDagData {
  nodes: SsrDagNode[];
  edges: Array<{ source: string; target: string }>;
  head_commit_id: string | null;
}

declare global {
  interface Window {
    __graphCfg?:  GraphCfg;
    __graphData?: SsrDagData;
    escHtml:  (s: string) => string;
    apiFetch: (path: string, init?: RequestInit) => Promise<unknown>;
    fmtDate:  (d: string) => string;
    initRepoNav?: (repoId: string) => void;
  }
}

// ── Design constants ──────────────────────────────────────────────────────────

const PALETTE = [
  '#58a6ff','#3fb950','#f0883e','#bc8cff',
  '#ff7b72','#79c0ff','#56d364','#ffa657',
  '#d2a8ff','#ff9492','#2dd4bf','#fbbf24',
];

// Commit type → node fill color (semantic primary encoding)
const TYPE_COLORS: Record<string, string> = {
  feat:     '#3fb950',  // green   — new capability
  fix:      '#f85149',  // red     — bug fix
  refactor: '#bc8cff',  // purple  — structural change
  init:     '#58a6ff',  // blue    — initialisation
  docs:     '#6e96c9',  // muted blue
  style:    '#fbbf24',  // yellow  — formatting
  test:     '#2dd4bf',  // teal    — tests
  chore:    '#6e7681',  // gray    — housekeeping
  perf:     '#f0883e',  // orange  — performance
  build:    '#a78bfa',  // violet  — build system
  ci:       '#60a5fa',  // sky     — CI/CD
  revert:   '#fb923c',  // amber   — revert
};

// Semver pip colors (top-right corner badge on the node)
const SEMVER_COLORS: Record<string, string> = {
  major: '#ef4444',   // red   — breaking version bump
  minor: '#3b82f6',   // blue  — feature version bump
  patch: '#22c55e',   // green — patch/fix bump
};

const HEAD_COLOR     = '#f0883e';
const MERGE_COLOR    = '#bc8cff';
const SESSION_COLOR  = '#2dd4bf';
const BREAKING_COLOR = '#ef4444';
const AGENT_COLOR    = '#a78bfa';   // violet for agent-authored nodes
const DIM_ALPHA      = 0.18;

// Layout constants
const ROW_H   = 48;   // slightly more breathing room
const LANE_W  = 26;
const NODE_R  = 9;
const PAD_L   = 20;
const PAD_T   = 32;
const LBL_GAP = 22;

// Minimap
const MM_W  = 148;
const MM_H  = 100;
const MM_PAD = 10;

// ── Color helpers ─────────────────────────────────────────────────────────────

const _colorCache: Record<string, string> = {};
function colorFor(name: string): string {
  if (_colorCache[name]) return _colorCache[name];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return (_colorCache[name] = PALETTE[Math.abs(h) % PALETTE.length]);
}

function commitType(n: DagNode): string | null {
  if (n.commitType) return n.commitType;
  const m = (n.message || '').match(/^(\w+)[\(!:]/);
  return m ? m[1].toLowerCase() : null;
}

function nodeSemanticColor(n: DagNode, branchColor: string): string {
  const ct = commitType(n);
  if (ct && TYPE_COLORS[ct]) return TYPE_COLORS[ct];
  if (n.isAgent) return AGENT_COLOR;
  return branchColor;
}

function timeAgo(ts: string): string {
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60)    return `${Math.floor(s)}s ago`;
  if (s < 3600)  return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── Layout ────────────────────────────────────────────────────────────────────

interface Layout {
  rows:     DagNode[];          // display order: index 0 = top = NEWEST
  pos:      Record<string, { lane: number; row: number }>;
  laneCount: number;
  laneColors: Record<string, string>;  // branch → color
  labelX:   number;
}

function buildLayout(nodes: DagNode[], _edges: DagEdge[]): Layout {
  // Display newest-first: reverse the array (API returns oldest-first)
  const rows = [...nodes].reverse();

  // Assign lanes by branch name, preserving first-seen order
  const laneMap: Record<string, number> = {};
  const laneColors: Record<string, string> = {};
  let nextLane = 0;

  // Give main/master/dev priority lane 0
  const PRIORITY = ['main', 'master', 'dev', 'develop', 'HEAD'];
  for (const n of rows) {
    if (PRIORITY.includes(n.branch) && laneMap[n.branch] === undefined) {
      laneColors[n.branch] = colorFor(n.branch);
      laneMap[n.branch] = nextLane++;
    }
  }
  for (const n of rows) {
    if (laneMap[n.branch] === undefined) {
      laneColors[n.branch] = colorFor(n.branch);
      laneMap[n.branch] = nextLane++;
    }
  }

  const pos: Record<string, { lane: number; row: number }> = {};
  rows.forEach((n, row) => {
    pos[n.commitId] = { lane: laneMap[n.branch] ?? 0, row };
  });

  const laneCount = Math.max(1, nextLane);
  const labelX    = PAD_L + laneCount * LANE_W + LBL_GAP;
  return { rows, pos, laneCount, laneColors, labelX };
}

// ── Canvas state ──────────────────────────────────────────────────────────────

let canvas!:   HTMLCanvasElement;
let mmCanvas!: HTMLCanvasElement;
let ctx!:      CanvasRenderingContext2D;
let mmCtx!:    CanvasRenderingContext2D;
let dpr = 1;

let _layout!:  Layout;
let _nodeMap:  Record<string, DagNode> = {};
let _sessMap:  SessionMap = {};
let _headId = '';
let _baseUrl = '';

// View state
let tx = 0, ty = 0, scale = 1;
let hoverId: string | null = null;
let searchQuery = '';
let matchSet: Set<string> | null = null;
let pinned: string | null = null;   // pinned tooltip on click

let rafId: number | null = null;
let dirty = false;

function scheduleRedraw(): void {
  dirty = true;
  if (rafId !== null) return;
  rafId = requestAnimationFrame(() => {
    rafId = null;
    if (dirty) { dirty = false; draw(); }
  });
}

// ── Canvas setup ──────────────────────────────────────────────────────────────

function resizeCanvas(): void {
  const vp    = canvas.parentElement!;
  const W     = vp.clientWidth;
  const H     = vp.clientHeight;
  dpr         = window.devicePixelRatio || 1;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const mmEl = document.getElementById('dag-minimap') as HTMLCanvasElement | null;
  if (mmEl) {
    mmEl.width  = MM_W * dpr;
    mmEl.height = MM_H * dpr;
    mmEl.style.width  = MM_W + 'px';
    mmEl.style.height = MM_H + 'px';
    mmCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

// ── Coordinate helpers ────────────────────────────────────────────────────────

function nodeX(lane: number): number { return PAD_L + lane * LANE_W + LANE_W / 2; }
function nodeY(row: number):  number { return PAD_T + row * ROW_H; }
function worldToScreen(wx: number, wy: number): [number, number] {
  return [wx * scale + tx, wy * scale + ty];
}
function screenToWorld(sx: number, sy: number): [number, number] {
  return [(sx - tx) / scale, (sy - ty) / scale];
}

// ── Hit testing ───────────────────────────────────────────────────────────────

function hitTest(sx: number, sy: number): string | null {
  const [wx, wy] = screenToWorld(sx, sy);
  const vpH = canvas.clientHeight;
  const visibleRows = Math.ceil(vpH / (ROW_H * scale)) + 2;
  const startRow    = Math.max(0, Math.floor((0 - ty) / (ROW_H * scale)) - 1);
  const endRow      = Math.min(_layout.rows.length, startRow + visibleRows);

  for (let i = startRow; i < endRow; i++) {
    const n  = _layout.rows[i];
    const p  = _layout.pos[n.commitId];
    if (!p) continue;
    const cx = nodeX(p.lane);
    const cy = nodeY(p.row);
    const dx = wx - cx, dy = wy - cy;
    // Node circle hit
    if (dx * dx + dy * dy <= (NODE_R + 6) * (NODE_R + 6)) return n.commitId;
    // Label row hit (full width, ±ROW_H/2 vertically)
    if (Math.abs(dy) < ROW_H / 2 && wx >= _layout.labelX - 8) return n.commitId;
  }
  return null;
}

// ── Drawing primitives ────────────────────────────────────────────────────────

function drawEdges(): void {
  const vpW = canvas.clientWidth;
  const vpH = canvas.clientHeight;
  const [wLeft, wTop]    = screenToWorld(0, 0);
  const [wRight, wBottom] = screenToWorld(vpW, vpH);

  // Build lookup: commitId → row data
  const rowIdx: Record<string, number> = {};
  _layout.rows.forEach((n, i) => { rowIdx[n.commitId] = i; });

  // We iterate rows and draw the edge from each row to its parents
  for (const n of _layout.rows) {
    const p = _layout.pos[n.commitId];
    if (!p) continue;
    const x1 = nodeX(p.lane);
    const y1 = nodeY(p.row);

    // Quick cull: skip if node is completely off-screen
    if (y1 * scale + ty + 60 < 0) continue;
    if (y1 * scale + ty - 60 > vpH) continue;

    const bColor = _layout.laneColors[n.branch] ?? '#8b949e';
    const isSearchActive = matchSet !== null;
    const isMatch = !matchSet || matchSet.has(n.commitId);

    for (const pid of (n.parentIds ?? [])) {
      const pNode = _nodeMap[pid];
      if (!pNode) continue;
      const pp  = _layout.pos[pid];
      if (!pp) continue;

      const x2 = nodeX(pp.lane);
      const y2 = nodeY(pp.row);

      // Skip if edge is entirely off-screen
      const minY = Math.min(y1, y2) * scale + ty;
      const maxY = Math.max(y1, y2) * scale + ty;
      if (maxY < -10 || minY > vpH + 10) continue;

      const pMatch  = !matchSet || matchSet.has(pid);
      const alpha   = isSearchActive && !isMatch && !pMatch ? DIM_ALPHA : (isMatch ? 0.72 : 0.72);
      const edgeCol = isMatch ? bColor : (isSearchActive ? hexToRgba(bColor, DIM_ALPHA) : bColor);

      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = edgeCol;
      ctx.lineWidth   = 2 / scale;
      ctx.beginPath();

      if (x1 === x2) {
        // Same lane: straight vertical line
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
      } else {
        // Cross-lane: L-shaped cubic bezier
        const midY = (y1 + y2) / 2;
        ctx.moveTo(x1, y1);
        ctx.bezierCurveTo(x1, midY, x2, midY, x2, y2);
      }
      ctx.stroke();
      ctx.restore();
    }
  }
}

function drawNode(n: DagNode, isHover: boolean): void {
  const p = _layout.pos[n.commitId];
  if (!p) return;
  const cx  = nodeX(p.lane);
  const cy  = nodeY(p.row);
  const bc  = _layout.laneColors[n.branch] ?? '#8b949e';
  const nc  = nodeSemanticColor(n, bc);   // commit-type fill (the Muse differentiator)
  const isHead  = n.commitId === _headId || n.isHead;
  const isMerge = (n.parentIds ?? []).length > 1;
  const inSess  = Boolean(_sessMap[n.commitId]);
  const isSearchActive = matchSet !== null;
  const isMatch = !matchSet || matchSet.has(n.commitId);
  const alpha   = isSearchActive && !isMatch ? DIM_ALPHA : 1;

  ctx.save();
  ctx.globalAlpha = alpha;

  // ── Outermost rings (session, breaking, HEAD glow) ──────────────────────
  if (n.isBreaking) {
    // Red pulsing ring for breaking changes — impossible to miss
    ctx.shadowBlur  = isHover ? 18 / scale : 10 / scale;
    ctx.shadowColor = BREAKING_COLOR;
    ctx.strokeStyle = BREAKING_COLOR;
    ctx.lineWidth   = 2 / scale;
    ctx.beginPath();
    ctx.arc(cx, cy, NODE_R + 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  if (isHead) {
    ctx.shadowBlur  = 14 / scale;
    ctx.shadowColor = HEAD_COLOR;
    ctx.strokeStyle = HEAD_COLOR;
    ctx.lineWidth   = 2 / scale;
    ctx.beginPath();
    ctx.arc(cx, cy, NODE_R + (n.isBreaking ? 12 : 5), 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  if (inSess) {
    ctx.strokeStyle = SESSION_COLOR;
    ctx.lineWidth   = 1.5 / scale;
    ctx.setLineDash([3 / scale, 2 / scale]);
    ctx.beginPath();
    ctx.arc(cx, cy, NODE_R + (isHead ? 10 : 8), 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── Hover ring ───────────────────────────────────────────────────────────
  if (isHover) {
    ctx.strokeStyle = nc;
    ctx.lineWidth   = 1.5 / scale;
    ctx.globalAlpha = alpha * 0.3;
    ctx.beginPath();
    ctx.arc(cx, cy, NODE_R + 12, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = alpha;
  }

  // ── Branch color ring (thin outer ring preserves lane identity) ──────────
  ctx.strokeStyle = bc;
  ctx.lineWidth   = 1.5 / scale;
  ctx.beginPath();
  ctx.arc(cx, cy, NODE_R + 2.5, 0, Math.PI * 2);
  ctx.stroke();

  // ── Node body — filled with commit-type color ────────────────────────────
  if (isMerge) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.PI / 4);
    const d = NODE_R * 0.9;
    ctx.fillStyle   = MERGE_COLOR;
    ctx.strokeStyle = '#0d1117';
    ctx.lineWidth   = 1.5 / scale;
    ctx.shadowBlur  = isHover ? 10 / scale : 0;
    ctx.shadowColor = MERGE_COLOR;
    ctx.beginPath();
    ctx.roundRect(-d, -d, d * 2, d * 2, 2 / scale);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.restore();
  } else {
    ctx.fillStyle   = nc;
    ctx.strokeStyle = '#0d1117';
    ctx.lineWidth   = 1 / scale;
    ctx.shadowBlur  = isHover ? 12 / scale : 4 / scale;
    ctx.shadowColor = nc;
    ctx.beginPath();
    ctx.arc(cx, cy, NODE_R, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // ── Inner label (agent "AI" vs author initial) ───────────────────────────
  if (scale > 0.4) {
    ctx.fillStyle    = '#0d1117';
    ctx.font         = 'bold 9px system-ui';
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    const label = n.isAgent ? 'AI' : (n.author || '?')[0].toUpperCase();
    ctx.fillText(label, cx, cy + 0.5);
  }

  // ── Semver pip (top-right corner) ────────────────────────────────────────
  const bump = n.semVerBump ?? 'none';
  const pipColor = SEMVER_COLORS[bump];
  if (pipColor && scale > 0.25) {
    const pipR = bump === 'major' ? 3.5 / scale : 2.5 / scale;
    const pipX = cx + NODE_R * 0.72;
    const pipY = cy - NODE_R * 0.72;
    ctx.fillStyle   = pipColor;
    ctx.strokeStyle = '#0d1117';
    ctx.lineWidth   = 0.8 / scale;
    ctx.shadowBlur  = bump === 'major' ? 6 / scale : 0;
    ctx.shadowColor = pipColor;
    ctx.beginPath();
    ctx.arc(pipX, pipY, pipR, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  ctx.restore();
}

function drawPill(
  text: string,
  x: number,
  cy: number,
  fillColor: string,
  textColor: string,
  h = 16,
  padX = 7,
): number {
  ctx.font = 'bold 10px JetBrains Mono, Menlo, monospace';
  const tw = ctx.measureText(text).width;
  const pw = tw + padX * 2;
  ctx.fillStyle = fillColor;
  ctx.beginPath();
  ctx.roundRect(x, cy - h / 2, pw, h, 4);
  ctx.fill();
  ctx.fillStyle = textColor;
  ctx.fillText(text, x + padX, cy + 0.5);
  return pw + 6;
}

function drawLabel(n: DagNode, isHover: boolean): void {
  const p = _layout.pos[n.commitId];
  if (!p) return;
  const cy    = nodeY(p.row);
  const isSearchActive = matchSet !== null;
  const isMatch = !matchSet || matchSet.has(n.commitId);
  const alpha   = isSearchActive && !isMatch ? DIM_ALPHA : 1;

  if (scale < 0.28) return;

  ctx.save();
  ctx.globalAlpha = alpha;

  const sha7    = n.commitId.substring(0, 7);
  const ctype   = commitType(n);
  const typeCol = ctype ? (TYPE_COLORS[ctype] ?? null) : null;
  const bodyMsg = ctype ? n.message.replace(/^\w+(\([^)]*\))?!?\s*:\s*/, '') : n.message;
  const isHead  = n.commitId === _headId || n.isHead;

  let x = _layout.labelX;

  // SHA badge
  ctx.font         = '11px JetBrains Mono, Menlo, monospace';
  ctx.fillStyle    = isHover ? '#79c0ff' : '#58a6ff';
  ctx.textAlign    = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(sha7, x, cy);
  x += ctx.measureText(sha7).width + 10;

  // Commit type pill
  if (typeCol && ctype) {
    x += drawPill(ctype, x, cy, hexToRgba(typeCol, 0.18), typeCol);
    ctx.fillStyle = '#6e7681';
    ctx.font      = '13px system-ui, -apple-system, sans-serif';
    ctx.fillText(': ', x, cy);
    x += ctx.measureText(': ').width;
  }

  // Breaking badge
  if (n.isBreaking) {
    x += drawPill('BREAKING', x, cy, hexToRgba(BREAKING_COLOR, 0.2), BREAKING_COLOR, 16, 6);
  }

  // Message
  const vpW      = canvas.clientWidth;
  const maxW     = vpW - x * scale - tx - 220;
  const maxChars = Math.max(10, Math.floor(maxW / (scale * 7.5)));
  const display  = bodyMsg.length > maxChars ? bodyMsg.substring(0, maxChars - 1) + '…' : bodyMsg;
  ctx.font      = `${isHover ? 'bold ' : ''}13px system-ui, -apple-system, sans-serif`;
  ctx.fillStyle = isHover ? '#ffffff' : '#c9d1d9';
  ctx.fillText(display, x, cy);
  x += ctx.measureText(display).width + 14;

  // Branch labels
  for (const lbl of (n.branchLabels ?? [])) {
    const lc = _layout.laneColors[lbl] ?? colorFor(lbl);
    ctx.font = 'bold 10px JetBrains Mono, Menlo, monospace';
    x += drawPill(lbl, x, cy, hexToRgba(lc, 0.2), lc, 18, 7);
  }

  // HEAD badge
  if (isHead) {
    ctx.font = 'bold 10px JetBrains Mono, Menlo, monospace';
    x += drawPill('HEAD', x, cy, hexToRgba(HEAD_COLOR, 0.25), HEAD_COLOR, 18, 7);
  }

  // Agent badge (only when zoomed in enough)
  if (n.isAgent && scale > 0.6) {
    x += drawPill('agent', x, cy, hexToRgba(AGENT_COLOR, 0.18), AGENT_COLOR);
  }

  // Semver bump badge
  const bump = n.semVerBump ?? 'none';
  const bumpCol = SEMVER_COLORS[bump];
  if (bumpCol && scale > 0.6) {
    drawPill(bump, x, cy, hexToRgba(bumpCol, 0.18), bumpCol);
  }

  // Time (right-aligned, dimmer)
  if (scale > 0.5 && n.timestamp) {
    const ago = timeAgo(n.timestamp);
    ctx.font      = '11px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#484f58';
    ctx.textAlign = 'right';
    ctx.fillText(ago, (vpW - 8) / scale - tx / scale, cy);
  }

  ctx.restore();
}

// ── Minimap ───────────────────────────────────────────────────────────────────

function drawMinimap(): void {
  if (!mmCtx) return;
  const MW = MM_W, MH = MM_H;
  mmCtx.clearRect(0, 0, MW, MH);

  // Background
  mmCtx.fillStyle = 'rgba(22,27,34,0.92)';
  mmCtx.fillRect(0, 0, MW, MH);
  mmCtx.strokeStyle = 'rgba(48,54,61,0.8)';
  mmCtx.lineWidth   = 1;
  mmCtx.strokeRect(0, 0, MW, MH);

  const totalH  = PAD_T * 2 + _layout.rows.length * ROW_H;
  const totalW  = _layout.labelX + 400;
  const scaleX  = (MW - 4) / totalW;
  const scaleY  = (MH - 4) / totalH;

  // Draw miniature edges (simplified)
  mmCtx.strokeStyle = 'rgba(88,166,255,0.25)';
  mmCtx.lineWidth   = 0.5;
  for (const n of _layout.rows) {
    const p = _layout.pos[n.commitId];
    if (!p) continue;
    const cx = (nodeX(p.lane) * scaleX + 2);
    const cy = (nodeY(p.row)  * scaleY + 2);
    for (const pid of (n.parentIds ?? [])) {
      const pp = _layout.pos[pid];
      if (!pp) continue;
      mmCtx.beginPath();
      mmCtx.moveTo(cx, cy);
      mmCtx.lineTo(nodeX(pp.lane) * scaleX + 2, nodeY(pp.row) * scaleY + 2);
      mmCtx.stroke();
    }
  }

  // Draw miniature nodes — colored by commit type (semantic encoding)
  for (const n of _layout.rows) {
    const p = _layout.pos[n.commitId];
    if (!p) continue;
    const cx = nodeX(p.lane) * scaleX + 2;
    const cy = nodeY(p.row)  * scaleY + 2;
    const isHead = n.commitId === _headId;
    const bc = _layout.laneColors[n.branch] ?? '#8b949e';
    const nc = nodeSemanticColor(n, bc);
    mmCtx.fillStyle = isHead ? HEAD_COLOR : (nc + 'cc');
    mmCtx.beginPath();
    mmCtx.arc(cx, cy, isHead ? 3 : 1.5, 0, Math.PI * 2);
    mmCtx.fill();
  }

  // Viewport rectangle
  const vpW = canvas.clientWidth;
  const vpH = canvas.clientHeight;
  const rx  = (-tx / scale) * scaleX + 2;
  const ry  = (-ty / scale) * scaleY + 2;
  const rw  = (vpW / scale) * scaleX;
  const rh  = (vpH / scale) * scaleY;
  mmCtx.strokeStyle = 'rgba(88,166,255,0.6)';
  mmCtx.lineWidth   = 1.5;
  mmCtx.fillStyle   = 'rgba(88,166,255,0.06)';
  mmCtx.fillRect(rx, ry, rw, rh);
  mmCtx.strokeRect(rx, ry, rw, rh);
}

// ── Main draw ─────────────────────────────────────────────────────────────────

function draw(): void {
  const vpW = canvas.clientWidth;
  const vpH = canvas.clientHeight;
  ctx.clearRect(0, 0, vpW, vpH);

  // Compute visible row range for culling
  const [, wTop]    = screenToWorld(0, 0);
  const [, wBottom] = screenToWorld(0, vpH);

  ctx.save();
  ctx.translate(tx, ty);
  ctx.scale(scale, scale);

  drawEdges();

  for (let i = 0; i < _layout.rows.length; i++) {
    const n  = _layout.rows[i];
    const wy = nodeY(i);
    if (wy < wTop - ROW_H || wy > wBottom + ROW_H) continue;
    drawNode(n, n.commitId === hoverId);
  }

  // Labels after nodes (they overdraw edges)
  for (let i = 0; i < _layout.rows.length; i++) {
    const n  = _layout.rows[i];
    const wy = nodeY(i);
    if (wy < wTop - ROW_H || wy > wBottom + ROW_H) continue;
    drawLabel(n, n.commitId === hoverId);
  }

  ctx.restore();
  drawMinimap();
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function showTooltip(e: MouseEvent, cid: string): void {
  const tip = document.getElementById('dag-popover');
  if (!tip) return;
  const n = _nodeMap[cid];
  if (!n) return;

  const bc    = _layout.laneColors[n.branch] ?? '#8b949e';
  const ctype = commitType(n);
  const tc    = ctype ? (TYPE_COLORS[ctype] ?? null) : null;
  const body  = ctype ? n.message.replace(/^\w+(\([^)]*\))?!?\s*:\s*/, '') : n.message;

  const popSha     = document.getElementById('pop-sha');
  const popBranch  = document.getElementById('pop-branch-badge') as HTMLElement | null;
  const popMsg     = document.getElementById('pop-msg');
  const popAuthor  = document.getElementById('pop-author');
  const popAvatar  = document.getElementById('pop-avatar') as HTMLElement | null;
  const popTime    = document.getElementById('pop-time');
  const popSession = document.getElementById('pop-session') as HTMLElement | null;
  const popType    = document.getElementById('pop-type') as HTMLElement | null;
  const popMuse    = document.getElementById('pop-muse') as HTMLElement | null;

  if (popSha)    popSha.textContent    = n.commitId.substring(0, 12);
  if (popBranch) {
    popBranch.textContent       = n.branch;
    popBranch.style.background  = bc + '22';
    popBranch.style.color       = bc;
    popBranch.style.borderColor = bc + '44';
  }
  if (popMsg)    popMsg.textContent    = body.length > 120 ? body.substring(0, 117) + '…' : body;
  if (popAuthor) popAuthor.textContent = n.author;
  if (popAvatar) {
    popAvatar.textContent      = n.isAgent ? '✦' : (n.author || '?')[0].toUpperCase();
    popAvatar.style.background = n.isAgent ? AGENT_COLOR : colorFor(n.author);
  }
  if (popTime)   popTime.textContent   = timeAgo(n.timestamp);
  if (popType && ctype && tc) {
    popType.textContent       = ctype;
    popType.style.display     = 'inline-flex';
    popType.style.background  = tc + '22';
    popType.style.color       = tc;
    popType.style.borderColor = tc + '44';
  } else if (popType) {
    popType.style.display = 'none';
  }
  const sess = _sessMap[cid];
  if (popSession) {
    popSession.textContent = sess?.intent ? `◯ ${sess.intent}` : '';
    popSession.style.display = sess?.intent ? 'block' : 'none';
  }

  // Muse-specific enrichment row
  if (popMuse) {
    const parts: string[] = [];
    if (n.isAgent)    parts.push(`<span class="pop-muse-badge pop-muse-agent">✦ agent</span>`);
    if (n.isBreaking) parts.push(`<span class="pop-muse-badge pop-muse-breaking">⚡ breaking</span>`);
    const bump = n.semVerBump ?? 'none';
    if (bump && bump !== 'none') {
      const bumpHex = SEMVER_COLORS[bump] ?? '#8b949e';
      parts.push(`<span class="pop-muse-badge" style="background:${bumpHex}22;color:${bumpHex};border-color:${bumpHex}44">${bump}</span>`);
    }
    if ((n.symAdded ?? 0) > 0 || (n.symRemoved ?? 0) > 0) {
      const addStr = (n.symAdded ?? 0) > 0 ? `<span class="pop-sym-add">+${n.symAdded} sym</span>` : '';
      const delStr = (n.symRemoved ?? 0) > 0 ? `<span class="pop-sym-del">−${n.symRemoved} sym</span>` : '';
      parts.push(`<span class="pop-sym-stats">${addStr}${addStr && delStr ? ' ' : ''}${delStr}</span>`);
    }
    popMuse.innerHTML = parts.join('');
    popMuse.style.display = parts.length ? 'flex' : 'none';
  }

  tip.style.display = 'block';
  const vw = window.innerWidth, vh = window.innerHeight;
  let px = e.clientX + 20, py = e.clientY - 10;
  if (px + 380 > vw) px = e.clientX - 390;
  if (py + 280 > vh) py = e.clientY - 280;
  tip.style.left = px + 'px';
  tip.style.top  = py + 'px';
}

function hideTooltip(): void {
  if (pinned) return;
  const tip = document.getElementById('dag-popover');
  if (tip) tip.style.display = 'none';
}

// ── Sidebar population ────────────────────────────────────────────────────────

function populateSidebar(nodes: DagNode[]): void {
  const authorCounts: Record<string, number> = {};
  const typeCounts:   Record<string, number> = {};
  nodes.forEach(n => {
    authorCounts[n.author] = (authorCounts[n.author] || 0) + 1;
    const ct = commitType(n) ?? 'other';
    typeCounts[ct] = (typeCounts[ct] || 0) + 1;
  });
  const authors    = Object.entries(authorCounts).sort((a, b) => b[1] - a[1]);
  const maxC       = authors[0]?.[1] ?? 1;
  const mergeCount = nodes.filter(n => (n.parentIds ?? []).length > 1).length;
  const agentCount = nodes.filter(n => n.isAgent).length;
  const breakCount = nodes.filter(n => n.isBreaking).length;

  const statAuthors  = document.getElementById('stat-authors');
  const statMerges   = document.getElementById('stat-merges');
  const statAgents   = document.getElementById('stat-agents');
  const statBreaking = document.getElementById('stat-breaking');
  if (statAuthors)  statAuthors.textContent  = String(authors.length);
  if (statMerges)   statMerges.textContent   = String(mergeCount);
  if (statAgents)   statAgents.textContent   = String(agentCount);
  if (statBreaking) statBreaking.textContent = String(breakCount);

  const branches = Object.keys(_layout.laneColors);
  const branchCounts: Record<string, number> = {};
  nodes.forEach(n => { branchCounts[n.branch] = (branchCounts[n.branch] || 0) + 1; });

  const legendBranches = document.getElementById('legend-branches');
  if (legendBranches) {
    legendBranches.innerHTML = branches.map(b =>
      `<span class="graph-legend-branch">
        <span class="graph-legend-dot" style="background:${_layout.laneColors[b]}"></span>
        ${window.escHtml(b)}
      </span>`
    ).join('');
  }

  // Commit-type legend (what makes Muse unique)
  const legendTypes = document.getElementById('legend-types');
  if (legendTypes) {
    const typeOrder = ['feat','fix','refactor','perf','chore','docs','test','style','build','ci','revert','init'];
    const present   = typeOrder.filter(t => typeCounts[t]);
    if (present.length) {
      legendTypes.innerHTML = present.map(t =>
        `<span class="graph-legend-type">
          <span class="graph-legend-dot" style="background:${TYPE_COLORS[t] ?? '#8b949e'}"></span>
          ${window.escHtml(t)} <span class="graph-legend-type-count">${typeCounts[t]}</span>
        </span>`
      ).join('');
      legendTypes.style.display = 'flex';
    } else {
      legendTypes.style.display = 'none';
    }
  }

  const sidebarBranches = document.getElementById('sidebar-branch-list');
  if (sidebarBranches) {
    sidebarBranches.innerHTML = branches.map(b =>
      `<div class="branch-legend-item">
        <span class="branch-legend-pill" style="background:${_layout.laneColors[b]}"></span>
        <span class="branch-legend-name">${window.escHtml(b)}</span>
        <span class="branch-legend-count">${branchCounts[b] ?? 0}</span>
      </div>`
    ).join('');
  }

  // Commit type breakdown card
  const sidebarTypes = document.getElementById('sidebar-type-list');
  if (sidebarTypes) {
    const sorted = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
    const maxT   = sorted[0]?.[1] ?? 1;
    sidebarTypes.innerHTML = sorted.map(([t, cnt]) => {
      const col = TYPE_COLORS[t] ?? '#6e7681';
      const pct = Math.round((cnt / maxT) * 100);
      return `<div class="contributor-item">
        <span class="contributor-avatar-sm" style="background:${col};color:#0d1117;font-size:9px;font-weight:700">${window.escHtml(t[0].toUpperCase())}</span>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:4px">
            <span class="contributor-name" style="color:${col}">${window.escHtml(t)}</span>
            <span class="contributor-count">${cnt}</span>
          </div>
          <div class="contributor-bar">
            <div class="contributor-bar-fill" style="width:${pct}%;background:${col}"></div>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  const sidebarContribs = document.getElementById('sidebar-contributor-list');
  if (sidebarContribs) {
    sidebarContribs.innerHTML = authors.map(([author, count]) => {
      const pct    = Math.round((count / maxC) * 100);
      const acolor = colorFor(author);
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
}

// ── Search ────────────────────────────────────────────────────────────────────

function applySearch(q: string): void {
  searchQuery = q.trim().toLowerCase();
  if (!searchQuery) {
    matchSet = null;
  } else {
    matchSet = new Set<string>();
    for (const n of _layout.rows) {
      if (
        n.message.toLowerCase().includes(searchQuery) ||
        n.author.toLowerCase().includes(searchQuery) ||
        n.commitId.toLowerCase().startsWith(searchQuery) ||
        n.branch.toLowerCase().includes(searchQuery)
      ) {
        matchSet.add(n.commitId);
      }
    }
    // Update match count badge
    const badge = document.getElementById('search-match-count');
    if (badge) badge.textContent = matchSet.size > 0 ? `${matchSet.size} match${matchSet.size > 1 ? 'es' : ''}` : 'no match';
  }
  const badge = document.getElementById('search-match-count');
  if (badge) badge.textContent = matchSet ? (matchSet.size > 0 ? `${matchSet.size} match${matchSet.size !== 1 ? 'es' : ''}` : 'no match') : '';
  scheduleRedraw();
}

// ── Pan / Zoom ────────────────────────────────────────────────────────────────

function clampView(): void {
  const vpH     = canvas.clientHeight;
  const totalH  = PAD_T * 2 + _layout.rows.length * ROW_H;
  const minTy   = Math.min(0, vpH - totalH * scale - PAD_T * scale);
  ty = Math.max(minTy, Math.min(PAD_T, ty));
}

function zoomAround(cx: number, cy: number, factor: number): void {
  const ns = Math.max(0.12, Math.min(5, scale * factor));
  tx = cx - (cx - tx) * (ns / scale);
  ty = cy - (cy - ty) * (ns / scale);
  scale = ns;
  clampView();
  scheduleRedraw();
  updateZoomLabel();
}

function updateZoomLabel(): void {
  const lbl = document.getElementById('zoom-level');
  if (lbl) lbl.textContent = Math.round(scale * 100) + '%';
}

function scrollToHead(): void {
  // HEAD is index 0 (newest-first display)
  const headRow = _layout.rows.findIndex(n => n.commitId === _headId);
  if (headRow < 0) return;
  const vpH  = canvas.clientHeight;
  const headY = nodeY(headRow);
  ty = vpH / 2 - headY * scale;
  clampView();
  scheduleRedraw();
}

// ── Event wiring ──────────────────────────────────────────────────────────────

function wireCanvas(vp: HTMLElement): void {
  let dragging = false;
  let dragSX = 0, dragSY = 0;
  let hasMoved = false;

  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    // Pinch-to-zoom on macOS trackpads sends ctrlKey=true with wheel events.
    // Plain two-finger scroll should pan the graph, not zoom.
    if (e.ctrlKey || e.metaKey) {
      // Zoom: pinch gesture or Ctrl/Cmd + scroll
      const factor = e.deltaY < 0 ? 1.12 : 0.89;
      zoomAround(e.clientX - rect.left, e.clientY - rect.top, factor);
    } else {
      // Pan: two-finger scroll — translate vertically (and horizontally for trackpads)
      tx -= e.deltaX;
      ty -= e.deltaY;
      clampView();
      scheduleRedraw();
    }
  }, { passive: false });

  canvas.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    dragging = true; hasMoved = false;
    dragSX = e.clientX; dragSY = e.clientY;
    pinned = null;
    const tip = document.getElementById('dag-popover');
    if (tip) tip.style.display = 'none';
  });

  window.addEventListener('mouseup', e => {
    if (!dragging) return;
    if (!hasMoved) {
      // It was a click, not a drag
      const rect = canvas.getBoundingClientRect();
      const cid  = hitTest(e.clientX - rect.left, e.clientY - rect.top);
      if (cid) window.location.href = _baseUrl + '/commits/' + cid;
    }
    dragging = false;
  });

  window.addEventListener('mousemove', e => {
    if (dragging) {
      const dx = e.clientX - dragSX;
      const dy = e.clientY - dragSY;
      if (Math.abs(dx) + Math.abs(dy) > 3) hasMoved = true;
      tx += dx; ty += dy;
      dragSX = e.clientX; dragSY = e.clientY;
      clampView();
      scheduleRedraw();
      return;
    }
    // Hover hit test
    const rect   = canvas.getBoundingClientRect();
    const cid    = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (cid !== hoverId) {
      hoverId = cid;
      canvas.style.cursor = cid ? 'pointer' : 'grab';
      scheduleRedraw();
    }
    if (cid) showTooltip(e, cid);
    else hideTooltip();
  });

  canvas.addEventListener('mouseleave', () => {
    hoverId = null;
    hideTooltip();
    scheduleRedraw();
  });

  // Touch support
  let touchStartY = 0, touchLastY = 0, touchStartScale = 1;
  let touch2Dist = 0;
  canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      touch2Dist  = Math.sqrt(dx * dx + dy * dy);
      touchStartScale = scale;
    } else {
      touchStartY = touchLastY = e.touches[0].clientY;
    }
  }, { passive: false });
  canvas.addEventListener('touchmove', e => {
    e.preventDefault();
    if (e.touches.length === 2) {
      const dx   = e.touches[0].clientX - e.touches[1].clientX;
      const dy   = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      const rect = canvas.getBoundingClientRect();
      zoomAround(midX - rect.left, midY - rect.top, dist / touch2Dist);
      touch2Dist = dist;
    } else {
      const curY = e.touches[0].clientY;
      ty += curY - touchLastY;
      touchLastY = curY;
      clampView();
      scheduleRedraw();
    }
  }, { passive: false });

  // Zoom controls
  document.addEventListener('click', e => {
    const t = (e.target as Element).closest<HTMLElement>('[data-action]');
    if (!t) return;
    const vpRect = canvas.getBoundingClientRect();
    const cx     = vpRect.width / 2;
    const cy     = vpRect.height / 2;
    switch (t.dataset.action) {
      case 'zoom-in':    zoomAround(cx, cy, 1.3); break;
      case 'zoom-out':   zoomAround(cx, cy, 0.77); break;
      case 'zoom-reset': scale = 1; tx = 0; scrollToHead(); updateZoomLabel(); break;
    }
  });

  // Minimap click to navigate
  const mmEl = document.getElementById('dag-minimap');
  if (mmEl) {
    mmEl.addEventListener('click', e => {
      const rect   = mmEl.getBoundingClientRect();
      const mx     = e.clientX - rect.left;
      const my     = e.clientY - rect.top;
      const totalH = PAD_T * 2 + _layout.rows.length * ROW_H;
      const totalW = _layout.labelX + 400;
      const scaleY = (MM_H - 4) / totalH;
      const wy     = (my - 2) / scaleY;
      const vpH    = canvas.clientHeight;
      ty = vpH / 2 - wy * scale;
      clampView();
      scheduleRedraw();
    });
  }

  window.addEventListener('resize', () => {
    resizeCanvas();
    scheduleRedraw();
  });
}

// ── Session map ───────────────────────────────────────────────────────────────

function buildSessionMap(sessions: SessionEntry[]): SessionMap {
  const map: SessionMap = {};
  const sorted = [...sessions].sort((a, b) =>
    new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  );
  sorted.forEach(s => {
    (s.commits ?? []).forEach(cid => {
      if (!map[cid]) map[cid] = { intent: s.intent ?? '', sessionId: s.sessionId };
    });
  });
  return map;
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

function normaliseSsrDag(ssr: SsrDagData): DagData {
  // The SSR payload uses Python snake_case; normalise to the camelCase shape
  // that the rest of graph.ts expects (matching the /repos/{id}/dag API response).
  return {
    headCommitId: ssr.head_commit_id ?? '',
    edges: ssr.edges,
    nodes: ssr.nodes.map(n => ({
      commitId:     n.commit_id,
      message:      n.message,
      author:       n.author,
      timestamp:    n.timestamp,
      branch:       n.branch,
      parentIds:    n.parent_ids,
      isHead:       n.is_head,
      branchLabels: n.branch_labels,
      tagLabels:    n.tag_labels,
      commitType:   n.commit_type,
      semVerBump:   n.sem_ver_bump,
      isBreaking:   n.is_breaking,
      isAgent:      n.is_agent,
      symAdded:     n.sym_added,
      symRemoved:   n.sym_removed,
    })),
  };
}

async function load(cfg: GraphCfg): Promise<void> {
  if (typeof window.initRepoNav === 'function') window.initRepoNav(cfg.repoId);

  const loadingEl = document.getElementById('dag-loading');

  try {
    // Use SSR-injected DAG data when available to avoid a round-trip on first paint.
    // The sessions fetch is always async (not worth SSR-ing for this panel).
    const ssrDag = window.__graphData;
    const [dagData, sessData] = await Promise.all([
      ssrDag
        ? Promise.resolve(normaliseSsrDag(ssrDag))
        : window.apiFetch('/repos/' + cfg.repoId + '/dag') as Promise<DagData>,
      window.apiFetch('/repos/' + cfg.repoId + '/sessions?limit=200').catch(() => ({ sessions: [] })),
    ]) as [DagData, { sessions?: SessionEntry[] }];

    if (loadingEl) loadingEl.style.display = 'none';

    if (!dagData.nodes.length) {
      const vp = document.getElementById('dag-viewport');
      if (vp) vp.innerHTML = '<div class="graph-empty">No commits yet.</div>';
      return;
    }

    _headId  = dagData.headCommitId;
    _baseUrl = cfg.baseUrl;
    _sessMap = buildSessionMap(sessData.sessions ?? []);
    _layout  = buildLayout(dagData.nodes, dagData.edges);

    dagData.nodes.forEach(n => { _nodeMap[n.commitId] = n; });

    // Wire up canvas
    canvas  = document.getElementById('dag-canvas') as HTMLCanvasElement;
    mmCanvas = document.getElementById('dag-minimap') as HTMLCanvasElement;
    ctx     = canvas.getContext('2d')!;
    mmCtx   = mmCanvas?.getContext('2d')!;
    const vp = canvas.parentElement!;

    resizeCanvas();
    wireCanvas(vp);

    // Wire search
    const searchInput = document.getElementById('dag-search') as HTMLInputElement | null;
    if (searchInput) {
      searchInput.addEventListener('input', () => applySearch(searchInput.value));
      searchInput.addEventListener('keydown', e => { if (e.key === 'Escape') { searchInput.value = ''; applySearch(''); } });
    }

    // Initial view: show HEAD at top-ish
    scale = 1;
    tx    = 0;
    scrollToHead();
    updateZoomLabel();
    populateSidebar(dagData.nodes);
    draw();

  } catch (err) {
    const e = err as Error;
    if (e.message !== 'auth' && loadingEl) {
      loadingEl.innerHTML = `<span style="color:var(--color-danger)">✕ ${window.escHtml(e.message)}</span>`;
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initGraph(): void {
  const cfg = window.__graphCfg;
  if (!cfg) return;
  void load(cfg);
}
