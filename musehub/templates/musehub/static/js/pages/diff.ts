/**
 * diff.ts — Musical diff page for a single commit.
 *
 * Config is read from window.__diffCfg (set by the page_data block).
 * Registered as: window.MusePages['diff']
 */

// ── Types ─────────────────────────────────────────────────────────────────────

interface DiffCfg {
  repoId:   string;
  commitId: string;
  base:     string;
}

interface CommitData {
  commitId:  string;
  message:   string;
  author:    string;
  timestamp: string;
  branch:    string;
  parentIds?: string[];
}

interface CommitObj { objectId: string; path: string; }

declare global {
  interface Window {
    __diffCfg?:  DiffCfg;
    escHtml:     (s: string) => string;
    apiFetch:    (path: string, init?: RequestInit) => Promise<unknown>;
    authHeaders: () => Record<string, string>;
    parseCommitMessage: (msg: string) => { type: string; scope: string; subject: string };
    parseCommitMeta:    (msg: string) => Record<string, string>;
    initRepoNav?: (repoId: string) => void;
    queueAudio?:  (url: string, name: string, repo: string) => void;
    shortSha?:    (sha: string) => string;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s: string): string { return window.escHtml(s); }
function apiFetch(path: string): Promise<unknown> { return window.apiFetch(path); }

function shortSha(sha: string): string {
  return typeof window.shortSha === 'function'
    ? window.shortSha(sha)
    : sha.substring(0, 8);
}

function metaDiff(a: string | null | undefined, b: string | null | undefined, label: string, icon: string): string {
  if (!a && !b) return '';
  if (a === b) return `
    <div class="meta-item">
      <span class="meta-label">${icon} ${label}</span>
      <span class="meta-value text-sm">${esc(a!)}</span>
    </div>`;
  return `
    <div class="meta-item">
      <span class="meta-label">${icon} ${label}</span>
      <span class="meta-value text-sm">
        ${a ? `<span style="text-decoration:line-through;color:var(--color-danger)">${esc(a)}</span> ` : ''}
        ${b ? `<span style="color:var(--color-success)">${esc(b)}</span>` : ''}
      </span>
    </div>`;
}

function trackDiff(parentObjects: CommitObj[], childObjects: CommitObj[]): string {
  const ext       = (p: string) => p.split('.').pop()!.toLowerCase();
  const trackName = (p: string) => p.split('/').pop()!.replace(/\.[^.]+$/, '');

  const parentPaths = new Set((parentObjects || []).map(o => o.path));
  const childPaths  = new Set((childObjects  || []).map(o => o.path));

  const added   = (childObjects  || []).filter(o => !parentPaths.has(o.path));
  const removed = (parentObjects || []).filter(o => !childPaths.has(o.path));
  const changed = (childObjects  || []).filter(o =>  parentPaths.has(o.path));

  const rows: string[] = [];

  removed.forEach(o => rows.push(`
    <div class="diff-track-row diff-track-removed">
      <span class="diff-sign diff-sign-remove">−</span>
      <span class="text-sm">${esc(trackName(o.path))}</span>
      <span class="text-xs text-muted">.${esc(ext(o.path))} &bull; removed</span>
    </div>`));

  added.forEach(o => rows.push(`
    <div class="diff-track-row diff-track-added">
      <span class="diff-sign diff-sign-add">+</span>
      <span class="text-sm">${esc(trackName(o.path))}</span>
      <span class="text-xs text-muted">.${esc(ext(o.path))} &bull; added</span>
    </div>`));

  changed.forEach(o => rows.push(`
    <div class="diff-track-row diff-track-changed">
      <span class="diff-sign diff-sign-change">~</span>
      <span class="text-sm">${esc(trackName(o.path))}</span>
      <span class="text-xs text-muted">.${esc(ext(o.path))} &bull; modified</span>
    </div>`));

  if (rows.length === 0)
    return '<p class="text-muted text-sm">No artifact changes detected.</p>';

  return rows.join('');
}

function seededWave(seed: number, color: string): string {
  let x = seed;
  const bars = Array.from({ length: 64 }, () => {
    x = (x * 1103515245 + 12345) & 0x7fffffff;
    const h = 10 + (x % 80);
    return `<div style="flex:1;background:${color};opacity:0.7;border-radius:1px 1px 0 0;min-height:4px;height:${h}%"></div>`;
  }).join('');
  return `<div style="display:flex;align-items:flex-end;gap:2px;height:80px;background:var(--bg-base);border-radius:var(--radius-sm);padding:var(--space-2)">${bars}</div>`;
}

// ── Audio preview handlers ────────────────────────────────────────────────────

let _diffCfg: DiffCfg;

async function loadCommitAudio(cid: string): Promise<void> {
  try {
    const data    = await apiFetch('/repos/' + _diffCfg.repoId + '/objects') as { objects?: CommitObj[] };
    const objects = data.objects || [];
    const audioObj = objects.find(o => {
      const ext = o.path.split('.').pop()!.toLowerCase();
      return ['mp3','ogg','wav','flac'].includes(ext);
    });
    if (audioObj) {
      const url = `/api/v1/repos/${_diffCfg.repoId}/objects/${audioObj.objectId}/content`;
      if (typeof window.queueAudio === 'function') window.queueAudio(url, shortSha(cid), _diffCfg.repoId);
    } else {
      alert('No audio artifacts found for this commit.');
    }
  } catch(e) {
    alert('Could not load audio: ' + (e as Error).message);
  }
}

function setupEventDelegation(): void {
  document.addEventListener('click', e => {
    const target = (e.target as Element).closest<HTMLElement>('[data-action]');
    if (!target) return;
    switch (target.dataset.action) {
      case 'load-commit-audio':
        void loadCommitAudio(target.dataset.commitId ?? '');
        break;
      case 'load-parent-audio':
        void loadCommitAudio(target.dataset.commitId ?? '');
        break;
    }
  });
}

// ── Main load ─────────────────────────────────────────────────────────────────

async function load(): Promise<void> {
  if (typeof window.initRepoNav === 'function') window.initRepoNav(_diffCfg.repoId);
  try {
    const commitsData = await apiFetch('/repos/' + _diffCfg.repoId + '/commits?limit=200') as { commits?: CommitData[] };
    const commits  = commitsData.commits || [];
    const commit   = commits.find(c => c.commitId === _diffCfg.commitId);

    if (!commit) {
      const content = document.getElementById('content');
      if (content) content.innerHTML = '<p class="error">Commit not found.</p>';
      return;
    }

    const parentId = (commit.parentIds || [])[0];
    const parent   = parentId ? commits.find(c => c.commitId === parentId) : null;

    const objectsData = await apiFetch('/repos/' + _diffCfg.repoId + '/objects') as { objects?: CommitObj[] };
    const allObjects  = objectsData.objects || [];

    const parsedChild  = window.parseCommitMessage(commit.message);
    const parsedParent = parent ? window.parseCommitMessage(parent.message) : null;

    const metaChild  = window.parseCommitMeta(commit.message);
    const metaParent = parent ? window.parseCommitMeta(parent.message) : {} as Record<string, string>;

    const seed1 = parseInt(parentId ? parentId.substring(0, 8) : '0', 16) || 12345;
    const seed2 = parseInt(_diffCfg.commitId.substring(0, 8), 16) || 54321;

    const content = document.getElementById('content');
    if (content) content.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-4)">
          <a href="${_diffCfg.base}/commits/${_diffCfg.commitId}" class="btn btn-ghost btn-sm">&larr; Back to commit</a>
          <h2 style="margin:0">Musical Diff</h2>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:var(--space-4);align-items:start;margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            ${parent ? `
            <a href="${_diffCfg.base}/commits/${parentId}" class="text-mono text-sm">${shortSha(parentId!)}</a>
            <div class="text-sm text-muted" style="margin-top:4px">${esc(parsedParent!.subject || parent.message)}</div>
            ` : '<span class="text-muted text-sm">Root commit — no parent</span>'}
          </div>
          <div style="font-size:24px;color:var(--text-muted);align-self:center">→</div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <a href="${_diffCfg.base}/commits/${_diffCfg.commitId}" class="text-mono text-sm">${shortSha(_diffCfg.commitId)}</a>
            <div class="text-sm text-muted" style="margin-top:4px">${esc(parsedChild.subject || commit.message)}</div>
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">Musical Properties</h3>
        <div class="meta-row" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));margin-bottom:var(--space-4)">
          ${metaDiff(metaParent['key'], metaChild['key'], 'Key', '&#9837;')}
          ${metaDiff(metaParent['tempo'] || metaParent['bpm'], metaChild['tempo'] || metaChild['bpm'], 'BPM', '&#9201;')}
          ${metaDiff(metaParent['section'], metaChild['section'], 'Section', '&#127926;')}
          ${metaDiff(parent ? parent.branch : null, commit.branch, 'Branch', '&#9900;')}
        </div>

        <h3 style="margin-bottom:var(--space-3)">Artifact Changes</h3>
        <div style="margin-bottom:var(--space-4)">
          ${parent
            ? trackDiff([], allObjects)
            : '<p class="text-muted text-sm">This is the root commit — all artifacts are new.</p>'}
        </div>

        <h3 style="margin-bottom:var(--space-3)">Audio Waveform Comparison</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-bottom:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent ${parent ? shortSha(parentId!) : '—'}</div>
            ${seededWave(seed1, 'var(--color-accent)')}
            ${parent
              ? `<button class="btn btn-secondary btn-sm" style="margin-top:var(--space-2);width:100%" data-action="load-parent-audio" data-commit-id="${esc(parentId!)}">&#9654; Preview</button>`
              : '<p class="text-muted text-sm">No parent</p>'}
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit ${shortSha(_diffCfg.commitId)}</div>
            ${seededWave(seed2, 'var(--color-success)')}
            <button class="btn btn-secondary btn-sm" style="margin-top:var(--space-2);width:100%" data-action="load-commit-audio" data-commit-id="${esc(_diffCfg.commitId)}">&#9654; Preview</button>
          </div>
        </div>

        <h3 style="margin-bottom:var(--space-3)">Commit Messages</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">Parent</div>
            <pre style="font-size:12px">${parent ? esc(parent.message) : 'None'}</pre>
          </div>
          <div>
            <div class="text-xs text-muted" style="margin-bottom:var(--space-1)">This commit</div>
            <pre style="font-size:12px">${esc(commit.message)}</pre>
          </div>
        </div>
      </div>`;
  } catch(e) {
    const err = e as Error;
    if (err.message !== 'auth') {
      const content = document.getElementById('content');
      if (content) content.innerHTML = `<p class="error">&#10005; ${esc(err.message)}</p>`;
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initDiff(): void {
  const cfg = window.__diffCfg;
  if (!cfg) return;
  _diffCfg = cfg;
  setupEventDelegation();
  void load();
}
