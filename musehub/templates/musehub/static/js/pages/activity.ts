/**
 * Activity feed – progressive enhancement.
 *
 * Responsibilities:
 *  1. Row entrance animations (staggered fade-in via IntersectionObserver).
 *  2. Keep the "latest event" timestamp chip up-to-date without a full reload
 *     by re-rendering relative timestamps every 60 s.
 */

declare global {
  interface Window {
    __activityCfg?: { base: string };
  }
}

// ── Relative-time refresh ─────────────────────────────────────────────────

/** Parse an ISO datetime string and return a human-readable relative label. */
function relativeLabel(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s  = Math.floor(ms / 1000);
  if (s < 60)  return "just now";
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function refreshTimestamps(): void {
  document.querySelectorAll<HTMLElement>("[data-iso]").forEach(el => {
    const iso = el.dataset.iso;
    if (iso) el.textContent = relativeLabel(iso);
  });
}

// ── Row entrance animation ────────────────────────────────────────────────

function attachRowAnimations(root: Element = document.body): void {
  const rows = root.querySelectorAll<HTMLElement>(".av-row, .av-date-header");
  if (!rows.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (!entry.isIntersecting) return;
      const el = entry.target as HTMLElement;
      el.style.animationDelay = `${i * 30}ms`;
      el.classList.add("av-row--visible");
      io.unobserve(el);
    });
  }, { threshold: 0.05 });

  rows.forEach(row => {
    row.classList.add("av-row--hidden");
    io.observe(row);
  });
}

// ── HTMX post-swap re-init ────────────────────────────────────────────────

function bindHtmxSwap(): void {
  document.body.addEventListener("htmx:afterSwap", (e: Event) => {
    const target = (e as CustomEvent).detail?.target as HTMLElement | undefined;
    if (!target) return;
    if (target.id === "av-feed" || target.closest("#av-feed")) {
      attachRowAnimations(target);
      refreshTimestamps();
    }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────

export function initActivity(): void {
  attachRowAnimations();
  refreshTimestamps();
  setInterval(refreshTimestamps, 60_000);
  bindHtmxSwap();
}
