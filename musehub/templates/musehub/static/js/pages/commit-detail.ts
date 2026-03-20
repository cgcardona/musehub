/**
 * commit-detail.ts — D3 symbol graph for the MuseHub commit detail page.
 *
 * Reads `structuredDelta` from the page-data JSON block and renders:
 *  - A force-directed symbol graph (nodes = symbols, file cluster backgrounds)
 *  - Three modes: Graph (default) | Dead Code | Blast Radius (impact)
 *  - A symbol info panel (click a node to inspect)
 *
 * Data shape (from commit_meta.structured_delta):
 *   { domain, ops: [{ op, address, child_ops: [{ op, address, content_summary }] }] }
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

interface SnapshotDiff {
  added: string[];
  modified: string[];
  removed: string[];
  total_files: number;
}

interface Provenance {
  agent_id?: string;
  model_id?: string;
  is_agent?: boolean;
  sem_ver_bump?: string;
}

interface PageData {
  page: string;
  repoId?: string;
  commitId?: string;
  owner?: string;
  repoSlug?: string;
  baseUrl?: string;
  structuredDelta?: StructuredDelta | null;
  snapshotDiff?: SnapshotDiff | null;
  provenance?: Provenance;
  commitType?: string;
  isBreaking?: boolean;
}

interface SymNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  file: string;
  kind: string;       // class | method | function | variable | unknown
  op: string;         // insert | delete | replace | unknown
  summary: string;
  isDeadCode: boolean;
  fileOp: string;     // op of the parent file
}

interface SymEdge {
  source: string | SymNode;
  target: string | SymNode;
}

interface FileCluster {
  file: string;
  nodes: SymNode[];
}

// ── Constants ──────────────────────────────────────────────────────────────────

const OP_COLOR: Record<string, string> = {
  insert:  '#34d399',   // green
  delete:  '#f87171',   // red
  replace: '#fbbf24',   // amber
  patch:   '#fbbf24',
  unknown: '#94a3b8',
};

const KIND_FILL: Record<string, string> = {
  class:    '#a78bfa',  // purple
  method:   '#2dd4bf',  // teal
  function: '#60a5fa',  // blue
  variable: '#f9a825',  // gold
  unknown:  '#78909c',
};

const NODE_R = 10;
const DEAD_DASHES = '3,3';

// ── State ─────────────────────────────────────────────────────────────────────

let _graphMode: 'default' | 'dead' | 'impact' = 'default';
let _selectedNode: SymNode | null = null;
let _simulation: d3.Simulation<SymNode, SymEdge> | null = null;
let _nodes: SymNode[] = [];
let _edges: SymEdge[] = [];

// ── Helpers ───────────────────────────────────────────────────────────────────

function detectKind(address: string, summary: string): string {
  const s = summary.toLowerCase();
  if (s.includes('class'))    return 'class';
  if (s.includes('method'))   return 'method';
  if (s.includes('function')) return 'function';
  if (s.includes('variable') || s.includes('constant')) return 'variable';
  // Heuristic from address: Class.method => method, _foo => function
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
      // Dead code: "0 callers" in summary, or delete op
      const isDeadCode = co.op === 'delete' ||
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

    // Infer parent → child edges from address hierarchy
    // e.g. Foo::Bar.method → Bar is child of Foo
    for (const nid of fileNodeIds) {
      const sym = nid.split('::').pop() ?? '';
      if (sym.includes('.')) {
        const parentSym = sym.split('.')[0];
        // Find parent node in same file
        const parentId = fileNodeIds.find(id => {
          const s = id.split('::').pop() ?? '';
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

// ── Render ────────────────────────────────────────────────────────────────────

function renderGraph(delta: StructuredDelta): void {
  const svgEl = document.getElementById('cd2-sym-svg') as SVGElement | null;
  if (!svgEl) return;

  const { nodes, edges } = buildGraph(delta);
  if (!nodes.length) {
    svgEl.style.display = 'none';
    const section = document.getElementById('cd2-sym-graph-section');
    if (section) section.style.display = 'none';
    return;
  }
  _nodes = nodes;
  _edges = edges;

  // Size SVG to its container
  const W = svgEl.parentElement?.clientWidth ? Math.min(svgEl.parentElement.clientWidth - 240, 760) : 600;
  const H = Math.max(300, Math.min(nodes.length * 28, 420));

  const svg = d3.select<SVGElement, unknown>('#cd2-sym-svg')
    .attr('viewBox', `0 0 ${W} ${H}`)
    .attr('width', W).attr('height', H);

  svg.selectAll('*').remove();

  // ── Defs: arrowhead marker ─────────────────────────────────────────────────
  svg.append('defs').append('marker')
    .attr('id', 'sg-arrow').attr('viewBox', '-2 -4 10 8')
    .attr('refX', NODE_R + 4).attr('refY', 0)
    .attr('markerWidth', 5).attr('markerHeight', 5).attr('orient', 'auto')
    .append('path').attr('d', 'M-2,-4L6,0L-2,4Z')
    .attr('fill', 'rgba(255,255,255,.25)');

  // ── File cluster backgrounds ───────────────────────────────────────────────
  const clusterLayer = svg.append('g').attr('class', 'sg-cluster-layer');
  const infoLayer    = svg.append('g').attr('class', 'sg-info-layer');
  const edgeLayer    = svg.append('g').attr('class', 'sg-edge-layer');
  const nodeLayer    = svg.append('g').attr('class', 'sg-node-layer');

  // Group by file
  const byFile = d3.group(nodes, d => d.file);
  const fileArr = Array.from(byFile.keys());

  // Partition canvas into columns per file
  const colW = W / fileArr.length;
  const fileCols = new Map<string, number>();
  fileArr.forEach((f, i) => fileCols.set(f, i));

  // Initial positions: spread by file column
  nodes.forEach(n => {
    const col = fileCols.get(n.file) ?? 0;
    n.x = colW * col + colW / 2 + (Math.random() - 0.5) * 40;
    n.y = H / 2 + (Math.random() - 0.5) * 60;
  });

  // ── Simulation ─────────────────────────────────────────────────────────────
  _simulation = d3.forceSimulation<SymNode>(nodes)
    .force('link', d3.forceLink<SymNode, SymEdge>(edges)
      .id(d => d.id).distance(55).strength(0.6))
    .force('charge', d3.forceManyBody().strength(-160))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide(NODE_R + 18))
    .force('column', () => {
      // Gently pull each node toward its file's column centre
      for (const n of nodes) {
        const col = fileCols.get(n.file) ?? 0;
        const cx = colW * col + colW / 2;
        n.vx = (n.vx ?? 0) + (cx - (n.x ?? 0)) * 0.04;
      }
    });

  // ── Edges ──────────────────────────────────────────────────────────────────
  const edgeSel = edgeLayer.selectAll<SVGLineElement, SymEdge>('.sg-edge')
    .data(edges).enter()
    .append('line').attr('class', 'sg-edge inactive')
    .attr('stroke', 'rgba(255,255,255,.2)').attr('stroke-width', 1.2)
    .attr('marker-end', 'url(#sg-arrow)');

  // ── Nodes ──────────────────────────────────────────────────────────────────
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

  // ── File cluster boxes (drawn after layout settles) ────────────────────────
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
  });

  // ── Tick ───────────────────────────────────────────────────────────────────
  _simulation.on('tick', () => {
    edgeSel
      .attr('x1', d => (d.source as SymNode).x ?? 0)
      .attr('y1', d => (d.source as SymNode).y ?? 0)
      .attr('x2', d => (d.target as SymNode).x ?? 0)
      .attr('y2', d => (d.target as SymNode).y ?? 0);

    nodeSel.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });
}

// ── Mode switching ────────────────────────────────────────────────────────────

function setMode(mode: 'default' | 'dead' | 'impact'): void {
  _graphMode = mode;

  // Update button states
  ['graph', 'dead', 'impact'].forEach(m => {
    const el = document.getElementById(`sgm-${m}`);
    if (!el) return;
    const isActive = (m === 'graph' && mode === 'default') ||
                     (m === 'dead'   && mode === 'dead')    ||
                     (m === 'impact' && mode === 'impact');
    el.className = 'cd2-mode-btn' + (isActive ? (mode === 'dead' ? ' active-red' : ' active') : '');
  });

  const svgEl = document.getElementById('cd2-sym-svg');
  if (!svgEl) return;

  if (mode === 'default') {
    svgEl.removeAttribute('data-mode');
    d3.selectAll('.sg-node').classed('sg-inactive', false);
    d3.selectAll('.sg-edge').classed('inactive', false);
  } else if (mode === 'dead') {
    svgEl.setAttribute('data-mode', 'dead');
    d3.selectAll<SVGGElement, SymNode>('.sg-node')
      .classed('sg-inactive', d => !d.isDeadCode);
    d3.selectAll('.sg-edge').classed('inactive', true);
  } else if (mode === 'impact') {
    svgEl.setAttribute('data-mode', 'impact');
    if (_selectedNode) highlightImpact(_selectedNode);
    else {
      // Auto-pick first node with outgoing edges
      const firstConnected = _nodes.find(n =>
        _edges.some(e => (e.source as SymNode).id === n.id)
      ) ?? _nodes[0];
      if (firstConnected) selectNode(firstConnected);
    }
  }
}

function highlightImpact(node: SymNode): void {
  // Transitive callers: walk edges backward from `node`
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
      const s = (e.source as SymNode).id, t = (e.target as SymNode).id;
      return !impacted.has(s) && !impacted.has(t);
    });
}

// ── Symbol info panel ─────────────────────────────────────────────────────────

function selectNode(node: SymNode): void {
  _selectedNode = node;

  // Highlight selected ring
  d3.selectAll<SVGGElement, SymNode>('.sg-node')
    .classed('sg-selected', d => d.id === node.id);

  if (_graphMode === 'impact') highlightImpact(node);

  const panel = document.getElementById('cd2-sym-info');
  if (!panel) return;

  const opCol  = OP_COLOR[node.op]  ?? OP_COLOR.unknown;
  const kndCol = KIND_FILL[node.kind] ?? KIND_FILL.unknown;

  const callees = _edges
    .filter(e => (e.source as SymNode).id === node.id)
    .map(e => (e.target as SymNode).label);
  const callers = _edges
    .filter(e => (e.target as SymNode).id === node.id)
    .map(e => (e.source as SymNode).label);

  const pill = (label: string, col: string, text: string) =>
    `<span style="font-family:var(--font-mono);font-size:10px;padding:1px 6px;border-radius:3px;border:1px solid ${col}40;color:${col};background:${col}10">${text}</span>`;

  panel.innerHTML = `
    <div style="font-family:var(--font-mono);font-size:12px;color:var(--color-accent);margin-bottom:6px">${node.id.split('::').pop()}</div>
    <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px">
      ${pill('op',  opCol,  node.op)}
      ${pill('knd', kndCol, node.kind)}
    </div>
    <div style="font-size:10px;color:var(--text-muted);margin-bottom:2px">file</div>
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);margin-bottom:6px">${node.file}</div>
    ${node.summary ? `<div style="font-size:11px;color:var(--text-muted);line-height:1.4;margin-bottom:6px">${node.summary}</div>` : ''}
    ${node.isDeadCode ? `<div style="color:#f87171;font-size:10px;margin-bottom:6px">⚠ dead code — 0 callers</div>` : ''}
    ${callees.length ? `
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);margin-bottom:3px">calls →</div>
      <div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:4px">${callees.map(c =>
        `<span style="font-family:var(--font-mono);font-size:9px;color:var(--color-success);padding:1px 5px;border-radius:3px;background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.2)">${c}</span>`
      ).join('')}</div>` : ''}
    ${callers.length ? `
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);margin-bottom:3px">← callers</div>
      <div style="display:flex;flex-wrap:wrap;gap:2px">${callers.map(c =>
        `<span style="font-family:var(--font-mono);font-size:9px;color:#2dd4bf;padding:1px 5px;border-radius:3px;background:rgba(45,212,191,.08);border:1px solid rgba(45,212,191,.2)">${c}</span>`
      ).join('')}</div>` : ''}
    ${!callees.length && !callers.length ? `<div style="font-size:10px;color:var(--text-muted)">No call-graph edges in this commit.</div>` : ''}
  `;
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initCommitDetail(): void {
  // Expose mode setter for onclick attributes in template
  (window as Window & { __sgSetMode?: (m: string) => void }).__sgSetMode = (m: string) => {
    if (m === 'default' || m === 'dead' || m === 'impact') setMode(m);
  };

  const dataEl = document.getElementById('page-data');
  if (!dataEl) return;

  let data: PageData;
  try {
    data = JSON.parse(dataEl.textContent ?? '{}') as PageData;
  } catch {
    return;
  }

  if (data.structuredDelta?.ops?.length) {
    renderGraph(data.structuredDelta);
  }
}
