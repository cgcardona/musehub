/**
 * Arrange page — progressive enhancement.
 *
 * All matrix data is SSR'd by the Python route handler.
 * This module adds:
 *  1. Fixed-position tooltip on cell hover.
 *  2. Row highlight on <tr> hover.
 *  3. Column highlight on header/cell hover.
 *  4. Entrance animation: bar fills animate in when the matrix scrolls into view.
 */

interface ArrangeCfg {
  base: string;
  ref: string;
  owner: string;
  repoSlug: string;
}


// ── Tooltip ──────────────────────────────────────────────────────────────────

function setupTooltip(): void {
  const tip      = document.getElementById("ar-tooltip") as HTMLElement | null;
  const tipTitle = document.getElementById("ar-tip-title") as HTMLElement | null;
  const tipNotes = document.getElementById("ar-tip-notes") as HTMLElement | null;
  const tipDens  = document.getElementById("ar-tip-density") as HTMLElement | null;
  const tipBeats = document.getElementById("ar-tip-beats") as HTMLElement | null;
  if (!tip) return;

  function show(cell: HTMLElement, x: number, y: number): void {
    const inst    = cell.dataset.instrument ?? "";
    const sec     = cell.dataset.section ?? "";
    const notes   = cell.dataset.notes ?? "0";
    const density = parseFloat(cell.dataset.density ?? "0");
    const bStart  = cell.dataset.beatStart ?? "0";
    const bEnd    = cell.dataset.beatEnd ?? "0";

    if (tipTitle) tipTitle.textContent = `${inst.charAt(0).toUpperCase() + inst.slice(1)} · ${sec.replace(/_/g, " ")}`;
    if (tipNotes) tipNotes.textContent = notes;
    if (tipDens)  tipDens.textContent  = `${(density * 100).toFixed(0)}%`;
    if (tipBeats) tipBeats.textContent = `${parseFloat(bStart).toFixed(0)}–${parseFloat(bEnd).toFixed(0)}`;

    tip.style.left = `${x + 16}px`;
    tip.style.top  = `${y - 16}px`;
    tip.classList.add("ar-tooltip--visible");
  }

  function hide(): void {
    tip.classList.remove("ar-tooltip--visible");
  }

  document.querySelectorAll<HTMLElement>(".ar-cell[data-notes]").forEach(cell => {
    cell.addEventListener("mouseenter", e => {
      const me = e as MouseEvent;
      show(cell, me.clientX, me.clientY);
    });
    cell.addEventListener("mousemove", e => {
      const me = e as MouseEvent;
      tip.style.left = `${me.clientX + 16}px`;
      tip.style.top  = `${me.clientY - 16}px`;
    });
    cell.addEventListener("mouseleave", hide);
  });
}

// ── Row highlight ─────────────────────────────────────────────────────────────

function setupRowHighlight(): void {
  const rows = document.querySelectorAll<HTMLTableRowElement>("#ar-matrix tbody tr");
  rows.forEach(row => {
    row.addEventListener("mouseenter", () => row.classList.add("ar-row-hover"));
    row.addEventListener("mouseleave", () => row.classList.remove("ar-row-hover"));
  });
}

// ── Column highlight ──────────────────────────────────────────────────────────

function setupColHighlight(): void {
  const table = document.getElementById("ar-matrix");
  if (!table) return;

  let activeCol: number | null = null;

  function setColHighlight(colIdx: number | null): void {
    // Remove all existing highlights
    table!.querySelectorAll<HTMLElement>(".ar-col-hover").forEach(el =>
      el.classList.remove("ar-col-hover"),
    );
    if (colIdx === null) return;
    table!.querySelectorAll<HTMLElement>(`[data-col="${colIdx}"]`).forEach(el =>
      el.classList.add("ar-col-hover"),
    );
  }

  table.querySelectorAll<HTMLElement>("[data-col]").forEach(el => {
    el.addEventListener("mouseenter", () => {
      const col = parseInt(el.dataset.col ?? "-1", 10);
      if (col >= 0) {
        activeCol = col;
        setColHighlight(col);
      }
    });
    el.addEventListener("mouseleave", () => {
      activeCol = null;
      setColHighlight(null);
    });
  });
}

// ── Bar fill entrance animation ───────────────────────────────────────────────

function animatePanelBars(): void {
  const fills = document.querySelectorAll<HTMLElement>(".ar-panel-bar-fill");
  if (!fills.length) return;

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target as HTMLElement;
      const target = el.style.width;
      el.style.width = "0%";
      requestAnimationFrame(() => {
        el.style.transition = "width 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94)";
        el.style.width = target;
      });
      observer.unobserve(el);
    });
  }, { threshold: 0.15 });

  fills.forEach(f => observer.observe(f));
}

// ── Cell density bar animation ────────────────────────────────────────────────

function animateCellBars(): void {
  document.querySelectorAll<HTMLElement>(".ar-cell-bar-fill").forEach(el => {
    const target = el.style.width;
    el.style.width = "0%";
    setTimeout(() => {
      el.style.transition = "width 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)";
      el.style.width = target;
    }, 100 + Math.random() * 200);
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initArrange(_data?: Record<string, unknown>): void {
  setupTooltip();
  setupRowHighlight();
  setupColHighlight();
  animatePanelBars();
  animateCellBars();
}
