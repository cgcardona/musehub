/**
 * insights.ts — Semantic Observatory for the Muse code-domain Insights page.
 *
 * Five D3 v7 visualisations that expose what Muse tracks that Git cannot:
 *   1. SemVer Timeline + Symbol Velocity — commit history coloured by bump level,
 *      with per-commit bar sub-chart showing +/- symbol counts.
 *   2. Language Treemap — d3.treemap sized by byte count.
 *   3. Commit DNA Arc — concentric d3.pie: outer = commit type, inner = semver.
 *   4. Breaking Change Blast Radius — d3.forceSimulation radiating breaking commits.
 *
 * All data is SSR'd into page_json and passed in as `data`; no extra round-trips
 * on first paint. The symbol-graph viewer (view.ts) is booted from here too when
 * the domain is "code", because insights.html embeds the sv-layout DOM.
 */

import * as d3 from 'd3';
import { initView } from './view.ts';

// ── Types ──────────────────────────────────────────────────────────────────────

interface CommitEntry {
  date: string;
  sym_added: number;
  sym_removed: number;
  bump: string;
  is_breaking: boolean;
  breaking_addr_count: number;
  msg: string;
}

interface LanguageEntry {
  name: string;
  count: number;
  bytes: number;
  pct: number;
  pct_bytes: number;
  color: string;
}

interface TypeBar {
  name: string;
  count: number;
  pct: number;
}

interface SemverCounts {
  major: number;
  minor: number;
  patch: number;
  none: number;
}

interface InsightsData extends Record<string, unknown> {
  viewerType?: string;
  timeline?: CommitEntry[];
  symCumulative?: number[];
  languages?: LanguageEntry[];
  typeBars?: TypeBar[];
  semverCounts?: SemverCounts;
  breakingCount?: number;
}

// ── Colour palette ─────────────────────────────────────────────────────────────

const BUMP_HEX: Record<string, string> = {
  major: '#f85149',
  minor: '#e3b341',
  patch: '#3fb950',
  none: '#484f58',
};

const TYPE_HEX: Record<string, string> = {
  feat:    '#3fb950',
  fix:     '#f85149',
  refactor:'#58a6ff',
  docs:    '#e3b341',
  test:    '#a371f7',
  chore:   '#8b949e',
  perf:    '#79c0ff',
  ci:      '#bc8cff',
  build:   '#ffa657',
  style:   '#ff7b72',
  other:   '#484f58',
};

const SEMVER_HEX: Record<string, string> = {
  major: '#f85149',
  minor: '#e3b341',
  patch: '#3fb950',
  none:  '#484f58',
};

// ── Shared tooltip ─────────────────────────────────────────────────────────────

let _sharedTip: HTMLDivElement | null = null;

function getTip(): HTMLDivElement {
  if (!_sharedTip) {
    _sharedTip = document.createElement('div');
    _sharedTip.className = 'ins-d3-tip';
    document.body.appendChild(_sharedTip);
  }
  return _sharedTip;
}

function showTip(e: MouseEvent, html: string): void {
  const t = getTip();
  t.innerHTML = html;
  t.style.opacity = '1';
  moveTip(e);
}

function moveTip(e: MouseEvent): void {
  const t = getTip();
  t.style.left = `${e.clientX + 14}px`;
  t.style.top  = `${e.clientY - 36}px`;
}

function hideTip(): void {
  const t = getTip();
  t.style.opacity = '0';
}

// ── Panel label helpers ────────────────────────────────────────────────────────

function panelLabel(container: Element, text: string): void {
  const el = container.querySelector<HTMLElement>('.ins-d3-label');
  if (el && !el.textContent?.trim()) el.textContent = text;
}

// ── Chart 1+2: SemVer Timeline ─────────────────────────────────────────────────
// Combo chart:
//   Top panel  — cumulative symbol growth area, dots coloured by SemVer bump
//   Bottom panel — per-commit velocity bars (+added green / -removed red)

function drawSemVerTimeline(timeline: CommitEntry[], cumulative: number[]): void {
  const wrap = document.getElementById('ins-timeline-svg-wrap');
  if (!wrap || !timeline.length) return;

  const W  = wrap.clientWidth  || 700;
  const H1 = 160;   // growth area height
  const H2 = 60;    // velocity bars height
  const GAP = 8;
  const H  = H1 + GAP + H2;
  const ML = 42, MR = 16, MT = 14, MB = 24;
  const innerW = W - ML - MR;

  const parseDate = d3.timeParse('%Y-%m-%d');
  const points = timeline.map((d, i) => ({
    ...d,
    date: parseDate(d.date) ?? new Date(),
    cum: cumulative[i] ?? 0,
    i,
  }));

  const xScale = d3.scaleTime()
    .domain(d3.extent(points, d => d.date) as [Date, Date])
    .range([0, innerW]);

  const yExt = d3.extent(points, d => d.cum) as [number, number];
  const yPad = Math.abs(yExt[1] - yExt[0]) * 0.15 || 20;
  const yScale = d3.scaleLinear()
    .domain([Math.min(0, yExt[0] - yPad), yExt[1] + yPad])
    .range([H1 - MT - MB, 0])
    .nice();

  const maxBar = Math.max(1, ...points.map(d => Math.max(d.sym_added, d.sym_removed)));
  const yBar   = d3.scaleLinear().domain([0, maxBar]).range([H2, 0]);

  const svg = d3.select(wrap)
    .append('svg')
    .attr('width', W).attr('height', H + MT + MB)
    .attr('viewBox', `0 0 ${W} ${H + MT + MB}`)
    .style('overflow', 'visible');

  // ── Top panel (growth area) ──────────────────────────────────────────────────
  const gTop = svg.append('g').attr('transform', `translate(${ML},${MT})`);
  const innerH1 = H1 - MT - MB;

  // Bump-coloured background bands
  for (let i = 0; i < points.length - 1; i++) {
    const x0 = xScale(points[i].date);
    const x1 = xScale(points[i + 1].date);
    gTop.append('rect')
      .attr('x', x0).attr('y', 0)
      .attr('width', Math.max(0, x1 - x0)).attr('height', innerH1)
      .attr('fill', BUMP_HEX[points[i].bump] ?? '#484f58')
      .attr('opacity', 0.055);
  }

  // Area + line
  const areaFn = d3.area<typeof points[0]>()
    .x(d => xScale(d.date))
    .y0(innerH1)
    .y1(d => yScale(d.cum))
    .curve(d3.curveMonotoneX);

  const lineFn = d3.line<typeof points[0]>()
    .x(d => xScale(d.date))
    .y(d => yScale(d.cum))
    .curve(d3.curveMonotoneX);

  const defs = svg.append('defs');
  const gradId = 'ins-tl-grad';
  const grad = defs.append('linearGradient')
    .attr('id', gradId).attr('x1', '0').attr('x2', '0').attr('y1', '0').attr('y2', '1');
  grad.append('stop').attr('offset', '0%').attr('stop-color', 'var(--color-accent)').attr('stop-opacity', 0.35);
  grad.append('stop').attr('offset', '100%').attr('stop-color', 'var(--color-accent)').attr('stop-opacity', 0.02);

  gTop.append('path').datum(points)
    .attr('fill', `url(#${gradId})`)
    .attr('d', areaFn);

  gTop.append('path').datum(points)
    .attr('fill', 'none')
    .attr('stroke', 'var(--color-accent)')
    .attr('stroke-width', 1.5)
    .attr('d', lineFn);

  // Breaking-change vertical markers
  points.filter(d => d.is_breaking).forEach(d => {
    gTop.append('line')
      .attr('x1', xScale(d.date)).attr('x2', xScale(d.date))
      .attr('y1', 0).attr('y2', innerH1)
      .attr('stroke', BUMP_HEX.major)
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '3,3')
      .attr('opacity', 0.55);
  });

  // Commit dots
  gTop.selectAll<SVGCircleElement, typeof points[0]>('circle')
    .data(points)
    .join('circle')
    .attr('cx', d => xScale(d.date))
    .attr('cy', d => yScale(d.cum))
    .attr('r',  d => Math.max(2.5, Math.min(7, Math.sqrt((d.sym_added + d.sym_removed) * 3))))
    .attr('fill',   d => BUMP_HEX[d.bump] ?? '#484f58')
    .attr('stroke', 'var(--bg-base)')
    .attr('stroke-width', 1)
    .attr('opacity', 0.9)
    .style('cursor', 'pointer')
    .on('mouseenter', (e: MouseEvent, d) => {
      showTip(e, [
        `<strong>${d.msg || '(no message)'}</strong>`,
        `${(d.date as unknown as Date).toLocaleDateString()} &nbsp;·&nbsp; <span style="color:${BUMP_HEX[d.bump]}">${d.bump}</span>`,
        `+${d.sym_added} / −${d.sym_removed} symbols`,
        d.is_breaking ? `<span style="color:${BUMP_HEX.major}">⚠ breaking change</span>` : '',
      ].filter(Boolean).join('<br>'));
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', () => hideTip());

  // Y axis (growth)
  gTop.append('g')
    .call(d3.axisLeft(yScale).ticks(4).tickSize(-innerW))
    .call(ax => ax.select('.domain').remove())
    .call(ax => ax.selectAll('.tick line')
      .attr('stroke', 'var(--border-subtle)').attr('opacity', 0.5))
    .call(ax => ax.selectAll('.tick text')
      .attr('fill', 'var(--text-muted)').attr('font-size', 10));

  gTop.append('text')
    .attr('x', -4).attr('y', -4)
    .attr('text-anchor', 'end')
    .attr('font-size', 9)
    .attr('fill', 'var(--text-muted)')
    .text('symbols');

  // ── Bottom panel (velocity bars) ───────────────────────────────────────────
  const gBot = svg.append('g')
    .attr('transform', `translate(${ML},${MT + H1 + GAP})`);

  const bw = Math.max(1, (innerW / points.length) * 0.4);

  // Added bars (green)
  gBot.selectAll<SVGRectElement, typeof points[0]>('.bar-add')
    .data(points)
    .join('rect')
    .attr('class', 'bar-add')
    .attr('x', d => xScale(d.date) - bw)
    .attr('y', d => yBar(d.sym_added))
    .attr('width', bw)
    .attr('height', d => H2 - yBar(d.sym_added))
    .attr('fill', '#3fb950')
    .attr('opacity', 0.75)
    .on('mouseenter', (e: MouseEvent, d) => {
      showTip(e, `+${d.sym_added} symbols added<br><span style="opacity:.7">${d.msg}</span>`);
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', () => hideTip());

  // Removed bars (red)
  gBot.selectAll<SVGRectElement, typeof points[0]>('.bar-del')
    .data(points)
    .join('rect')
    .attr('class', 'bar-del')
    .attr('x', d => xScale(d.date))
    .attr('y', d => yBar(d.sym_removed))
    .attr('width', bw)
    .attr('height', d => H2 - yBar(d.sym_removed))
    .attr('fill', '#f85149')
    .attr('opacity', 0.75)
    .on('mouseenter', (e: MouseEvent, d) => {
      showTip(e, `−${d.sym_removed} symbols removed<br><span style="opacity:.7">${d.msg}</span>`);
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', () => hideTip());

  // Shared X axis (on bottom panel)
  gBot.append('g')
    .attr('transform', `translate(0,${H2})`)
    .call(d3.axisBottom(xScale).ticks(Math.min(8, points.length)).tickSize(0))
    .call(ax => ax.select('.domain').attr('stroke', 'var(--border-subtle)'))
    .call(ax => ax.selectAll('.tick text')
      .attr('fill', 'var(--text-muted)').attr('font-size', 10));

  // Legend
  const legendY = MT + H1 + GAP + H2 + 18;
  const lg = svg.append('g').attr('transform', `translate(${ML},${legendY})`);

  const bumpKeys = ['major', 'minor', 'patch', 'none'] as const;
  bumpKeys.forEach((k, i) => {
    const x = i * 72;
    lg.append('circle').attr('cx', x + 5).attr('cy', 5).attr('r', 4).attr('fill', BUMP_HEX[k]);
    lg.append('text').attr('x', x + 13).attr('y', 9)
      .attr('font-size', 10).attr('fill', 'var(--text-muted)').text(k);
  });
  lg.append('rect').attr('x', 310).attr('y', 1).attr('width', 8).attr('height', 8).attr('fill', '#3fb950').attr('opacity', 0.75);
  lg.append('text').attr('x', 322).attr('y', 9).attr('font-size', 10).attr('fill', 'var(--text-muted)').text('added');
  lg.append('rect').attr('x', 370).attr('y', 1).attr('width', 8).attr('height', 8).attr('fill', '#f85149').attr('opacity', 0.75);
  lg.append('text').attr('x', 382).attr('y', 9).attr('font-size', 10).attr('fill', 'var(--text-muted)').text('removed');
}

// ── Chart 3: Language Treemap ──────────────────────────────────────────────────

function drawLanguageTreemap(languages: LanguageEntry[]): void {
  const wrap = document.getElementById('ins-treemap-svg-wrap');
  if (!wrap || !languages.length) return;

  const W = wrap.clientWidth  || 320;
  const H = 260;

  const root = d3.hierarchy({ name: 'root', children: languages })
    .sum(d => ('bytes' in d ? (d as LanguageEntry).bytes : 0))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  d3.treemap<{ name: string; children?: LanguageEntry[] } | LanguageEntry>()
    .size([W, H])
    .paddingInner(2)
    .paddingOuter(1)
    (root);

  const svg = d3.select(wrap)
    .append('svg')
    .attr('width', W).attr('height', H)
    .attr('viewBox', `0 0 ${W} ${H}`)
    .style('border-radius', '6px')
    .style('overflow', 'hidden');

  const leaves = root.leaves() as d3.HierarchyRectangularNode<LanguageEntry>[];

  const cell = svg.selectAll('g')
    .data(leaves)
    .join('g')
    .attr('transform', d => `translate(${d.x0},${d.y0})`);

  cell.append('rect')
    .attr('width',  d => Math.max(0, d.x1 - d.x0))
    .attr('height', d => Math.max(0, d.y1 - d.y0))
    .attr('fill',   d => d.data.color || '#484f58')
    .attr('opacity', 0.82)
    .attr('rx', 3)
    .style('cursor', 'default')
    .style('transition', 'opacity 0.15s')
    .on('mouseenter', function(e: MouseEvent, d) {
      d3.select(this).attr('opacity', 1);
      showTip(e, [
        `<strong>${d.data.name}</strong>`,
        `${d.data.count} files &nbsp;(${d.data.pct}%)`,
        `${Math.round((d.data.bytes ?? 0) / 1024)} KB &nbsp;(${d.data.pct_bytes}%)`,
      ].join('<br>'));
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', function() {
      d3.select(this).attr('opacity', 0.82);
      hideTip();
    });

  cell.append('text')
    .attr('x', 5).attr('y', 14)
    .attr('font-size', d => Math.min(13, Math.max(8, (d.x1 - d.x0) / 5)))
    .attr('font-weight', 600)
    .attr('fill', '#fff')
    .attr('opacity', 0.92)
    .style('pointer-events', 'none')
    .text(d => {
      const w = d.x1 - d.x0;
      const name = d.data.name;
      return w > 30 ? name : '';
    });

  cell.append('text')
    .attr('x', 5).attr('y', 26)
    .attr('font-size', 9)
    .attr('fill', '#fff')
    .attr('opacity', 0.7)
    .style('pointer-events', 'none')
    .text(d => {
      const w = d.x1 - d.x0;
      const h = d.y1 - d.y0;
      return (w > 42 && h > 24) ? `${d.data.pct}%` : '';
    });

  // Entrance animation: scale from 0 with stagger
  cell.selectAll('rect')
    .style('transform-origin', 'center')
    .style('transform', 'scale(0.6)')
    .style('opacity', '0')
    .transition()
    .delay((_d, i) => i * 18)
    .duration(350)
    .ease(d3.easeCubicOut)
    .style('transform', 'scale(1)')
    .style('opacity', '0.82');
}

// ── Chart 4: Commit DNA Arc ────────────────────────────────────────────────────
// Two concentric d3.pie rings: outer = commit type, inner = semver distribution.

function drawCommitDNAArc(typeBars: TypeBar[], semver: SemverCounts, totalCommits: number): void {
  const wrap = document.getElementById('ins-arc-svg-wrap');
  if (!wrap || !typeBars.length) return;

  const size = Math.min(wrap.clientWidth || 280, 280);
  const cx   = size / 2;
  const cy   = size / 2;
  const outerR = size * 0.44;
  const midR   = size * 0.30;
  const innerR = size * 0.18;

  const svg = d3.select(wrap)
    .append('svg')
    .attr('width', size).attr('height', size)
    .attr('viewBox', `0 0 ${size} ${size}`);

  const arcOuter = d3.arc<d3.PieArcDatum<TypeBar>>()
    .innerRadius(midR).outerRadius(outerR).padAngle(0.025).cornerRadius(3);

  const arcOuterHover = d3.arc<d3.PieArcDatum<TypeBar>>()
    .innerRadius(midR).outerRadius(outerR + 6).padAngle(0.025).cornerRadius(3);

  const pieOuter = d3.pie<TypeBar>().value(d => d.count).sort(null);

  const gOuter = svg.append('g').attr('transform', `translate(${cx},${cy})`);
  const outerSlices = gOuter.selectAll<SVGPathElement, d3.PieArcDatum<TypeBar>>('path')
    .data(pieOuter(typeBars))
    .join('path')
    .attr('fill', d => TYPE_HEX[d.data.name] ?? '#484f58')
    .attr('opacity', 0.85)
    .style('cursor', 'pointer')
    .on('mouseenter', function(e: MouseEvent, d) {
      d3.select(this)
        .transition().duration(150)
        .attr('d', arcOuterHover(d) ?? '');
      showTip(e, [
        `<strong>${d.data.name}</strong>`,
        `${d.data.count} commits &nbsp;(${d.data.pct}%)`,
      ].join('<br>'));
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', function(_, d) {
      d3.select(this)
        .transition().duration(150)
        .attr('d', arcOuter(d) ?? '');
      hideTip();
    });

  // Entrance animation: grow from innerRadius
  outerSlices
    .attr('d', arcOuter)
    .style('transform-origin', 'center')
    .style('transform', 'scale(0)')
    .transition().delay((_d, i) => i * 40).duration(500).ease(d3.easeCubicOut)
    .style('transform', 'scale(1)');

  // Inner ring: semver
  type SemKV = { key: string; value: number };
  const semverData: SemKV[] = [
    { key: 'major', value: semver.major },
    { key: 'minor', value: semver.minor },
    { key: 'patch', value: semver.patch },
    { key: 'none',  value: semver.none  },
  ].filter(d => d.value > 0);

  const arcInner = d3.arc<d3.PieArcDatum<SemKV>>()
    .innerRadius(innerR).outerRadius(midR - 2).padAngle(0.03).cornerRadius(3);

  const pieInner = d3.pie<SemKV>().value(d => d.value).sort(null);

  const gInner = svg.append('g').attr('transform', `translate(${cx},${cy})`);
  gInner.selectAll<SVGPathElement, d3.PieArcDatum<SemKV>>('path')
    .data(pieInner(semverData))
    .join('path')
    .attr('d', arcInner)
    .attr('fill', d => SEMVER_HEX[d.data.key] ?? '#484f58')
    .attr('opacity', 0.7)
    .on('mouseenter', (e: MouseEvent, d) => {
      showTip(e, `<strong>${d.data.key} bump</strong><br>${d.data.value} commits`);
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', () => hideTip());

  // Center label
  const gCenter = svg.append('g').attr('transform', `translate(${cx},${cy})`);
  gCenter.append('text')
    .attr('text-anchor', 'middle').attr('dy', '0.15em')
    .attr('font-size', Math.floor(size * 0.1)).attr('font-weight', 700)
    .attr('font-family', 'var(--font-mono)').attr('fill', 'var(--text-primary)')
    .text(totalCommits);
  gCenter.append('text')
    .attr('text-anchor', 'middle').attr('dy', '1.5em')
    .attr('font-size', 9).attr('fill', 'var(--text-muted)')
    .attr('font-family', 'var(--font-sans)')
    .text('commits');

  // Ring labels (outer): only for large slices
  gOuter.selectAll<SVGTextElement, d3.PieArcDatum<TypeBar>>('.arc-label')
    .data(pieOuter(typeBars))
    .join('text')
    .attr('class', 'arc-label')
    .attr('transform', d => `translate(${arcOuter.centroid(d)})`)
    .attr('text-anchor', 'middle')
    .attr('font-size', 9)
    .attr('fill', '#fff')
    .attr('font-weight', 600)
    .style('pointer-events', 'none')
    .text(d => (d.endAngle - d.startAngle) > 0.4 ? d.data.name : '');
}

// ── Chart 5: Breaking Change Blast Radius ──────────────────────────────────────
// d3.forceSimulation: central "repo" node + one node per breaking commit,
// sized by symbol count, draggable, with glow filter.

interface BlastNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  r: number;
  isCenter: boolean;
  entry?: CommitEntry;
}

function drawBreakingBlast(timeline: CommitEntry[]): void {
  const wrap = document.getElementById('ins-blast-svg-wrap');
  if (!wrap) return;

  const breaking = timeline.filter(d => d.is_breaking);
  if (!breaking.length) return;

  const W  = wrap.clientWidth || 700;
  const H  = 220;
  const cx = W / 2;
  const cy = H / 2;

  const svg = d3.select(wrap)
    .append('svg')
    .attr('width', W).attr('height', H)
    .attr('viewBox', `0 0 ${W} ${H}`)
    .style('overflow', 'visible');

  // Glow filter
  const defs = svg.append('defs');
  const filt = defs.append('filter').attr('id', 'ins-blast-glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
  filt.append('feGaussianBlur').attr('in', 'SourceGraphic').attr('stdDeviation', 4).attr('result', 'blur');
  filt.append('feMerge').selectAll('feMergeNode')
    .data(['blur', 'SourceGraphic'])
    .join('feMergeNode')
    .attr('in', d => d);

  // Build nodes
  const maxAddr = Math.max(1, ...breaking.map(d => d.breaking_addr_count || 1));
  const nodes: BlastNode[] = [
    { id: 'repo', label: 'repo', r: 18, isCenter: true },
    ...breaking.map((e, i) => ({
      id: `b${i}`,
      label: e.msg.slice(0, 28),
      r: 6 + (e.breaking_addr_count ?? 1) / maxAddr * 14,
      isCenter: false,
      entry: e,
    })),
  ];

  const links = breaking.map((_e, i) => ({
    source: 'repo',
    target: `b${i}`,
  }));

  const sim = d3.forceSimulation<BlastNode>(nodes)
    .force('link', d3.forceLink(links).id((d: d3.SimulationNodeDatum) => (d as BlastNode).id).distance(90).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(cx, cy))
    .force('collision', d3.forceCollide<BlastNode>().radius(d => d.r + 6));

  const g = svg.append('g');

  const link = g.selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#f85149')
    .attr('stroke-width', 1)
    .attr('stroke-opacity', 0.3)
    .attr('stroke-dasharray', '4,3');

  const node = g.selectAll<SVGGElement, BlastNode>('.blast-node')
    .data(nodes)
    .join('g')
    .attr('class', 'blast-node')
    .style('cursor', d => d.isCenter ? 'default' : 'grab')
    .call(
      d3.drag<SVGGElement, BlastNode>()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
    );

  // Center circle
  node.filter(d => d.isCenter)
    .append('circle')
    .attr('r', d => d.r)
    .attr('fill', 'var(--color-accent)')
    .attr('opacity', 0.9);

  node.filter(d => d.isCenter)
    .append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '0.35em')
    .attr('font-size', 7)
    .attr('fill', '#fff')
    .attr('font-weight', 700)
    .style('pointer-events', 'none')
    .text('repo');

  // Breaking commit circles
  node.filter(d => !d.isCenter)
    .append('circle')
    .attr('r', d => d.r)
    .attr('fill', '#f85149')
    .attr('opacity', 0.8)
    .attr('filter', 'url(#ins-blast-glow)')
    .on('mouseenter', (e: MouseEvent, d) => {
      if (!d.entry) return;
      showTip(e, [
        `<strong>${d.entry.msg || '(no message)'}</strong>`,
        d.entry.date,
        d.entry.breaking_addr_count
          ? `${d.entry.breaking_addr_count} symbol${d.entry.breaking_addr_count !== 1 ? 's' : ''} broken`
          : 'breaking change',
      ].join('<br>'));
    })
    .on('mousemove', (e: MouseEvent) => moveTip(e))
    .on('mouseleave', () => hideTip());

  node.filter(d => !d.isCenter)
    .append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '-' + ((d: BlastNode) => d.r + 4))
    .attr('dy', (d) => -(d.r + 5))
    .attr('font-size', 9)
    .attr('fill', 'var(--text-muted)')
    .style('pointer-events', 'none')
    .text(d => d.label);

  sim.on('tick', () => {
    link
      .attr('x1', d => (d.source as BlastNode).x ?? 0)
      .attr('y1', d => (d.source as BlastNode).y ?? 0)
      .attr('x2', d => (d.target as BlastNode).x ?? 0)
      .attr('y2', d => (d.target as BlastNode).y ?? 0);

    node.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });
}

// ── Bar entrance animations (legacy SSR bars) ─────────────────────────────────

function animateBars(): void {
  const bars = Array.from(document.querySelectorAll<HTMLElement>('.js-bar-fill'));
  if (!bars.length) return;

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el  = entry.target as HTMLElement;
      const pct = el.style.getPropertyValue('--bar-pct') || '0%';
      el.style.width = '0%';
      requestAnimationFrame(() => {
        el.style.transition = 'width 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        el.style.width = pct;
      });
      io.unobserve(el);
    });
  }, { threshold: 0.1 });

  bars.forEach(b => io.observe(b));
}

function animateCountUp(): void {
  const vals = Array.from(document.querySelectorAll<HTMLElement>('.ins-stat-value'));
  if (!vals.length) return;

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el   = entry.target as HTMLElement;
      const raw  = el.textContent ?? '';
      const num  = parseInt(raw.replace(/[^\d]/g, ''), 10);
      const suffix = raw.replace(/[\d,]/g, '').trim();
      if (isNaN(num) || num === 0) return;

      const duration = Math.min(1200, Math.max(400, num * 2));
      const start    = performance.now();
      const tick = (now: number) => {
        const t    = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);
        const cur  = Math.round(ease * num);
        el.textContent = cur.toLocaleString() + (suffix ? ' ' + suffix : '');
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      io.unobserve(el);
    });
  }, { threshold: 0.5 });

  vals.forEach(v => io.observe(v));
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initInsights(data: Record<string, unknown>): void {
  const d = data as InsightsData;

  // Boot the symbol-dependency graph that lives at the top of this page.
  // initView guards itself with `if (data.viewerType !== 'code') return`.
  initView(data);

  const timeline   = (d.timeline     ?? []) as CommitEntry[];
  const cumulative = (d.symCumulative ?? []) as number[];
  const languages  = (d.languages    ?? []) as LanguageEntry[];
  const typeBars   = (d.typeBars     ?? []) as TypeBar[];
  const semver     = (d.semverCounts ?? { major: 0, minor: 0, patch: 0, none: 0 }) as SemverCounts;
  const totalCommits = typeBars.reduce((s, t) => s + t.count, 0);

  // Render D3 charts
  if (timeline.length) {
    drawSemVerTimeline(timeline, cumulative);
    drawBreakingBlast(timeline);
  }
  if (languages.length) drawLanguageTreemap(languages);
  if (typeBars.length)  drawCommitDNAArc(typeBars, semver, totalCommits);

  // Legacy SSR animations (now correctly wired)
  animateCountUp();
  animateBars();
}
