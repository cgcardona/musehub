/**
 * release-detail.ts — Release detail page module.
 *
 * Responsibilities:
 *  1. Wire the native <audio> element to custom play/pause, progress, time controls.
 *  2. Gracefully hide the player and show the error state when audio fails to load.
 *  3. Animate asset rows on scroll (IntersectionObserver).
 *  4. Progress bar click-to-seek.
 */

// ── Time formatter ────────────────────────────────────────────────────────────

function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) return "—";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

// ── Native audio player ───────────────────────────────────────────────────────

function initAudioPlayer(): void {
  const audio    = document.getElementById("rd-audio")    as HTMLAudioElement | null;
  const playBtn  = document.getElementById("rd-play-btn") as HTMLButtonElement | null;
  const progWrap = document.getElementById("rd-progress-wrap") as HTMLElement | null;
  const progFill = document.getElementById("rd-progress-fill") as HTMLElement | null;
  const timeEl   = document.getElementById("rd-time")     as HTMLElement | null;
  const player   = document.getElementById("rd-player")   as HTMLElement | null;
  const errorEl  = document.getElementById("rd-audio-error") as HTMLElement | null;

  if (!audio) return;

  // Enable controls once audio is ready
  audio.addEventListener("canplaythrough", () => {
    if (playBtn) playBtn.disabled = false;
    if (timeEl) timeEl.textContent = `0:00 / ${fmtTime(audio.duration)}`;
  });

  // Update progress and time while playing
  audio.addEventListener("timeupdate", () => {
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    if (progFill) progFill.style.width = `${pct}%`;
    if (timeEl)  timeEl.textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
  });

  // Reset play button when track ends
  audio.addEventListener("ended", () => {
    if (playBtn) playBtn.textContent = "▶";
  });

  // Graceful error state — hide player, show error banner
  audio.addEventListener("error", () => {
    if (player)  player.style.display  = "none";
    if (errorEl) errorEl.classList.add("visible");
    if (timeEl)  timeEl.textContent = "—";
  });

  // Play / Pause toggle
  if (playBtn) {
    playBtn.addEventListener("click", () => {
      if (audio.paused) {
        audio.play().catch(() => {
          if (player)  player.style.display  = "none";
          if (errorEl) errorEl.classList.add("visible");
        });
        playBtn.textContent = "⏸";
      } else {
        audio.pause();
        playBtn.textContent = "▶";
      }
    });
  }

  // Click on progress bar to seek
  if (progWrap) {
    progWrap.addEventListener("click", (e: MouseEvent) => {
      if (!audio.duration) return;
      const rect = progWrap.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });
  }

  // Start loading
  audio.load();
}

// ── Asset row entrance animations ─────────────────────────────────────────────

function animateAssets(): void {
  const rows = document.querySelectorAll<HTMLElement>(".rd-asset-row, .rd-dl-card");
  if (!rows.length) return;

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (!entry.isIntersecting) return;
      const el = entry.target as HTMLElement;
      el.style.animationDelay = `${i * 40}ms`;
      io.unobserve(el);
    });
  }, { threshold: 0.05 });

  rows.forEach(row => io.observe(row));
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initReleaseDetail(_data?: Record<string, unknown>): void {
  initAudioPlayer();
  animateAssets();
}
