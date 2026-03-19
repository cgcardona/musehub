/**
 * Search page — progressive enhancement.
 *
 * Responsibilities:
 *  1. Highlight search terms in rendered result card titles.
 *  2. Wire mode pills → hidden input → re-trigger HTMX form submit.
 *  3. Re-run highlighting after every HTMX swap inside #sr-results.
 *  4. Global search page: same mode pill wiring for #sr-global-form.
 */

interface SearchCfg {
  owner: string;
  repoSlug: string;
  base: string;
  query: string;
}

declare global {
  interface Window {
    __searchCfg?: SearchCfg;
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function escRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ── Highlight search terms ────────────────────────────────────────────────────

function highlightTerms(root: Element, query: string): void {
  if (!query || query.length < 2) return;
  const terms = query.trim().split(/\s+/).filter(t => t.length > 1);
  if (!terms.length) return;

  const pattern = new RegExp(`(${terms.map(escRegex).join("|")})`, "gi");

  root.querySelectorAll<HTMLElement>("[data-highlight]").forEach(el => {
    const original = el.textContent ?? "";
    if (!pattern.test(original)) return;
    pattern.lastIndex = 0;
    el.innerHTML = original.replace(pattern, '<mark class="sr-hl">$1</mark>');
  });
}

// ── Mode pill wiring ──────────────────────────────────────────────────────────

function setupModePills(
  containerSelector: string,
  hiddenInputId: string,
  formId: string,
): void {
  const container = document.querySelector(containerSelector);
  const hidden    = document.getElementById(hiddenInputId) as HTMLInputElement | null;
  const form      = document.getElementById(formId) as HTMLFormElement | null;
  if (!container || !hidden || !form) return;

  container.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach(btn => {
    btn.addEventListener("click", () => {
      hidden.value = btn.dataset.mode ?? "keyword";

      // Update active pill styles
      container.querySelectorAll("[data-mode]").forEach(b =>
        b.classList.remove("sr-mode-pill--active"),
      );
      btn.classList.add("sr-mode-pill--active");

      // Trigger HTMX form submit by dispatching a submit event
      form.dispatchEvent(new Event("submit", { bubbles: true }));
    });
  });

  // Global search page mode pills (data-global-mode)
  container.querySelectorAll<HTMLButtonElement>("[data-global-mode]").forEach(btn => {
    const globalInput = document.getElementById("sr-global-mode") as HTMLInputElement | null;
    if (!globalInput) return;
    btn.addEventListener("click", () => {
      globalInput.value = btn.dataset.globalMode ?? "keyword";
      container.querySelectorAll("[data-global-mode]").forEach(b =>
        b.classList.remove("sr-mode-pill--active"),
      );
      btn.classList.add("sr-mode-pill--active");
      form.dispatchEvent(new Event("submit", { bubbles: true }));
    });
  });
}

// ── Re-highlight after HTMX swap ─────────────────────────────────────────────

function setupHtmxHighlight(): void {
  document.body.addEventListener("htmx:afterSwap", (e: Event) => {
    const target = (e as CustomEvent).detail?.target as Element | null;
    if (!target) return;
    const input = document.getElementById("sr-q") as HTMLInputElement | null;
    const query = input?.value ?? window.__searchCfg?.query ?? "";
    highlightTerms(target, query);
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initSearch(): void {
  const cfg   = window.__searchCfg;
  const query = cfg?.query ?? "";

  // Initial highlight on page load
  const results = document.getElementById("sr-results");
  if (results && query) highlightTerms(results, query);

  // Global search initial highlight
  const globalResults = document.getElementById("sr-global-results");
  if (globalResults && query) highlightTerms(globalResults, query);

  // Mode pills
  setupModePills(".sr-mode-bar", "sr-mode-hidden", "sr-form");
  setupModePills(".sr-mode-bar", "sr-global-mode",  "sr-global-form");

  // Re-highlight on every HTMX swap
  setupHtmxHighlight();
}
