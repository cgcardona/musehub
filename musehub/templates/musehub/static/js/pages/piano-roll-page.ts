/**
 * piano-roll-page.ts — Piano roll viewer page module.
 *
 * Wires transport controls (play / stop) to the PianoRoll global loaded by
 * piano-roll.ts.  Falls back to a legacy loader if PianoRoll.init is absent.
 *
 * Data expected in #page-data:
 *   { "page": "piano-roll", "repo_id": "...", "ref": "...", "path": "..." }
 *
 * Registered as: window.MusePages['piano-roll']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

export interface PianoRollPageData extends RepoPageData {
  ref?: string;
  path?: string;
  midi_url?: string;
}

function attachTransportControls(): void {
  const playBtn = document.getElementById('play-btn');
  const stopBtn = document.getElementById('stop-btn');

  if (playBtn) {
    playBtn.addEventListener('click', () => {
      const pr = (window as unknown as { PianoRoll?: { play?: () => void } }).PianoRoll;
      if (pr?.play) pr.play();
    });
  }
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      const pr = (window as unknown as { PianoRoll?: { stop?: () => void } }).PianoRoll;
      if (pr?.stop) pr.stop();
    });
  }
}

async function legacyLoad(repoId: string): Promise<void> {
  const canvas = document.getElementById('piano-canvas') as HTMLCanvasElement | null;
  if (!canvas) return;

  const pr = (window as unknown as { PianoRoll?: { init?: unknown } }).PianoRoll;
  if (pr?.init) return; // New-style self-init handles it

  const midiUrl  = canvas.dataset.midiUrl;
  const rollPath = canvas.dataset.path ?? null;
  const apiFetch = window.apiFetch;
  if (!apiFetch) return;

  try {
    const outer = document.getElementById('piano-roll-outer');
    if (rollPath) {
      const objData = await apiFetch('/repos/' + encodeURIComponent(repoId) + '/objects?limit=500') as { objects?: Array<{ path: string; objectId: string }> };
      const obj = (objData.objects ?? []).find((o) => o.path === rollPath);
      if (obj && typeof window.renderFromObjectId === 'function') {
        window.renderFromObjectId(repoId, obj.objectId, outer);
      }
    } else if (midiUrl) {
      if (typeof window.renderFromUrl === 'function') {
        window.renderFromUrl(midiUrl, outer);
      }
    }
  } catch (_) { /* silent */ }
}

export async function initPianoRollPage(data: PianoRollPageData): Promise<void> {
  initRepoPage(data);
  attachTransportControls();
  if (data.repo_id) await legacyLoad(String(data.repo_id));
}
