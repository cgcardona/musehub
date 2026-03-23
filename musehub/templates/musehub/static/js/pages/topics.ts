/**
 * topics.ts — Topics index and topic-detail page module.
 *
 * Reads config from the #page-data JSON element:
 *   { page: "topics", mode: "index" | "topic", tag?, sort?, pageNum?, pageSize? }
 */

type PageData = Record<string, unknown>;

interface TopicEntry {
  name: string;
  repoCount: number;
}

interface CuratedGroup {
  label: string;
  topics: TopicEntry[];
}

interface RepoCard {
  owner: string;
  slug: string;
  name: string;
  description: string | null;
  starCount: number;
  tags: string[];
  keySignature: string | null;
  tempoBpm: number | null;
  createdAt: string | null;
}

interface TopicsIndexData {
  allTopics: TopicEntry[];
  curatedGroups: CuratedGroup[];
}

interface TopicDetailData {
  repos: RepoCard[];
  total: number;
  page: number;
  pageSize: number;
}

function esc(s: string | null | undefined): string {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtRelative(ts: string | null | undefined): string {
  if (!ts) return '';
  const d    = new Date(ts);
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function repoCardHtml(repo: RepoCard): string {
  const tagsHtml = (repo.tags ?? []).slice(0, 4).map(t =>
    `<a href="/topics/${encodeURIComponent(t)}" class="badge badge-tag" style="
      display:inline-block;padding:2px 8px;margin:2px 2px 0 0;border-radius:12px;
      font-size:11px;background:#1f6feb22;color:#58a6ff;
      border:1px solid #1f6feb55;text-decoration:none">#${esc(t)}</a>`,
  ).join('');

  const meta: string[] = [];
  if (repo.keySignature) meta.push(`🎵 ${esc(repo.keySignature)}`);
  if (repo.tempoBpm) meta.push(`♩ ${repo.tempoBpm} BPM`);

  return `
  <div class="card" style="display:flex;flex-direction:column;gap:6px;padding:14px">
    <div>
      <a href="/${esc(repo.owner)}/${esc(repo.slug)}"
         style="font-weight:600;font-size:15px">${esc(repo.owner)}/${esc(repo.name)}</a>
    </div>
    ${repo.description ? `<p style="font-size:13px;color:#8b949e;margin:0">${esc(repo.description)}</p>` : ''}
    <div>${tagsHtml}</div>
    <div style="display:flex;gap:12px;font-size:12px;color:#8b949e;margin-top:2px">
      <span>⭐ ${repo.starCount ?? 0}</span>
      ${meta.map(m => `<span>${m}</span>`).join('')}
      <span style="margin-left:auto">${fmtRelative(repo.createdAt)}</span>
    </div>
  </div>`;
}

function renderTopicsIndex(data: TopicsIndexData): void {
  const all    = data.allTopics ?? [];
  const groups = data.curatedGroups ?? [];

  function renderGrid(topics: TopicEntry[]): string {
    if (!topics.length) return '<p style="color:#8b949e;font-size:14px">No topics found.</p>';
    return `<div style="display:flex;flex-wrap:wrap;gap:8px">` +
      topics.map(t => `
        <a href="/topics/${encodeURIComponent(t.name)}"
           style="display:flex;align-items:center;gap:6px;padding:6px 12px;
                  border-radius:20px;border:1px solid #30363d;background:#161b22;
                  text-decoration:none;color:#c9d1d9;font-size:13px">
          <span style="font-weight:600">#${esc(t.name)}</span>
          <span style="background:#21262d;padding:1px 6px;border-radius:10px;
                       font-size:11px;color:#8b949e">${t.repoCount}</span>
        </a>`).join('') +
      `</div>`;
  }

  function renderCuratedGroups(groupList: CuratedGroup[]): string {
    return groupList.map(g => {
      const visible = g.topics.filter(t => t.repoCount > 0);
      if (!visible.length) return '';
      return `
        <div style="margin-bottom:20px">
          <h3 style="font-size:14px;color:#8b949e;margin:0 0 10px;font-weight:600;
                     text-transform:uppercase;letter-spacing:0.5px">${esc(g.label)}</h3>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            ${visible.map(t => `
              <a href="/topics/${encodeURIComponent(t.name)}"
                 style="padding:4px 10px;border-radius:14px;background:#21262d;
                        border:1px solid #30363d;font-size:12px;color:#c9d1d9;
                        text-decoration:none">
                #${esc(t.name)}
                <span style="color:#8b949e;font-size:11px">${t.repoCount}</span>
              </a>`).join('')}
          </div>
        </div>`;
    }).join('');
  }

  const contentEl = document.getElementById('content');
  if (!contentEl) return;

  let filtered = [...all];

  function applyFilter(): void {
    const inp = document.getElementById('topic-filter') as HTMLInputElement | null;
    const filterText = inp ? inp.value.toLowerCase().trim() : '';
    filtered = filterText ? all.filter(t => t.name.includes(filterText)) : [...all];
    const gridEl = document.getElementById('topic-grid');
    if (gridEl) gridEl.innerHTML = renderGrid(filtered);
  }

  (window as unknown as Record<string, unknown>)['_topicsApplyFilter'] = applyFilter;

  contentEl.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 280px;gap:24px;align-items:start">
      <div>
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
          <h1 style="margin:0;font-size:22px">🏷️ Topics</h1>
          <span style="color:#8b949e;font-size:14px">${all.length} topic${all.length !== 1 ? 's' : ''}</span>
        </div>
        <div style="margin-bottom:16px">
          <input id="topic-filter" type="text" placeholder="Filter topics…"
                 style="width:100%;max-width:400px;padding:8px 12px;
                        background:#0d1117;color:#c9d1d9;border:1px solid #30363d;
                        border-radius:6px;font-size:14px" />
        </div>
        <div id="topic-grid">${renderGrid(all)}</div>
      </div>
      <div>
        <div class="card" style="padding:16px">
          <h2 style="font-size:14px;margin:0 0 16px;color:#e6edf3">Browse by category</h2>
          ${renderCuratedGroups(groups)}
          ${!groups.length ? '<p style="color:#8b949e;font-size:13px">No curated groups available.</p>' : ''}
        </div>
      </div>
    </div>`;

  const filterInput = document.getElementById('topic-filter');
  if (filterInput) filterInput.addEventListener('input', applyFilter);
}

function renderTopicDetail(
  tag: string,
  data: TopicDetailData,
  sort: string,
  page: number,
  pageSize: number,
): void {
  const repos    = data.repos   ?? [];
  const total    = data.total   ?? 0;
  const curPage  = data.page    ?? page;
  const ps       = data.pageSize ?? pageSize;
  const featured = repos.slice(0, 3);

  function featuredCardHtml(repo: RepoCard): string {
    return `
      <div class="card" style="padding:16px;border:1px solid #30363d;
           background:linear-gradient(135deg,#161b22 0%,#0d1117 100%)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <a href="/${esc(repo.owner)}/${esc(repo.slug)}"
             style="font-weight:700;font-size:16px">${esc(repo.owner)}/${esc(repo.name)}</a>
          <span style="background:#21262d;padding:2px 8px;border-radius:10px;
                       font-size:12px;color:#f0b429">⭐ ${repo.starCount ?? 0}</span>
        </div>
        ${repo.description
          ? `<p style="font-size:13px;color:#8b949e;margin:0 0 10px">${esc(repo.description)}</p>`
          : ''}
        <div style="font-size:12px;color:#8b949e">
          ${repo.keySignature ? `🎵 ${esc(repo.keySignature)}` : ''}
          ${repo.tempoBpm ? ` &bull; ♩ ${repo.tempoBpm} BPM` : ''}
        </div>
      </div>`;
  }

  function sortUrl(newSort: string): string {
    return `/topics/${encodeURIComponent(tag)}?sort=${newSort}&page=1`;
  }
  function pageUrl(newPage: number): string {
    return `/topics/${encodeURIComponent(tag)}?sort=${sort}&page=${newPage}`;
  }

  const totalPages = Math.ceil(total / ps);
  const pager = totalPages > 1 ? `
    <div style="display:flex;gap:8px;justify-content:center;margin-top:16px">
      ${curPage > 1
        ? `<a href="${pageUrl(curPage - 1)}" class="btn btn-secondary">&larr; Prev</a>` : ''}
      <span style="padding:6px 12px;font-size:13px;color:#8b949e">
        Page ${curPage} of ${totalPages}
      </span>
      ${curPage < totalPages
        ? `<a href="${pageUrl(curPage + 1)}" class="btn btn-secondary">Next &rarr;</a>` : ''}
    </div>` : '';

  const contentEl = document.getElementById('content');
  if (!contentEl) return;
  contentEl.innerHTML = `
    <div style="margin-bottom:24px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <h1 style="margin:0;font-size:24px">
          <a href="/topics" style="color:#8b949e;text-decoration:none">Topics</a>
          / <span style="color:#58a6ff">#${esc(tag)}</span>
        </h1>
        <span style="color:#8b949e;font-size:14px">${total} repo${total !== 1 ? 's' : ''}</span>
      </div>
    </div>
    ${featured.length ? `
      <div style="margin-bottom:24px">
        <h2 style="font-size:15px;color:#8b949e;margin:0 0 12px;text-transform:uppercase;
                   letter-spacing:0.5px;font-weight:600">⭐ Featured</h2>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px">
          ${featured.map(featuredCardHtml).join('')}
        </div>
      </div>` : ''}
    <div>
      <div style="display:flex;align-items:center;justify-content:space-between;
                  margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <h2 style="font-size:15px;margin:0;color:#8b949e;text-transform:uppercase;
                   letter-spacing:0.5px;font-weight:600">All Repositories</h2>
        <div style="display:flex;gap:6px;align-items:center">
          <span style="font-size:13px;color:#8b949e">Sort:</span>
          <a href="${sortUrl('stars')}"
             class="btn ${sort === 'stars' ? 'btn-primary' : 'btn-secondary'}"
             style="font-size:12px;padding:4px 10px">Most starred</a>
          <a href="${sortUrl('updated')}"
             class="btn ${sort === 'updated' ? 'btn-primary' : 'btn-secondary'}"
             style="font-size:12px;padding:4px 10px">Recently updated</a>
        </div>
      </div>
      ${repos.length === 0
        ? `<p style="color:#8b949e">No public repositories tagged with <strong>#${esc(tag)}</strong> yet.</p>`
        : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px">
             ${repos.map(repoCardHtml).join('')}
           </div>`}
      ${pager}
    </div>`;
}

async function uiFetch(url: string): Promise<unknown> {
  const headers: Record<string, string> = {};
  if (window.authHeaders) {
    const h = window.authHeaders() as Record<string, string>;
    Object.assign(headers, h);
  }
  const res = await fetch(url, { headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(res.status + ': ' + body);
  }
  return res.json() as Promise<unknown>;
}

export function initTopics(data: PageData): void {
  const mode     = String(data['mode'] ?? 'index');
  const tag      = String(data['tag'] ?? '');
  const sort     = String(data['sort'] ?? 'stars');
  const pageNum  = Number(data['pageNum'] ?? 1);
  const pageSize = Number(data['pageSize'] ?? 20);

  void (async () => {
    try {
      if (mode === 'index') {
        const indexData = (await uiFetch('/topics?format=json')) as TopicsIndexData;
        renderTopicsIndex(indexData);
      } else {
        const params = new URLSearchParams({
          format: 'json',
          sort,
          page: String(pageNum),
          page_size: String(pageSize),
        });
        const detailData = (await uiFetch(
          `/topics/${encodeURIComponent(tag)}?${params.toString()}`,
        )) as TopicDetailData;
        renderTopicDetail(tag, detailData, sort, pageNum, pageSize);
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      const contentEl = document.getElementById('content');
      if (contentEl) {
        contentEl.innerHTML = `<p class="error">&#10005; Failed to load topics: ${esc(String(err.message ?? e))}</p>`;
      }
    }
  })();
}
