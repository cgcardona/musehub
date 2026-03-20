/**
 * mcp-docs.ts — interactive behaviour for the MCP reference page.
 *
 * - Real-time tool filter (search by name or description)
 * - Copy-to-clipboard buttons
 * - Sidebar active-link highlight on scroll
 */

export function initMcpDocs(): void {
  setupToolFilter();
  setupCopyButtons();
  setupSidebarHighlight();
}

// ── Tool filter ───────────────────────────────────────────────────────────────

function setupToolFilter(): void {
  const input = document.getElementById('mcp-tool-filter') as HTMLInputElement | null;
  const countEl = document.getElementById('mcp-tool-count');
  if (!input) return;

  const cards = Array.from(document.querySelectorAll<HTMLElement>('.mcp-tool-card'));

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    let visible = 0;

    cards.forEach((card) => {
      const name = (card.dataset.toolName || '').toLowerCase();
      const desc = (card.dataset.toolDesc || '').toLowerCase();
      const match = !q || name.includes(q) || desc.includes(q);
      card.hidden = !match;
      if (match) visible++;
    });

    if (countEl) {
      countEl.textContent = q
        ? `${visible} / ${cards.length} tools`
        : `${cards.length} tools`;
    }

    // Show/hide section headings when all their tools are hidden
    document.querySelectorAll<HTMLElement>('.mcp-section').forEach((section) => {
      const toolList = section.querySelector('.mcp-tool-list');
      if (!toolList) return;
      const visibleInSection = Array.from(toolList.querySelectorAll<HTMLElement>('.mcp-tool-card'))
        .some((c) => !c.hidden);
      section.style.display = (q && !visibleInSection) ? 'none' : '';
    });
  });
}

// ── Copy buttons ──────────────────────────────────────────────────────────────

function setupCopyButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('.mcp-copy-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy || '';
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3fb950" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
        setTimeout(() => { btn.innerHTML = orig; }, 1500);
      });
    });
  });
}

// ── Sidebar active link on scroll ─────────────────────────────────────────────

function setupSidebarHighlight(): void {
  const links = Array.from(document.querySelectorAll<HTMLAnchorElement>('.mcp-sidebar-link[href^="#"]'));
  if (!links.length) return;

  const sections = links
    .map((link) => {
      const id = link.getAttribute('href')!.slice(1);
      return { link, el: document.getElementById(id) };
    })
    .filter((s): s is { link: HTMLAnchorElement; el: HTMLElement } => !!s.el);

  const headerHeight = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--header-height') || '42', 10);

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const match = sections.find((s) => s.el === entry.target);
        if (match) {
          if (entry.isIntersecting) {
            links.forEach((l) => l.style.removeProperty('color'));
            match.link.style.color = 'var(--text-primary)';
          }
        }
      });
    },
    { rootMargin: `-${headerHeight + 48}px 0px -60% 0px`, threshold: 0 },
  );

  sections.forEach(({ el }) => observer.observe(el));
}
