/**
 * forks.ts — Fork network SVG DAG renderer page module.
 *
 * Config is read from window.__forksCfg (set by the page_data block).
 * Registered as: window.MusePages['forks']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface ForksCfg {
  repoId: string;
  owner: string;
  repoSlug: string;
  base: string;
  forkNetwork: ForkNetwork;
}

interface ForkNode {
  owner: string;
  repoSlug: string;
  divergenceCommits?: number;
  forkedBy?: string;
  children?: ForkNode[];
}

interface ForkNetwork {
  root?: ForkNode;
}

declare global {
  interface Window { __forksCfg?: ForksCfg; }
}

// Globals injected from musehub.ts bundle
declare const escHtml: (s: unknown) => string;
declare const initRepoNav: (id: string) => void;

// ── Layout constants ──────────────────────────────────────────────────────────

const NW = 140, NH = 50, HGAP = 50, VGAP = 80, PAD = 20;

// ── Colour scale by divergence ────────────────────────────────────────────────

function divColour(ahead: number): string {
  if (ahead === 0)  return '#3fb950';
  if (ahead <= 5)   return '#d29922';
  if (ahead <= 20)  return '#e3964e';
  return '#f85149';
}

// ── SVG namespace helper ──────────────────────────────────────────────────────

function svgEl(tag: string, attrs: Record<string, string | number>): SVGElement {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

// ── Layout ────────────────────────────────────────────────────────────────────

interface LayoutResult {
  svgW: number;
  svgH: number;
  rootX: number;
  rootY: number;
  children: Array<{ x: number; y: number; node: ForkNode }>;
}

function buildLayout(forks: ForkNode[]): LayoutResult {
  const colCount = Math.max(1, forks.length);
  const svgW = Math.max(500, colCount * (NW + HGAP) + HGAP);

  const rootX = svgW / 2 - NW / 2;
  const rootY = PAD;

  const childY  = PAD + NH + VGAP;
  const totalW  = forks.length * NW + Math.max(0, forks.length - 1) * HGAP;
  const startX  = svgW / 2 - totalW / 2;
  const svgH    = forks.length > 0 ? childY + NH + PAD : NH + PAD * 2;

  const children = forks.map((f, i) => ({
    x: startX + i * (NW + HGAP),
    y: childY,
    node: f,
  }));

  return { svgW, svgH, rootX, rootY, children };
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function showDetail(cfg: ForksCfg, node: ForkNode, isRoot: boolean): void {
  const panel = document.getElementById('fork-detail');
  if (!panel) return;
  panel.style.display = '';

  const ahead      = node.divergenceCommits ?? 0;
  const col        = divColour(ahead);
  const initial    = (node.owner ?? '?').charAt(0).toUpperCase();
  const repoHref   = `/${escHtml(node.owner)}/${escHtml(node.repoSlug)}`;
  const compareHref = `${cfg.base}/compare/${encodeURIComponent(node.repoSlug)}`;
  const prHref     = `${cfg.base}/pulls/new?head=${encodeURIComponent(node.owner + ':main')}`;

  panel.innerHTML = `
    <div class="fork-card">
      <div class="fork-card-title">
        <span class="avatar-badge">${escHtml(initial)}</span>
        <a href="${repoHref}" class="fork-card-link">
          ${escHtml(node.owner)}/${escHtml(node.repoSlug)}
        </a>
        ${isRoot ? ' <span class="fork-upstream-badge">&#9673; upstream</span>' : ''}
      </div>
      <div class="fork-card-meta">
        ${isRoot
          ? 'This is the upstream (source) repository.'
          : `Forked by <strong>${escHtml(node.forkedBy ?? node.owner)}</strong>
             &bull; <span style="color:${col}">+${ahead} commit${ahead !== 1 ? 's' : ''} ahead</span>`}
      </div>
      <div class="fork-card-actions">
        ${!isRoot ? `
          <a class="btn btn-secondary" href="${compareHref}">&#128256; Compare</a>
          <a class="btn btn-primary"   href="${prHref}">&#8593; Contribute upstream</a>
        ` : ''}
        <a class="btn btn-secondary" href="${repoHref}">View repo &rarr;</a>
      </div>
    </div>`;
}

// ── SVG node ──────────────────────────────────────────────────────────────────

function makeNode(cfg: ForksCfg, x: number, y: number, node: ForkNode, isRoot: boolean): SVGElement {
  const g = svgEl('g', {
    style: 'cursor:pointer',
    tabindex: '0',
    role: 'button',
    'aria-label': `${node.owner}/${node.repoSlug}`,
  });
  const col = isRoot ? '#3fb950' : divColour(node.divergenceCommits ?? 0);

  g.appendChild(svgEl('rect', {
    x, y, width: NW, height: NH,
    rx: '8', ry: '8',
    fill: 'var(--bg-overlay, #161b22)',
    stroke: col,
    'stroke-width': isRoot ? '2' : '1.5',
  }));

  const lbl = svgEl('text', { x: x + NW / 2, y: y + 18, class: 'fork-node-label' });
  lbl.textContent = `${node.owner}/${node.repoSlug}`;
  g.appendChild(lbl);

  const sub = svgEl('text', { x: x + NW / 2, y: y + 34, class: 'fork-node-sub', fill: col });
  if (isRoot) {
    sub.textContent = '\u25c9 upstream';
    sub.setAttribute('fill', '#3fb950');
  } else {
    const a = node.divergenceCommits ?? 0;
    sub.textContent = a === 0 ? '\u2261 in sync' : `+${a} ahead`;
  }
  g.appendChild(sub);

  g.addEventListener('click', () => showDetail(cfg, node, isRoot));
  g.addEventListener('keydown', (e: Event) => {
    const ke = e as KeyboardEvent;
    if (ke.key === 'Enter' || ke.key === ' ') showDetail(cfg, node, isRoot);
  });

  return g;
}

// ── Render the SVG DAG ────────────────────────────────────────────────────────

function renderDAG(cfg: ForksCfg, rootNode: ForkNode, forks: ForkNode[]): void {
  const { svgW, svgH, rootX, rootY, children } = buildLayout(forks);
  const svg = document.getElementById('fork-svg');
  if (!svg) return;
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  svg.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
  svg.setAttribute('width', String(svgW));
  svg.setAttribute('height', String(svgH));

  const defs   = svgEl('defs', {});
  const marker = svgEl('marker', {
    id: 'arr', markerWidth: '8', markerHeight: '6',
    refX: '7', refY: '3', orient: 'auto',
  });
  marker.appendChild(svgEl('polygon', { points: '0 0, 8 3, 0 6', fill: '#8b949e' }));
  defs.appendChild(marker);
  svg.appendChild(defs);

  const rx = rootX + NW / 2;
  const ry = rootY + NH;
  for (const { x, y, node } of children) {
    const cx  = x + NW / 2;
    const mid = (ry + y) / 2;
    const col = divColour(node.divergenceCommits ?? 0);
    svg.appendChild(svgEl('path', {
      d: `M${rx},${ry} C${rx},${mid} ${cx},${mid} ${cx},${y}`,
      fill: 'none',
      stroke: col,
      'stroke-width': '1.5',
      'marker-end': 'url(#arr)',
    }));
  }

  svg.appendChild(makeNode(cfg, rootX, rootY, rootNode, true));
  for (const { x, y, node } of children) {
    svg.appendChild(makeNode(cfg, x, y, node, false));
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initForks(): void {
  const cfg = window.__forksCfg;
  if (!cfg) return;
  initRepoNav(cfg.repoId);
  const data  = cfg.forkNetwork ?? {};
  const root  = data.root ?? ({} as ForkNode);
  const forks = root.children ?? [];
  renderDAG(cfg, root, forks);
}
