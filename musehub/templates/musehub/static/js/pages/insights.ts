/**
 * Insights page — client-side interactivity.
 *
 * All data is SSR'd by the Python route handler and passed via
 * window.__insightsCfg.  This module only adds progressive enhancement:
 * heatmap tooltip, BPM dot interactivity, and bar chart entrance animations.
 */

interface InsightsCfg {
  repoId: string;
  base: string;
  bpmPoints: Array<{ ts: string; bpm: number }>;
  bpmSvg: string;
}

declare global {
  interface Window {
    __insightsCfg?: InsightsCfg;
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function $(sel: string, root: Document | Element = document): Element | null {
  return root.querySelector(sel);
}
function $all(sel: string, root: Document | Element = document): Element[] {
  return Array.from(root.querySelectorAll(sel));
}

// ── Tooltip ──────────────────────────────────────────────────────────────────

function setupTooltip(): void {
  const tip = document.getElementById("in-tooltip") as HTMLElement | null;
  if (!tip) return;

  function show(text: string, x: number, y: number): void {
    tip!.textContent = text;
    tip!.style.left = `${x + 14}px`;
    tip!.style.top  = `${y - 28}px`;
    tip!.classList.add("in-tooltip--visible");
  }
  function hide(): void {
    tip!.classList.remove("in-tooltip--visible");
  }

  // Heatmap cells
  $all(".in-heatmap-day[data-count]").forEach(cell => {
    cell.addEventListener("mouseenter", e => {
      const el   = cell as HTMLElement;
      const date = el.dataset.date ?? "";
      const cnt  = el.dataset.count ?? "0";
      if (!date) return;
      const label = cnt === "0"
        ? `No commits on ${date}`
        : `${cnt} commit${cnt === "1" ? "" : "s"} on ${date}`;
      const rect = el.getBoundingClientRect();
      show(label, rect.left + window.scrollX, rect.top + window.scrollY);
    });
    cell.addEventListener("mouseleave", hide);
  });
}

// ── BPM dots ─────────────────────────────────────────────────────────────────

function setupBpmDots(cfg: InsightsCfg): void {
  const dotsGroup = document.getElementById("in-bpm-dots");
  const tip       = document.getElementById("in-tooltip") as HTMLElement | null;
  if (!dotsGroup || !tip || cfg.bpmPoints.length < 2) return;

  const pts  = cfg.bpmPoints;
  const bpms = pts.map(p => p.bpm);
  const bMin = Math.min(...bpms);
  const bMax = Math.max(...bpms);
  const bRange = Math.max(bMax - bMin, 10);

  pts.forEach((p, i) => {
    const x = ((i / (pts.length - 1)) * 580 + 10).toFixed(1);
    const y = ((1 - (p.bpm - bMin) / bRange) * 60 + 10).toFixed(1);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", "3");
    circle.setAttribute("class", "in-bpm-dot");
    circle.setAttribute("data-bpm", String(p.bpm));
    circle.setAttribute("data-ts", p.ts);

    circle.addEventListener("mouseenter", ev => {
      const date = p.ts.slice(0, 10);
      const me   = ev as MouseEvent;
      tip!.textContent = `${p.bpm} BPM · ${date}`;
      tip!.style.left  = `${me.clientX + 14}px`;
      tip!.style.top   = `${me.clientY - 28}px`;
      tip!.classList.add("in-tooltip--visible");
      circle.setAttribute("r", "5");
    });
    circle.addEventListener("mouseleave", () => {
      tip!.classList.remove("in-tooltip--visible");
      circle.setAttribute("r", "3");
    });

    dotsGroup.appendChild(circle);
  });
}

// ── Bar chart entrance animation ─────────────────────────────────────────────

function animateBars(): void {
  const fills = $all(".js-bar-fill");
  if (!fills.length) return;

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el  = entry.target as HTMLElement;
      const pct = el.style.getPropertyValue("--bar-pct") || "0%";
      el.style.width = "0%";
      requestAnimationFrame(() => {
        el.style.transition = "width 0.7s cubic-bezier(0.25, 0.46, 0.45, 0.94)";
        el.style.width = pct;
      });
      observer.unobserve(el);
    });
  }, { threshold: 0.1 });

  fills.forEach(f => observer.observe(f));
}

// ── Entry point ──────────────────────────────────────────────────────────────

export function initInsights(): void {
  const cfg = window.__insightsCfg;
  if (!cfg) return;

  setupTooltip();
  animateBars();
  if (cfg.bpmPoints.length >= 2) {
    setupBpmDots(cfg);
  }
}
