/**
 * scan.ts — the free repo scan card (homepage hero) and its result page.
 *
 * Homepage: submits POST /scan, shows progress, then fills the result panel
 * from the JSON. Both pages: the "How the scan works" dialog, copy buttons.
 */

interface ScanPayload {
  id: string; repo: string; sha: string; pulls: number;
  grepTokens: number; museTokens: number; ratio: number; taskSaving: number;
  falseMatches: number; aliasMisses: number; shortUrl: string; imageUrl: string;
}

const $ = <T extends HTMLElement>(id: string): T | null => document.getElementById(id) as T | null;

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function copy(text: string, btn: HTMLElement): void {
  const label = btn.textContent;
  void navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied';
    window.setTimeout(() => { btn.textContent = label; }, 1500);
  });
}

function initInfo(): void {
  const dialog = $<HTMLDialogElement>('scan-info');
  $('scan-info-open')?.addEventListener('click', () => dialog?.showModal());
  dialog?.querySelector('[data-close]')?.addEventListener('click', () => dialog.close());
  dialog?.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
  const promptBtn = $('scan-prompt-copy');
  promptBtn?.addEventListener('click', () => copy($('scan-prompt-text')?.textContent ?? '', promptBtn));
  document.querySelectorAll<HTMLElement>('[data-copy]').forEach((b) =>
    b.addEventListener('click', () => copy(b.dataset.copy ?? '', b)));
}

function fill(r: ScanPayload): void {
  const set = (k: string, v: string): void => {
    document.querySelectorAll<HTMLElement>(`#scan-result [data-k="${k}"]`).forEach((el) => { el.textContent = v; });
  };
  set('repo', r.repo); set('sha', r.sha); set('ratio', String(r.ratio)); set('pulls', String(r.pulls));
  set('grep', `${fmtTokens(r.grepTokens)} tokens`); set('muse', `${fmtTokens(r.museTokens)} tokens`);
  set('saving', `${Math.round(r.taskSaving * 100)}%`);
  set('false', String(r.falseMatches)); set('alias', String(r.aliasMisses));
  const grepBar = $('scan-bar-grep'); if (grepBar) grepBar.style.width = '100%';
  const museBar = $('scan-bar-muse'); if (museBar) museBar.style.width = `${Math.max(1, (100 * r.museTokens) / r.grepTokens)}%`;
  const img = $<HTMLImageElement>('scan-card-img'); if (img) img.src = r.imageUrl;
  const preview = $<HTMLAnchorElement>('scan-preview'); if (preview) preview.href = r.shortUrl;
  const dl = $<HTMLAnchorElement>('scan-download');
  if (dl) { dl.href = r.imageUrl; dl.download = `muse-scan-${r.id}.png`; }
  const short = $<HTMLAnchorElement>('scan-short');
  if (short) { short.href = r.shortUrl; short.textContent = r.shortUrl.replace(/^https?:\/\//, ''); }
  const text = `My repo ${r.repo}: Muse finds what a change breaks with ${r.ratio}x fewer agent tokens. Free scan:`;
  const x = $<HTMLAnchorElement>('scan-share-x');
  if (x) x.href = `https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(r.shortUrl)}`;
  const copyBtn = $('scan-copy');
  if (copyBtn) copyBtn.onclick = () => copy(r.shortUrl, copyBtn);
}

function initForm(): void {
  const form = $<HTMLFormElement>('scan-form');
  if (!form) return;
  const steps = $('scan-steps'); const result = $('scan-result'); const err = $('scan-error');
  const submit = $<HTMLButtonElement>('scan-submit'); const bar = $('scan-progress');
  const prefill = new URLSearchParams(location.search).get('scan');
  const input = $<HTMLInputElement>('scan-repo');
  if (prefill && input) input.value = prefill;

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const repo = input?.value.trim() ?? '';
    if (!repo) return;
    if (err) err.hidden = true;
    if (result) result.hidden = true;
    if (steps) steps.hidden = false;
    if (submit) { submit.disabled = true; submit.textContent = 'Scanning'; }
    const rows = Array.from(document.querySelectorAll<HTMLElement>('#scan-steps .scan-step'));
    let i = 0;
    const tick = (): void => {
      rows.forEach((row, j) => {
        row.classList.toggle('done', j < i); row.classList.toggle('now', j === i);
        const mark = row.querySelector('i'); if (mark) mark.textContent = j < i ? '✓' : j === i ? '›' : '·';
      });
      if (bar) bar.style.width = `${Math.min(92, 8 + i * 24)}%`;
    };
    tick();
    const timer = window.setInterval(() => { if (i < rows.length - 1) { i += 1; tick(); } }, 6000);

    fetch('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ repo }) })
      .then(async (res) => {
        const body = (await res.json()) as ScanPayload & { error?: string };
        if (!res.ok) throw new Error(body.error ?? (res.status === 429 ? 'Too many scans from here. Try again in a minute.' : 'The scan failed.'));
        fill(body);
        if (result) result.hidden = false;
      })
      .catch((ex: Error) => { if (err) { err.textContent = ex.message; err.hidden = false; } })
      .finally(() => {
        window.clearInterval(timer);
        if (steps) steps.hidden = true;
        if (submit) { submit.disabled = false; submit.textContent = 'Scan for free'; }
      });
  });
}

export function initScan(): void {
  if (!document.getElementById('scan-card')) return;
  initInfo();
  initForm();
}
