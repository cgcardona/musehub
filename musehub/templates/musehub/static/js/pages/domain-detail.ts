/**
 * domain-detail.ts — Domain plugin detail page interactivity.
 *
 * Handles:
 *  - Copy-to-clipboard for terminal blocks and hash cells
 *  - Entrance animations for dimension cards (IntersectionObserver)
 *  - Install button feedback
 */

export interface DomainDetailData {
  domainSlug?: string;
  domainId?: string;
  [key: string]: unknown;
}

// ── Copy to clipboard ─────────────────────────────────────────────────────────

function setupCopyButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-copy-id]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const targetId = btn.dataset.copyId;
      if (!targetId) return;
      const el = document.getElementById(targetId);
      if (!el) return;
      const text = el.textContent?.trim() ?? '';
      try {
        await navigator.clipboard.writeText(text);
        const prev = btn.textContent;
        btn.textContent = '✓ Copied';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = prev;
          btn.classList.remove('copied');
        }, 2000);
      } catch {
        // fallback: select text
        const range = document.createRange();
        range.selectNode(el);
        window.getSelection()?.removeAllRanges();
        window.getSelection()?.addRange(range);
      }
    });
  });
}

// ── Dimension card entrance animation ─────────────────────────────────────────

function setupDimAnimations(): void {
  const grid = document.querySelector<HTMLElement>('.dd-dim-grid');
  if (!grid) return;

  const cards = Array.from(grid.querySelectorAll<HTMLElement>('.dd-dim-card'));
  cards.forEach(card => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(12px)';
  });

  const observer = new IntersectionObserver(entries => {
    if (!entries.some(e => e.isIntersecting)) return;
    observer.disconnect();
    cards.forEach((card, i) => {
      setTimeout(() => {
        card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
        card.style.opacity = '1';
        card.style.transform = 'none';
      }, i * 30);
    });
  }, { threshold: 0.1 });

  observer.observe(grid);
}

// ── Stat pill count-up animation ──────────────────────────────────────────────

function setupStatCountUp(): void {
  const pills = document.querySelectorAll<HTMLElement>('.dd-stat-pill__value');
  pills.forEach(el => {
    const raw = el.textContent?.trim() ?? '';
    const num = parseInt(raw, 10);
    if (isNaN(num) || num <= 1) return;
    el.textContent = '0';
    const duration = 600;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(ease * num));
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

// ── Install button ─────────────────────────────────────────────────────────────

function setupInstallButton(): void {
  const btn = document.getElementById('dd-install-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    // Show a "copied" instruction since Muse CLI install is a terminal command
    const installEl = document.getElementById('install-cmd');
    if (!installEl) return;
    const text = installEl.textContent?.trim() ?? '';
    navigator.clipboard.writeText(text).then(() => {
      const prev = btn.textContent;
      btn.textContent = '✓ Command Copied — paste in terminal';
      btn.setAttribute('disabled', '');
      setTimeout(() => {
        btn.textContent = prev ?? '↓ Install Domain';
        btn.removeAttribute('disabled');
      }, 3000);
    }).catch(() => {
      btn.textContent = 'Open terminal and run: muse domain install';
      setTimeout(() => { btn.textContent = '↓ Install Domain'; }, 4000);
    });
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initDomainDetail(_data: DomainDetailData): void {
  setupCopyButtons();
  setupDimAnimations();
  setupStatCountUp();
  setupInstallButton();
}
