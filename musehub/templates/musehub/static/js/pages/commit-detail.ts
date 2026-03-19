/**
 * commit-detail.ts — Commit detail page module.
 *
 * Responsibilities:
 *  1. Animate musical dimension change bars into view (IntersectionObserver).
 *  2. Initialize WaveSurfer audio player from window.__commitCfg.audioUrl.
 *  3. Copy-to-clipboard for commit SHA chip.
 */

declare global {
  interface Window {
    __commitCfg?: {
      repoId: string;
      commitId: string;
      shortId: string;
      base: string;
      audioUrl: string | null;
      listenUrl: string;
      embedUrl: string;
    };
    WaveSurfer?: {
      create(options: Record<string, unknown>): WaveSurferInstance;
    };
  }
}

interface WaveSurferInstance {
  load(url: string): void;
  playPause(): void;
  isPlaying(): boolean;
  getCurrentTime(): number;
  getDuration(): number;
  on(event: string, cb: (...args: unknown[]) => void): void;
}

// ── Dimension bar animations ──────────────────────────────────────────────

function attachDimAnimations(): void {
  const rows = document.querySelectorAll<HTMLElement>(".cd-dim-row");
  if (!rows.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const row  = entry.target as HTMLElement;
      const fill = row.querySelector<HTMLElement>(".cd-dim-fill");
      const pct  = row.dataset.target ?? "0";
      if (fill) {
        fill.style.width = "0";
        requestAnimationFrame(() => { fill.style.width = `${pct}%`; });
      }
      io.unobserve(row);
    });
  }, { threshold: 0.2 });

  rows.forEach(row => {
    const fill = row.querySelector<HTMLElement>(".cd-dim-fill");
    if (fill) fill.style.width = "0";
    io.observe(row);
  });
}

// ── SHA copy button ───────────────────────────────────────────────────────

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
    } catch { /* clipboard unavailable */ }
  });
}

// ── WaveSurfer audio player ───────────────────────────────────────────────

function fmtTime(s: number): string {
  if (!isFinite(s)) return "—";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function initAudioPlayer(url: string): void {
  const wrap    = document.getElementById("cd-waveform");
  const playBtn = document.getElementById("cd-play-btn") as HTMLButtonElement | null;
  const timeEl  = document.getElementById("cd-time");
  if (!wrap) return;

  if (window.WaveSurfer) {
    wrap.innerHTML = '<div id="ws-inner" style="height:64px;width:100%"></div>';
    const ws = window.WaveSurfer.create({
      container:     "#ws-inner",
      waveColor:     "var(--color-accent)",
      progressColor: "#388bfd",
      height:        64,
      normalize:     true,
      backend:       "MediaElement",
    });
    ws.load(url);
    ws.on("audioprocess", () => {
      if (timeEl) timeEl.textContent = fmtTime(ws.getCurrentTime());
    });
    ws.on("finish", () => {
      if (playBtn) playBtn.textContent = "▶";
    });
    ws.on("error", () => {
      wrap.innerHTML = '<span style="color:var(--color-danger);font-size:var(--font-size-sm)">⚠ Could not load audio.</span>';
    });
    if (playBtn) {
      playBtn.addEventListener("click", () => {
        ws.playPause();
        playBtn.textContent = ws.isPlaying() ? "⏸" : "▶";
      });
    }
  } else {
    // WaveSurfer not available — render native audio element
    wrap.innerHTML = `<audio controls preload="none" style="width:100%"><source src="${url}" /></audio>`;
    if (playBtn) playBtn.style.display = "none";
  }
}

// ── Entry point ───────────────────────────────────────────────────────────

export function initCommitDetail(): void {
  attachDimAnimations();
  bindShaCopy();

  const cfg = window.__commitCfg;
  if (cfg?.audioUrl) {
    initAudioPlayer(cfg.audioUrl);
  }
}
