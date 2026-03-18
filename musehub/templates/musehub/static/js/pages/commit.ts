/**
 * commit.ts — Commit liner-notes page module.
 *
 * The commit page has extensive client-side rendering (audio player, diff
 * viewer, cross-reference list, dimension analysis).  The bulk of that logic
 * is in the page_script block; this module performs the lightweight
 * initialisation that belongs outside the inline script:
 *
 *  - Repo nav hydration
 *  - Reactions loading
 *  - Expose helpers for the inline player onclick handlers
 *
 * Data expected in #page-data:
 *   { "page": "commit", "repo_id": "...", "commit_id": "...", "api_base": "..." }
 *
 * The heavy rendering logic (buildInlinePlayer, renderDiff, etc.) remains in
 * the page_script for now.  They read `repoId` / `commitId` from the page_data
 * JS block (const repoId = …) which is still injected by the template.
 *
 * Registered as: window.MusePages['commit']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

export interface CommitPageData extends RepoPageData {
  commit_id?: string;
}

export function initCommit(data: CommitPageData): void {
  initRepoPage(data);
  if (data.repo_id && data.commit_id && typeof window.loadReactions === 'function') {
    window.loadReactions('commit', String(data.commit_id), 'commit-reactions');
  }
}
