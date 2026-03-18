/**
 * repo-page.ts — universal initialiser for every repo-scoped page.
 *
 * Pages that only need repo-nav hydration register `{ "page": "repo" }` (or
 * include `"repo_id"` in their page_json block).  More complex pages extend
 * this and register their own key in MusePages.
 *
 * Registered as: window.MusePages['repo']
 */

export interface RepoPageData {
  page?: string;
  repo_id?: string;
  [key: string]: unknown;
}

export function initRepoPage(data: RepoPageData): void {
  const repoId = data.repo_id;
  if (repoId && typeof window.initRepoNav === 'function') {
    window.initRepoNav(String(repoId));
  }
}
