/**
 * view.ts — Interactive symbol dependency graph for the MuseHub code domain view page.
 *
 * Reads SSR-injected data from ``page_json`` (commits list + initialDelta) and renders:
 *   - Commit navigator: scroll through the last 20 commits, newest first
 *   - D3 force-directed symbol graph: nodes = symbols, edges = call hierarchy
 *   - Three display modes: Graph (default) | Dead Code | Impact (blast radius)
 *   - Symbol info panel: click any node to inspect kind, file, op, callers/callees
 *   - Semantic Changes panel: file → symbol tree for the selected commit
 *   - Search + kind filter: real-time filtering of visible nodes
 *
 * Data flow:
 *   SSR page_json.commits       → commit navigator (zero round-trips on first paint)
 *   SSR page_json.initialDelta  → symbol graph on first paint
 *   GET /api/repos/{id}/commits/{cid}  → structured_delta on navigator click
 */

import * as d3 from 'd3';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChildOp {
  op: string;
  address: string;
  content_summary?: string;
}

interface FileOp {
  op: string;
  address: string;
  child_summary?: string;
  child_ops?: ChildOp[];
}

interface StructuredDelta {
  domain?: string;
  ops: FileOp[];
}

interface SlimCommit {
  id: string;
  message: string;
  author: string;
  branch: string;
  ts: string;
  agentId: string;
}

interface PageData {
  page: string;
  repoId?: string;
  owner?: string;
  slug?: string;
  ref?: string;
  viewerType?: string;
  domainScopedId?: string;
  domainDisplayName?: string;
  commits?: SlimCommit[];
  initialDelta?: StructuredDelta | null;
}

interface WireCommit {
  commit_id: string;
  branch: string;
  message: string;
  author: string;
  committed_at: string;
  structured_delta?: StructuredDelta | null;
}

interface SymNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  file: string;
  kind: string;       // class | method | function | variable | unknown
  op: string;         // insert | delete | replace | unknown
  summary: string;
  isDeadCode: boolean;
  fileOp: string;
}

interface SymEdge {
  source: string | SymNode;
  target: string | SymNode;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const OP_COLOR: Record<string, string> = {
  insert:  '#34d399',
  delete:  '#f87171',
  replace: '#fbbf24',
  patch:   '#fbbf24',
  unknown: '#94a3b8',
};

const KIND_FILL: Record<string, string> = {
  class:    '#a78bfa',
  method:   '#2dd4bf',
  function: '#60a5fa',
  variable: '#f9a825',
  unknown:  '#78909c',
};

const OP_LABEL: Record<string, string> = {
  insert:  'added',
  delete:  'removed',
  replace: 'modified',
  patch:   'modified',
  unknown: 'changed',
};

const NODE_R = 10;
const DEAD_DASHES = '3,3';
const SVG_ID = 'sv-sym-svg';

// ── Module state ──────────────────────────────────────────────────────────────

let _graphMode: 'default' | 'dead' | 'impact' = 'default';
let _selectedNode: SymNode | null = null;
let _simulation: d3.Simulation<SymNode, SymEdge> | null = null;
let _nodes: SymNode[] = [];
let _edges: SymEdge[] = [];
let _commits: SlimCommit[] = [];
let _activeCommitIdx = 0;
let _repoId = '';
let _filterText = '';
let _filterKind = '';

// ── Helpers ───────────────────────────────────────────────────────────────────

function detectKind(address: string, summary: string): string {
  const s = summary.toLowerCase();
  if (s.includes('class'))    return 'class';
  if (s.includes('method'))   return 'method';
  if (s.includes('function')) return 'function';
  if (s.includes('variable') || s.includes('constant')) return 'variable';
  if (address.includes('::')) {
    const sym = address.split('::').pop() ?? '';
    if (sym.includes('.')) return 'method';
  }
  return 'unknown';
}

function shortLabel(address: string): string {
  const sym = address.split('::').pop() ?? address;
  const part = sym.split('.').pop() ?? sym;
  return part.length > 16 ? part.slice(0, 15) + '…' : part;
}

function relativeTime(isoTs: string): string {
  const ms = Date.now() - new Date(isoTs).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60)   return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)   return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Graph construction ────────────────────────────────────────────────────────

function buildGraph(delta: StructuredDelta): { nodes: SymNode[]; edges: SymEdge[] } {
  const nodes: SymNode[] = [];
  const edges: SymEdge[] = [];
  const seen = new Set<string>();

  for (const fileOp of delta.ops) {
    const file = fileOp.address.split('/').pop() ?? fileOp.address;
    if (!fileOp.child_ops?.length) continue;

    const fileNodeIds: string[] = [];
    for (const co of fileOp.child_ops) {
      const id = co.address;
      if (seen.has(id)) continue;
      seen.add(id);

      const summary = co.content_summary ?? '';
      const kind = detectKind(co.address, summary);
      const isDeadCode =
        co.op === 'delete' ||
        summary.includes('0 callers') ||
        summary.includes('dead');

      nodes.push({
        id,
        label: shortLabel(co.address),
        file,
        kind,
        op: co.op || fileOp.op || 'unknown',
        summary,
        isDeadCode,
        fileOp: fileOp.op,
      });
      fileNodeIds.push(id);
    }

    // Infer parent → child edges from address hierarchy (e.g. MyClass.my_method)
    for (const nid of fileNodeIds) {
      const sym = nid.split('::').pop() ?? '';
      if (sym.includes('.')) {
        const parentSym = sym.split('.')[0];
        const parentId = fileNodeIds.find(pid => {
          const s = pid.split('::').pop() ?? '';
          return s === parentSym;
        });
        if (parentId && parentId !== nid) {
          edges.push({ source: parentId, target: nid });
        }
      }
    }
  }

  return { nodes, edges };
}

// ── Graph rendering ───────────────────────────────────────────────────────────

function renderGraph(delta: StructuredDelta): void {
  const svgEl = document.getElementById(SVG_ID) as SVGElement | null;
  const emptyEl = document.getElementById('sv-empty');
  if (!svgEl) return;

  if (_simulation) {
    _simulation.stop();
    _simulation = null;
  }
  _selectedNode = null;
  _graphMode = 'default';

  const { nodes, edges } = buildGraph(delta);

  if (!nodes.length) {
    svgEl.style.display = 'none';
    if (emptyEl) emptyEl.removeAttribute('hidden');
    _nodes = [];
    _edges = [];
    updateStats(0, 0);
    return;
  }

  svgEl.style.display = '';
  if (emptyEl) emptyEl.setAttribute('hidden', '');
  _nodes = nodes;
  _edges = edges;

  const wrap = document.getElementById('sv-graph-wrap');
  const W = wrap ? Math.max(wrap.clientWidth - 4, 400) : 600;
  const H = Math.max(300, Math.min(nodes.length * 30, 480));

  const svg = d3.select<SVGElement, unknown>(`#${SVG_ID}`)
    .attr('viewBox', `0 0 ${W} ${H}`)
    .attr('width', '100%')
    .attr('height', H);

  svg.selectAll('*').remove();

  // Arrowhead marker
  svg.append('defs').append('marker')
    .attr('id', 'sv-arrow')
    .attr('viewBox', '-2 -4 10 8')
    .attr('refX', NODE_R + 4).attr('refY', 0)
    .attr('markerWidth', 5).attr('markerHeight', 5)
    .attr('orient', 'auto')
    .append('path').attr('d', 'M-2,-4L6,0L-2,4Z')
    .attr('fill', 'rgba(255,255,255,.25)');

  const clusterLayer = svg.append('g').attr('class', 'sg-cluster-layer');
  const infoLayer    = svg.append('g').attr('class', 'sg-info-layer');
  const edgeLayer    = svg.append('g').attr('class', 'sg-edge-layer');
  const nodeLayer    = svg.append('g').attr('class', 'sg-node-layer');

  const byFile = d3.group(nodes, d => d.file);
  const fileArr = Array.from(byFile.keys());
  const colW = W / Math.max(fileArr.length, 1);
  const fileCols = new Map<string, number>();
  fileArr.forEach((f, i) => fileCols.set(f, i));

  nodes.forEach(n => {
    const col = fileCols.get(n.file) ?? 0;
    n.x = colW * col + colW / 2 + (Math.random() - 0.5) * 40;
    n.y = H / 2 + (Math.random() - 0.5) * 60;
  });

  _simulation = d3.forceSimulation<SymNode>(nodes)
    .force('link', d3.forceLink<SymNode, SymEdge>(edges)
      .id(d => d.id).distance(55).strength(0.6))
    .force('charge', d3.forceManyBody().strength(-160))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide(NODE_R + 18))
    .force('column', () => {
      for (const n of nodes) {
        const col = fileCols.get(n.file) ?? 0;
        const cx = colW * col + colW / 2;
        n.vx = (n.vx ?? 0) + (cx - (n.x ?? 0)) * 0.04;
      }
    });

  const edgeSel = edgeLayer.selectAll<SVGLineElement, SymEdge>('.sg-edge')
    .data(edges).enter()
    .append('line').attr('class', 'sg-edge inactive')
    .attr('stroke', 'rgba(255,255,255,.2)').attr('stroke-width', 1.2)
    .attr('marker-end', 'url(#sv-arrow)');

  const nodeSel = nodeLayer.selectAll<SVGGElement, SymNode>('.sg-node')
    .data(nodes).enter()
    .append('g').attr('class', 'sg-node')
    .call(d3.drag<SVGGElement, SymNode>()
      .on('start', (ev, d) => {
        if (!ev.active && _simulation) _simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on('end', (ev, d) => {
        if (!ev.active && _simulation) _simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      }))
    .on('click', (_ev, d) => selectNode(d));

  // Dead code dashed ring
  nodeSel.filter(d => d.isDeadCode)
    .append('circle').attr('r', NODE_R + 5)
    .attr('fill', 'none').attr('stroke', '#f87171')
    .attr('stroke-width', 1.5).attr('stroke-dasharray', DEAD_DASHES)
    .attr('opacity', .55).attr('class', 'sg-dead-ring');

  // Op-coloured outer ring
  nodeSel.append('circle').attr('class', 'sg-ring').attr('r', NODE_R + 2)
    .attr('fill', 'none')
    .attr('stroke', d => OP_COLOR[d.op] ?? OP_COLOR.unknown)
    .attr('stroke-width', 2).attr('opacity', .75);

  // Kind-fill inner circle
  nodeSel.append('circle').attr('class', 'sg-fill').attr('r', NODE_R - 1)
    .attr('fill', d => KIND_FILL[d.kind] ?? KIND_FILL.unknown)
    .attr('fill-opacity', .85)
    .attr('stroke', 'rgba(0,0,0,.3)').attr('stroke-width', 1);

  // Label below node
  nodeSel.append('text').attr('class', 'sg-lbl')
    .attr('y', NODE_R + 12).attr('text-anchor', 'middle')
    .attr('font-size', 8).attr('font-family', 'var(--font-mono)')
    .attr('fill', 'rgba(255,255,255,.7)').attr('pointer-events', 'none')
    .text(d => d.label);

  // File cluster backgrounds (after simulation settles for accurate bounds)
  _simulation.on('end', () => {
    clusterLayer.selectAll('*').remove();
    infoLayer.selectAll('*').remove();

    byFile.forEach((fileNodes, file) => {
      const xs = fileNodes.map(n => n.x ?? 0);
      const ys = fileNodes.map(n => n.y ?? 0);
      const pad = 22;
      const x1 = Math.min(...xs) - pad, y1 = Math.min(...ys) - pad;
      const x2 = Math.max(...xs) + pad, y2 = Math.max(...ys) + pad;
      clusterLayer.append('rect')
        .attr('x', x1).attr('y', y1)
        .attr('width', x2 - x1).attr('height', y2 - y1)
        .attr('rx', 6).attr('class', 'sg-cluster-bg')
        .attr('fill', 'rgba(255,255,255,.013)')
        .attr('stroke', 'rgba(255,255,255,.06)');
      infoLayer.append('text')
        .attr('x', x1 + 6).attr('y', y1 + 12)
        .attr('font-size', 9).attr('font-family', 'var(--font-mono)')
        .attr('fill', 'rgba(255,255,255,.28)').attr('pointer-events', 'none')
        .text(file);
    });

    // Apply any active filter after layout settles
    applyFilter();
  });

  _simulation.on('tick', () => {
    edgeSel
      .attr('x1', d => (d.source as SymNode).x ?? 0)
      .attr('y1', d => (d.source as SymNode).y ?? 0)
      .attr('x2', d => (d.target as SymNode).x ?? 0)
      .attr('y2', d => (d.target as SymNode).y ?? 0);
    nodeSel.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  // Reset mode buttons to default
  syncModeButtons('default');
  updateStats(nodes.length, fileArr.length);
}

// ── Mode switching ────────────────────────────────────────────────────────────

function syncModeButtons(mode: 'default' | 'dead' | 'impact'): void {
  const map: Record<string, string> = { default: 'sv-mode-graph', dead: 'sv-mode-dead', impact: 'sv-mode-impact' };
  Object.entries(map).forEach(([m, id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle('sv-mode-active', m === mode);
    el.classList.toggle('sv-mode-active-red', m === 'dead' && mode === 'dead');
  });
}

function setMode(mode: 'default' | 'dead' | 'impact'): void {
  _graphMode = mode;
  syncModeButtons(mode);

  const svgEl = document.getElementById(SVG_ID);
  if (!svgEl) return;

  if (mode === 'default') {
    svgEl.removeAttribute('data-mode');
    d3.selectAll('.sg-node').classed('sg-inactive', false);
    d3.selectAll('.sg-edge').classed('inactive', false);
    applyFilter();
  } else if (mode === 'dead') {
    svgEl.setAttribute('data-mode', 'dead');
    d3.selectAll<SVGGElement, SymNode>('.sg-node')
      .classed('sg-inactive', d => !d.isDeadCode);
    d3.selectAll('.sg-edge').classed('inactive', true);
  } else if (mode === 'impact') {
    svgEl.setAttribute('data-mode', 'impact');
    if (_selectedNode) {
      highlightImpact(_selectedNode);
    } else {
      const firstConnected =
        _nodes.find(n => _edges.some(e => (e.source as SymNode).id === n.id)) ??
        _nodes[0];
      if (firstConnected) selectNode(firstConnected);
    }
  }
}

function highlightImpact(node: SymNode): void {
  const impacted = new Set<string>([node.id]);
  for (let depth = 0; depth < 4; depth++) {
    _edges.forEach(e => {
      const t = (e.target as SymNode).id;
      const s = (e.source as SymNode).id;
      if (impacted.has(t)) impacted.add(s);
    });
  }
  d3.selectAll<SVGGElement, SymNode>('.sg-node')
    .classed('sg-inactive', d => !impacted.has(d.id));
  d3.selectAll<SVGLineElement, SymEdge>('.sg-edge')
    .classed('inactive', e => {
      const s = (e.source as SymNode).id;
      const t = (e.target as SymNode).id;
      return !impacted.has(s) && !impacted.has(t);
    });
}

// ── Search / filter ───────────────────────────────────────────────────────────

function applyFilter(): void {
  if (!_filterText && !_filterKind) {
    d3.selectAll<SVGGElement, SymNode>('.sg-node').classed('sg-filtered', false);
    return;
  }
  const text = _filterText.toLowerCase();
  d3.selectAll<SVGGElement, SymNode>('.sg-node').classed('sg-filtered', d => {
    const matchText = !text || d.label.toLowerCase().includes(text) || d.id.toLowerCase().includes(text);
    const matchKind = !_filterKind || d.kind === _filterKind;
    return !(matchText && matchKind);
  });
}

// ── Symbol info panel ─────────────────────────────────────────────────────────

function selectNode(node: SymNode): void {
  _selectedNode = node;

  d3.selectAll<SVGGElement, SymNode>('.sg-node')
    .classed('sg-selected', d => d.id === node.id);

  if (_graphMode === 'impact') highlightImpact(node);

  const panel = document.getElementById('sv-info-panel');
  const nameEl = document.getElementById('sv-info-name');
  const kindEl = document.getElementById('sv-info-kind');
  const dlEl   = document.getElementById('sv-info-dl');

  if (!panel || !nameEl || !kindEl || !dlEl) return;

  const symName = node.id.split('::').pop() ?? node.id;
  const opCol   = OP_COLOR[node.op]   ?? OP_COLOR.unknown;
  const kndCol  = KIND_FILL[node.kind] ?? KIND_FILL.unknown;

  nameEl.textContent = symName;
  kindEl.textContent = node.kind;
  kindEl.style.setProperty('--kind-color', kndCol);

  const callees = _edges
    .filter(e => (e.source as SymNode).id === node.id)
    .map(e => (e.target as SymNode).label);
  const callers = _edges
    .filter(e => (e.target as SymNode).id === node.id)
    .map(e => (e.source as SymNode).label);

  const pill = (text: string, color: string) =>
    `<span class="sv-info-pill" style="border-color:${color}40;color:${color};background:${color}10">${escapeHtml(text)}</span>`;

  let rows = `
    <div class="sv-info-row">
      <dt>op</dt>
      <dd>${pill(OP_LABEL[node.op] ?? node.op, opCol)}</dd>
    </div>
    <div class="sv-info-row">
      <dt>file</dt>
      <dd class="sv-info-mono">${escapeHtml(node.file)}</dd>
    </div>
  `;
  if (node.summary) {
    rows += `<div class="sv-info-row sv-info-summary"><dd>${escapeHtml(node.summary)}</dd></div>`;
  }
  if (node.isDeadCode) {
    rows += `<div class="sv-info-row sv-info-dead"><dd>⚠ dead code — 0 callers</dd></div>`;
  }
  if (callees.length) {
    rows += `<div class="sv-info-row"><dt>calls →</dt><dd class="sv-info-pills">${callees.map(c => pill(c, '#34d399')).join('')}</dd></div>`;
  }
  if (callers.length) {
    rows += `<div class="sv-info-row"><dt>← callers</dt><dd class="sv-info-pills">${callers.map(c => pill(c, '#2dd4bf')).join('')}</dd></div>`;
  }
  if (!callees.length && !callers.length) {
    rows += `<div class="sv-info-row"><dd class="sv-info-no-edges">No call-graph edges in this commit.</dd></div>`;
  }

  dlEl.innerHTML = rows;
  panel.removeAttribute('hidden');
}

// ── Commit navigator ──────────────────────────────────────────────────────────

function renderCommitNav(): void {
  const list = document.getElementById('sv-commit-list');
  if (!list) return;

  if (!_commits.length) {
    list.innerHTML = '<li class="sv-commit-empty">No commits yet.</li>';
    return;
  }

  list.innerHTML = _commits.map((c, i) => {
    const sha = c.id.slice(0, 8);
    const msg = c.message.length > 52 ? c.message.slice(0, 51) + '…' : c.message;
    const ts  = c.ts ? relativeTime(c.ts) : '';
    const active = i === _activeCommitIdx ? ' sv-commit-active' : '';
    return `
      <li class="sv-commit-item${active}" role="option" aria-selected="${i === _activeCommitIdx}"
          data-idx="${i}" tabindex="0">
        <span class="sv-commit-sha">${escapeHtml(sha)}</span>
        <span class="sv-commit-msg">${escapeHtml(msg)}</span>
        <span class="sv-commit-meta">
          <span class="sv-commit-branch">${escapeHtml(c.branch)}</span>
          <span class="sv-commit-ts">${escapeHtml(ts)}</span>
        </span>
      </li>`;
  }).join('');

  list.querySelectorAll<HTMLLIElement>('.sv-commit-item').forEach(li => {
    li.addEventListener('click', () => {
      const idx = parseInt(li.dataset['idx'] ?? '0', 10);
      void activateCommit(idx);
    });
    li.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const idx = parseInt(li.dataset['idx'] ?? '0', 10);
        void activateCommit(idx);
      }
    });
  });
}

async function activateCommit(idx: number): Promise<void> {
  _activeCommitIdx = idx;

  // Update active state visually before fetch
  document.querySelectorAll('.sv-commit-item').forEach((el, i) => {
    el.classList.toggle('sv-commit-active', i === idx);
    el.setAttribute('aria-selected', String(i === idx));
  });

  const commit = _commits[idx];
  if (!commit) return;

  try {
    const res = await fetch(`/api/repos/${encodeURIComponent(_repoId)}/commits/${encodeURIComponent(commit.id)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const wire = await res.json() as WireCommit;
    if (wire.structured_delta?.ops?.length) {
      renderGraph(wire.structured_delta);
      renderAnalyze(wire.structured_delta, wire.message);
    } else {
      clearGraph();
      clearAnalyze(wire.message);
    }
  } catch (err) {
    console.error('[view] failed to load commit delta', err);
    clearGraph();
  }
}

function clearGraph(): void {
  const svgEl = document.getElementById(SVG_ID);
  const emptyEl = document.getElementById('sv-empty');
  if (svgEl) svgEl.style.display = 'none';
  if (emptyEl) emptyEl.removeAttribute('hidden');
  _nodes = [];
  _edges = [];
  updateStats(0, 0);
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function updateStats(symbolCount: number, fileCount: number): void {
  const el = document.getElementById('sv-stats');
  if (!el) return;
  if (symbolCount === 0) {
    el.textContent = '';
    return;
  }
  const fc = fileCount === 1 ? '1 file' : `${fileCount} files`;
  el.textContent = `${symbolCount} symbol${symbolCount !== 1 ? 's' : ''} · ${fc}`;
}

// ── Semantic Changes panel ────────────────────────────────────────────────────

function renderAnalyze(delta: StructuredDelta, commitMsg?: string): void {
  const body = document.getElementById('sv-analyze-body');
  const countEl = document.getElementById('sv-sym-count');
  if (!body) return;

  let totalSyms = 0;
  const parts: string[] = [];

  if (commitMsg) {
    parts.push(`<p class="sv-analyze-msg">${escapeHtml(commitMsg)}</p>`);
  }

  for (const fileOp of delta.ops) {
    if (!fileOp.child_ops?.length) continue;
    const ext = fileOp.address.includes('.')
      ? fileOp.address.split('.').pop() ?? ''
      : '';
    const opLabel = OP_LABEL[fileOp.op] ?? fileOp.op;
    const fileSyms = fileOp.child_ops.length;
    totalSyms += fileSyms;

    const opClass = `sv-op-${fileOp.op === 'insert' ? 'add' : fileOp.op === 'delete' ? 'del' : 'mod'}`;

    parts.push(`
      <div class="sv-file-card">
        <div class="sv-file-hd">
          <span class="sv-op-dot ${opClass}"></span>
          <span class="sv-file-path">${escapeHtml(fileOp.address)}</span>
          ${ext ? `<span class="sv-ext">.${escapeHtml(ext)}</span>` : ''}
          <span class="sv-file-sym-count">${fileSyms} sym${fileSyms !== 1 ? 's' : ''}</span>
        </div>
        <div class="sv-sym-tree">
          ${fileOp.child_ops.map(sym => {
            const addr = sym.address.includes('::') ? sym.address.split('::').slice(1).join('::') : sym.address;
            const isChild = addr.includes('.');
            const displayName = isChild ? addr.split('.').pop() ?? addr : addr;
            const symOpClass = `sv-op-${sym.op === 'insert' ? 'add' : sym.op === 'delete' ? 'del' : 'mod'}`;
            const kind = detectKind(sym.address, sym.content_summary ?? '');
            const kindColor = KIND_FILL[kind] ?? KIND_FILL.unknown;

            return `
              <div class="sv-sym-row ${isChild ? 'sv-sym-child' : 'sv-sym-top'}">
                ${isChild ? '<span class="sv-sym-indent">↳</span>' : ''}
                <span class="sv-op-dot ${symOpClass} sv-op-dot-sm"></span>
                <span class="sv-sym-name">${escapeHtml(displayName)}</span>
                <span class="sv-kind-chip" style="border-color:${kindColor}30;color:${kindColor}">${kind}</span>
              </div>`;
          }).join('')}
        </div>
      </div>`);
  }

  if (!parts.length) {
    body.innerHTML = '<p class="sv-analyze-empty">No semantic changes in this commit.</p>';
    if (countEl) countEl.textContent = '';
    return;
  }

  body.innerHTML = parts.join('');
  if (countEl) countEl.textContent = `${totalSyms} symbol${totalSyms !== 1 ? 's' : ''}`;
}

function clearAnalyze(commitMsg?: string): void {
  const body = document.getElementById('sv-analyze-body');
  const countEl = document.getElementById('sv-sym-count');
  if (!body) return;
  const msg = commitMsg ? `<p class="sv-analyze-msg">${escapeHtml(commitMsg)}</p>` : '';
  body.innerHTML = `${msg}<p class="sv-analyze-empty">No symbol data for this commit.</p>`;
  if (countEl) countEl.textContent = '';
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initView(rawData: Record<string, unknown>): void {
  const data = rawData as PageData;
  if (data.viewerType !== 'code') return;

  _repoId = data.repoId ?? '';
  _commits = (data.commits as SlimCommit[] | undefined) ?? [];
  _activeCommitIdx = 0;

  // ── Commit navigator ──────────────────────────────────────────────────────
  renderCommitNav();

  const prevBtn = document.getElementById('sv-prev');
  const nextBtn = document.getElementById('sv-next');
  prevBtn?.addEventListener('click', () => {
    if (_activeCommitIdx > 0) void activateCommit(_activeCommitIdx - 1);
  });
  nextBtn?.addEventListener('click', () => {
    if (_activeCommitIdx < _commits.length - 1) void activateCommit(_activeCommitIdx + 1);
  });

  // ── Mode buttons ──────────────────────────────────────────────────────────
  document.getElementById('sv-mode-graph')?.addEventListener('click', () => setMode('default'));
  document.getElementById('sv-mode-dead')?.addEventListener('click',  () => setMode('dead'));
  document.getElementById('sv-mode-impact')?.addEventListener('click', () => setMode('impact'));

  // ── Search + filter ───────────────────────────────────────────────────────
  document.getElementById('sv-search')?.addEventListener('input', (e: Event) => {
    _filterText = (e.target as HTMLInputElement).value.trim();
    applyFilter();
  });
  document.getElementById('sv-kind-filter')?.addEventListener('change', (e: Event) => {
    _filterKind = (e.target as HTMLSelectElement).value;
    applyFilter();
  });

  // ── Info panel close ──────────────────────────────────────────────────────
  document.getElementById('sv-info-close')?.addEventListener('click', () => {
    const panel = document.getElementById('sv-info-panel');
    panel?.setAttribute('hidden', '');
    _selectedNode = null;
    d3.selectAll('.sg-node').classed('sg-selected', false);
  });

  // ── Initial render from SSR data (zero round-trips) ───────────────────────
  const delta = data.initialDelta ?? null;
  if (delta?.ops?.length) {
    renderGraph(delta);
    const firstCommitMsg = _commits[0]?.message;
    renderAnalyze(delta, firstCommitMsg);
  } else if (_commits.length) {
    // No SSR delta but we have commits — fetch the first one
    void activateCommit(0);
  }
}
