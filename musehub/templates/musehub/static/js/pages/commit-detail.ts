/**
 * commit-detail.ts — Commit detail page module.
 *
 * The commit detail page is server-rendered (SSR).
 * This module handles:
 *  - Repo nav hydration
 *  - Loading reactions for the commit
 *
 * Data expected in #page-data:
 *   { "page": "commit-detail", "repo_id": "...", "commit_sha": "..." }
 *
 * Registered as: window.MusePages['commit-detail']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

export interface CommitDetailData extends RepoPageData {
  commit_sha?: string;
}

export function initCommitDetail(data: CommitDetailData): void {
  initRepoPage(data);
  if (data.repo_id && data.commit_sha && typeof window.loadReactions === 'function') {
    window.loadReactions('commit', String(data.commit_sha), 'commit-reactions');
  }
}
