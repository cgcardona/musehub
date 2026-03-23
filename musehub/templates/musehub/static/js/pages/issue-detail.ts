/**
 * issue-detail.ts — Issue detail page module.
 *
 * Responsibilities:
 *  1. Comment entrance animations (IntersectionObserver stagger).
 *  2. Re-animate comments after HTMX swap (new comment submitted).
 *  3. Milestone progress bar entrance animation.
 *  4. Copy issue URL to clipboard (keyboard shortcut + button if present).
 */


// ── Comment entrance animations ───────────────────────────────────────────────

function animateComments(root: Element | Document = document): void {
  const comments = root.querySelectorAll<HTMLElement>(".id-comment, .id-reply");
  if (!comments.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (!entry.isIntersecting) return;
      const el = entry.target as HTMLElement;
      el.style.animationDelay = `${i * 30}ms`;
      io.unobserve(el);
    });
  }, { threshold: 0.05 });

  comments.forEach(el => io.observe(el));
}

// ── Milestone fill animation ──────────────────────────────────────────────────

function animateMilestone(): void {
  const fill = document.querySelector<HTMLElement>(".id-ms-fill");
  if (!fill) return;
  const target = fill.style.width;
  fill.style.width = "0";
  requestAnimationFrame(() => {
    fill.style.transition = "width 0.6s ease";
    fill.style.width = target;
  });
}

// ── HTMX: re-animate on comment swap ─────────────────────────────────────────

function bindHtmxSwap(): void {
  document.body.addEventListener("htmx:afterSwap", (e: Event) => {
    const target = (e as CustomEvent).detail?.target as HTMLElement | undefined;
    if (!target) return;
    if (target.id === "issue-comments" || target.closest("#issue-comments")) {
      animateComments(target);
    }
  });
}

// ── Copy issue URL ────────────────────────────────────────────────────────────

function bindCopyUrl(): void {
  // "y" keyboard shortcut — mirrors GitHub's copy-issue-url shortcut
  document.addEventListener("keydown", async (e: KeyboardEvent) => {
    if (e.key !== "y" || e.ctrlKey || e.metaKey || e.altKey) return;
    const active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch { /* clipboard unavailable */ }
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initIssueDetail(_data?: Record<string, unknown>): void {
  animateComments();
  animateMilestone();
  bindHtmxSwap();
  bindCopyUrl();
}
