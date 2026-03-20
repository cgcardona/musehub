/**
 * insights.ts — Insights page progressive enhancement.
 *
 * All metrics are SSR'd; this module only adds:
 * - Bar chart entrance animations (IntersectionObserver)
 * - Donut chart SVG animation
 * - Stat card count-up animation
 * - Stacked bar hover tooltips
 */

declare global {
  interface Window {
    __insightsCfg?: { repoId: string; viewerType: string };
    MusePages: Record<string, () => void>;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function $<T extends Element = Element>(sel: string, root: Document | Element = document): T | null {
  return root.querySelector<T>(sel);
}
function $$<T extends Element = Element>(sel: string, root: Document | Element = document): T[] {
  return Array.from(root.querySelectorAll<T>(sel));
}

// ── Bar entrance animations ───────────────────────────────────────────────────

function animateBars(): void {
  const bars = $$<HTMLElement>('.js-bar-fill');
  if (!bars.length) return;

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el  = entry.target as HTMLElement;
      const pct = el.style.getPropertyValue('--bar-pct') || '0%';
      // Reset, then animate in
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

// ── Donut entrance animation ──────────────────────────────────────────────────

function animateDonuts(): void {
  const fills = $$<SVGCircleElement>('.ins-donut-fill');
  if (!fills.length) return;

  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target as SVGCircleElement;
      const da = el.getAttribute('stroke-dasharray') ?? '';
      el.setAttribute('stroke-dasharray', `0 ${da.split(' ')[1] ?? '240'}`);
      requestAnimationFrame(() => {
        el.style.transition = 'stroke-dasharray 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        el.setAttribute('stroke-dasharray', da);
      });
      io.unobserve(el);
    });
  }, { threshold: 0.2 });

  fills.forEach(f => io.observe(f));
}

// ── Stat card count-up ────────────────────────────────────────────────────────

function animateCountUp(): void {
  const vals = $$<HTMLElement>('.ins-stat-value');
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
        const t   = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);  // ease-out cubic
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

// ── Stacked language bar tooltips ─────────────────────────────────────────────

function setupStackTooltips(): void {
  const segs = $$<HTMLElement>('.ins-lang-stack-seg');
  if (!segs.length) return;

  let tip: HTMLDivElement | null = null;

  function getTip(): HTMLDivElement {
    if (!tip) {
      tip = document.createElement('div');
      tip.style.cssText = [
        'position:fixed;background:var(--bg-overlay);border:1px solid var(--border-default)',
        'border-radius:6px;padding:4px 10px;font-size:11px;color:var(--text-primary)',
        'pointer-events:none;z-index:9999;opacity:0;transition:opacity 0.1s;white-space:nowrap',
      ].join(';');
      document.body.appendChild(tip);
    }
    return tip;
  }

  segs.forEach(seg => {
    seg.addEventListener('mouseenter', e => {
      const me = e as MouseEvent;
      const t  = getTip();
      t.textContent = seg.getAttribute('title') ?? '';
      t.style.left  = `${me.clientX + 10}px`;
      t.style.top   = `${me.clientY - 32}px`;
      t.style.opacity = '1';
    });
    seg.addEventListener('mousemove', e => {
      const me = e as MouseEvent;
      if (!tip) return;
      tip.style.left = `${me.clientX + 10}px`;
      tip.style.top  = `${me.clientY - 32}px`;
    });
    seg.addEventListener('mouseleave', () => {
      if (tip) tip.style.opacity = '0';
    });
  });
}

// ── Dimension card hover enhancement ─────────────────────────────────────────

function setupDimCards(): void {
  $$<HTMLElement>('.ins-dim-card').forEach(card => {
    card.addEventListener('mouseenter', () => {
      card.style.boxShadow = '0 4px 20px rgba(0,0,0,0.25)';
    });
    card.addEventListener('mouseleave', () => {
      card.style.boxShadow = '';
    });
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initInsights(): void {
  animateBars();
  animateDonuts();
  animateCountUp();
  setupStackTooltips();
  setupDimCards();
}
