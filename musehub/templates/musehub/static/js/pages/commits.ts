/**
 * commits.ts — Commits list page module.
 *
 * Responsibilities:
 *  1. Branch selector → navigates with ?branch= param.
 *  2. Filter form → let HTMX handle partial updates; no manual JS submit needed.
 *  3. Compare mode — toggle, checkbox selection, compare strip link.
 *     Uses event delegation so it survives HTMX fragment swaps.
 */

declare global {
  interface Window {
    __commitsCfg?: {
      repoId: string;
      base: string;
      page: number;
      perPage: number;
      totalPages: number;
      branch: string;
    };
  }
}

// ── URL helpers ───────────────────────────────────────────────────────────

function buildUrl(overrides: Record<string, string | number | null>): string {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(overrides)) {
    if (v === null || v === undefined || v === "") {
      url.searchParams.delete(k);
    } else {
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

// ── Branch selector ───────────────────────────────────────────────────────

function bindBranchSelector(): void {
  const sel = document.getElementById("branch-sel") as HTMLSelectElement | null;
  if (!sel) return;
  sel.addEventListener("change", () => {
    window.location.href = buildUrl({ branch: sel.value || null, page: 1 });
  });
}

// ── Compare mode ──────────────────────────────────────────────────────────

let compareMode = false;
const selected  = new Set<string>();

function updateCompareStrip(): void {
  const strip       = document.getElementById("compare-strip");
  const countEl     = document.getElementById("compare-count");
  const link        = document.getElementById("compare-link") as HTMLAnchorElement | null;
  const cfg         = window.__commitsCfg;
  if (!strip) return;

  const n = selected.size;
  if (countEl) countEl.textContent = `${n} selected`;

  if (n === 2 && link && cfg) {
    const [a, b] = [...selected];
    link.href = `${cfg.base}/compare/${a}...${b}`;
    link.style.display = "";
  } else if (link) {
    link.style.display = "none";
  }
  strip.classList.toggle("visible", compareMode);
}

function toggleCompareMode(): void {
  compareMode = !compareMode;
  document.body.classList.toggle("compare-mode", compareMode);
  selected.clear();
  document.querySelectorAll<HTMLInputElement>(".compare-check").forEach(cb => { cb.checked = false; });
  document.querySelectorAll<HTMLElement>(".commit-list-row").forEach(r => r.classList.remove("compare-selected"));
  updateCompareStrip();
  const btn = document.getElementById("compare-toggle-btn");
  if (btn) btn.textContent = compareMode ? "✕ Exit Compare" : "⊞ Compare";
}

function onCompareCheck(cb: HTMLInputElement, commitId: string): void {
  const row = cb.closest<HTMLElement>(".commit-list-row");
  if (cb.checked) {
    if (selected.size >= 2) { cb.checked = false; return; }
    selected.add(commitId);
    row?.classList.add("compare-selected");
  } else {
    selected.delete(commitId);
    row?.classList.remove("compare-selected");
  }
  updateCompareStrip();
}

function bindCompareMode(): void {
  // Compare toggle button
  document.getElementById("compare-toggle-btn")
    ?.addEventListener("click", toggleCompareMode);

  // Cancel button inside strip
  document.getElementById("compare-cancel-btn")
    ?.addEventListener("click", toggleCompareMode);

  // Checkbox event delegation — survives HTMX fragment swaps
  document.addEventListener("change", (e: Event) => {
    const cb = (e.target as Element).closest<HTMLInputElement>(".compare-check");
    if (!cb) return;
    const commitId = cb.dataset.commitId ?? cb.closest<HTMLElement>(".commit-list-row")?.dataset.commitId;
    if (commitId) onCompareCheck(cb, commitId);
  });
}

// ── Re-apply compare state after HTMX swaps ──────────────────────────────

function bindHtmxSwap(): void {
  document.body.addEventListener("htmx:afterSwap", () => {
    // Re-check any previously selected commits after fragment swap
    selected.forEach(id => {
      const row = document.querySelector<HTMLElement>(`[data-commit-id="${id}"]`);
      const cb  = row?.querySelector<HTMLInputElement>(".compare-check");
      if (row && cb) {
        row.classList.add("compare-selected");
        cb.checked = true;
      }
    });
    if (compareMode) {
      document.body.classList.add("compare-mode");
    }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────

export function initCommits(): void {
  bindBranchSelector();
  bindCompareMode();
  bindHtmxSwap();
}
