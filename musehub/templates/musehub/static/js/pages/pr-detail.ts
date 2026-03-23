/**
 * PR Detail page — progressive enhancement.
 *
 * Responsibilities:
 *  1. Animate dimension divergence bars into view (IntersectionObserver).
 *  2. Copy-to-clipboard for commit SHA chips.
 *  3. Merge strategy selector — updates the HTMX button's hx-vals payload.
 */

// ── Dimension bar animations ──────────────────────────────────────────────

function attachDimAnimations(): void {
  const rows = document.querySelectorAll<HTMLElement>(".pd-dim-row");
  if (!rows.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const row   = entry.target as HTMLElement;
      const fill  = row.querySelector<HTMLElement>(".pd-dim-fill");
      const target = row.dataset.target ?? "0";
      if (fill) {
        // Reset to 0 then animate to target
        fill.style.width = "0";
        requestAnimationFrame(() => {
          fill.style.width = `${target}%`;
        });
      }
      io.unobserve(row);
    });
  }, { threshold: 0.2 });

  rows.forEach(row => io.observe(row));
}

// ── Copy-to-clipboard for SHA chips ──────────────────────────────────────

function bindShaCopy(): void {
  document.addEventListener("click", async (e: MouseEvent) => {
    const btn = (e.target as Element).closest<HTMLElement>("[data-sha]");
    if (!btn) return;
    const sha = btn.dataset.sha;
    if (!sha) return;
    try {
      await navigator.clipboard.writeText(sha);
      const orig = btn.textContent ?? "";
      btn.textContent = "✓";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    } catch {
      // clipboard not available in this context — silently ignore
    }
  });
}

// ── Merge strategy selector ───────────────────────────────────────────────

function bindMergeStrategy(): void {
  const strategies = document.querySelectorAll<HTMLElement>(".pd-strategy");
  const mergeBtn   = document.querySelector<HTMLButtonElement>("#merge-btn");
  if (!strategies.length || !mergeBtn) return;

  const strategyLabels: Record<string, string> = {
    merge_commit: "✓ Merge pull request",
    squash:       "⬜ Squash and merge",
    rebase:       "🔄 Rebase and merge",
  };

  strategies.forEach(strategy => {
    strategy.addEventListener("click", () => {
      const selected = strategy.dataset.strategy ?? "merge_commit";

      // Update active class
      strategies.forEach(s => s.classList.remove("active"));
      strategy.classList.add("active");

      // Update HTMX vals + button label
      mergeBtn.setAttribute(
        "hx-vals",
        JSON.stringify({ mergeStrategy: selected, deleteBranch: true }),
      );
      mergeBtn.textContent = strategyLabels[selected] ?? "✓ Merge";
    });
  });
}

// ── Entry point ───────────────────────────────────────────────────────────

export function initPRDetail(_data?: Record<string, unknown>): void {
  attachDimAnimations();
  bindShaCopy();
  bindMergeStrategy();
}
