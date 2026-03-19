/**
 * feed.ts — Activity feed page module.
 *
 * Responsibilities:
 *  1. Fetch /api/v1/feed and render event cards into #content.
 *  2. Mark single notifications as read via POST /notifications/{id}/read.
 *  3. Mark all notifications as read via POST /notifications/read-all.
 *  4. Update the nav badge count in-place without a page reload.
 *
 * Registered as: window.MusePages['feed']
 */

declare global {
  interface Window {
    escHtml:     (s: unknown) => string;
    fmtRelative: (iso: string | null | undefined) => string;
    apiFetch:    (path: string, init?: RequestInit) => Promise<unknown>;
    getToken:    () => string;
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface FeedItem {
  notif_id:   string;
  event_type: string;
  actor:      string;
  repo_id?:   string;
  created_at: string;
  is_read:    boolean;
}

interface EventMeta {
  icon:     string;
  sentence: (actor: string, repoId: string) => string;
}

// ── Actor helpers ─────────────────────────────────────────────────────────────

function actorHsl(actor: string): string {
  let hash = 0;
  for (let i = 0; i < actor.length; i++) {
    hash = actor.charCodeAt(i) + ((hash << 5) - hash);
  }
  return `hsl(${Math.abs(hash) % 360},50%,38%)`;
}

function actorAvatar(actor: string): string {
  const bg      = actorHsl(actor);
  const initial = window.escHtml((actor || '?').charAt(0).toUpperCase());
  return `<div class="comment-avatar" style="background:${bg};color:#e6edf3;font-weight:700;font-size:14px;border:none">${initial}</div>`;
}

function actorLink(actor: string): string {
  return `<a href="/${encodeURIComponent(actor)}" style="color:var(--text-primary);font-weight:600">${window.escHtml(actor)}</a>`;
}

function repoLink(repoId: string): string {
  if (!repoId) return '';
  const parts = repoId.split('/');
  const label = parts.length >= 2 ? window.escHtml(parts[1]) : window.escHtml(repoId);
  return `<a href="/${encodeURIComponent(repoId)}" style="color:var(--color-accent)">${label}</a>`;
}

// ── Event metadata ────────────────────────────────────────────────────────────

const EVENT_META: Record<string, EventMeta> = {
  comment:      { icon: '🗨️',  sentence: (a, r) => `${actorLink(a)} commented on ${repoLink(r)}` },
  mention:      { icon: '💬',  sentence: (a, r) => `${actorLink(a)} mentioned you in ${repoLink(r)}` },
  pr_opened:    { icon: '🔀',  sentence: (a, r) => `${actorLink(a)} opened a PR in ${repoLink(r)}` },
  pr_merged:    { icon: '✅',  sentence: (a, r) => `${actorLink(a)} merged a PR in ${repoLink(r)}` },
  issue_opened: { icon: '🐛',  sentence: (a, r) => `${actorLink(a)} opened an issue in ${repoLink(r)}` },
  issue_closed: { icon: '✔️', sentence: (a, r) => `${actorLink(a)} closed an issue in ${repoLink(r)}` },
  new_commit:   { icon: '🎵',  sentence: (a, r) => `${actorLink(a)} committed to ${repoLink(r)}` },
  new_follower: { icon: '👤',  sentence: (a)    => `${actorLink(a)} followed you` },
};

// ── Card renderer ─────────────────────────────────────────────────────────────

function eventCard(item: FeedItem): string {
  const meta      = EVENT_META[item.event_type] ?? { icon: '•', sentence: (a: string) => actorLink(a) };
  const icon      = meta.icon;
  const sentence  = meta.sentence(item.actor, item.repo_id ?? '');
  const timestamp = window.fmtRelative(item.created_at);
  const isUnread  = !item.is_read;

  const unreadStyle = isUnread
    ? 'border-left:3px solid var(--color-accent);padding-left:calc(var(--space-3) - 3px);'
    : 'border-left:3px solid transparent;padding-left:calc(var(--space-3) - 3px);opacity:0.75;';

  const markReadBtn = isUnread
    ? `<button
         class="mark-read-btn"
         data-notif-id="${window.escHtml(item.notif_id)}"
         data-action="mark-read"
         title="Mark as read"
         style="background:none;border:1px solid var(--border-color);border-radius:50%;width:22px;height:22px;cursor:pointer;color:var(--text-muted);font-size:12px;line-height:1;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;margin-left:var(--space-2)"
       >&#10003;</button>`
    : '';

  return `
    <div class="comment-item" data-notif-id="${window.escHtml(item.notif_id)}" style="${unreadStyle}">
      ${actorAvatar(item.actor)}
      <div class="comment-body" style="flex:1;min-width:0">
        <div class="comment-meta" style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap">
          <span style="font-size:16px;line-height:1">${icon}</span>
          <span>${sentence}</span>
          <span style="margin-left:auto;white-space:nowrap;display:flex;align-items:center;gap:var(--space-2)">
            ${window.escHtml(timestamp)}
            ${markReadBtn}
          </span>
        </div>
        ${isUnread ? '<div class="unread-dot" style="width:6px;height:6px;border-radius:50%;background:var(--color-accent);display:inline-block;margin-top:var(--space-1)"></div>' : ''}
      </div>
    </div>`;
}

// ── Mark-read helpers ─────────────────────────────────────────────────────────

function decrementNavBadge(): void {
  const badge = document.getElementById('nav-notif-badge');
  if (!badge) return;
  const current = parseInt(badge.textContent ?? '', 10);
  if (isNaN(current) || current <= 1) {
    badge.style.display = 'none';
  } else {
    badge.textContent = String(current - 1);
  }
}

async function markOneRead(btn: HTMLElement): Promise<void> {
  const notifId = btn.dataset.notifId;
  if (!notifId) return;
  try {
    await window.apiFetch('/notifications/' + encodeURIComponent(notifId) + '/read', { method: 'POST' });
    const card = document.querySelector<HTMLElement>(`.comment-item[data-notif-id="${CSS.escape(notifId)}"]`);
    if (card) {
      card.style.borderLeft = '3px solid transparent';
      card.style.opacity    = '0.75';
      card.querySelector('.unread-dot')?.remove();
    }
    btn.remove();
    decrementNavBadge();
  } catch (e) {
    if ((e as Error).message !== 'auth') btn.style.color = 'var(--color-danger)';
  }
}

async function markAllRead(): Promise<void> {
  const markAllBtn = document.getElementById('mark-all-read-btn') as HTMLButtonElement | null;
  if (markAllBtn) markAllBtn.disabled = true;
  try {
    await window.apiFetch('/notifications/read-all', { method: 'POST' });
    document.querySelectorAll<HTMLElement>('.comment-item').forEach(card => {
      card.style.borderLeft = '3px solid transparent';
      card.style.opacity    = '0.75';
      card.querySelector('.unread-dot')?.remove();
      card.querySelector('.mark-read-btn')?.remove();
    });
    const badge = document.getElementById('nav-notif-badge');
    if (badge) badge.style.display = 'none';
    markAllBtn?.remove();
  } catch (e) {
    if (markAllBtn) markAllBtn.disabled = false;
    if ((e as Error).message !== 'auth') {
      const err = document.getElementById('feed-error');
      if (err) err.textContent = 'Could not mark all as read: ' + (e as Error).message;
    }
  }
}

// ── Event delegation ──────────────────────────────────────────────────────────

function bindActions(): void {
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!el) return;
    if (el.dataset.action === 'mark-read') {
      void markOneRead(el);
    } else if (el.dataset.action === 'mark-all-read') {
      void markAllRead();
    }
  });
}

// ── Main load ─────────────────────────────────────────────────────────────────

async function load(): Promise<void> {
  const contentEl = document.getElementById('content');
  if (!contentEl) return;

  try {
    const items = ((await window.apiFetch('/feed?limit=50')) ?? []) as FeedItem[];

    if (items.length === 0) {
      contentEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">&#127926;</div>
          <p class="empty-title">Your feed is empty</p>
          <p class="empty-desc">Follow musicians and watch repos to see their activity here.</p>
          <a href="/explore" class="btn btn-primary">Explore repos</a>
        </div>`;
      return;
    }

    const hasUnread  = items.some(item => !item.is_read);
    const markAllHtml = hasUnread && window.getToken()
      ? `<button
           id="mark-all-read-btn"
           data-action="mark-all-read"
           class="btn btn-secondary"
           style="font-size:12px;padding:4px 10px"
         >&#10003; Mark all as read</button>`
      : '';

    contentEl.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4)">
        <h1 style="margin:0">Activity Feed</h1>
        ${markAllHtml}
      </div>
      <p id="feed-error" style="color:var(--color-danger);font-size:13px"></p>
      <div class="card" style="padding:0">
        ${items.map(eventCard).join('')}
      </div>`;
  } catch (e) {
    if ((e as Error).message !== 'auth' && contentEl) {
      contentEl.innerHTML = '<p class="error">&#10005; ' + window.escHtml((e as Error).message) + '</p>';
    }
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function initFeed(): void {
  bindActions();
  void load();
}
