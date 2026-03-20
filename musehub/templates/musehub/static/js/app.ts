/**
 * app.ts — MuseHub frontend entry point.
 *
 * Bundled by esbuild into static/app.js (IIFE format).
 * Each module attaches its public API to `window` for use in
 * Jinja2 templates that call e.g. togglePlay(), saveToken(), etc.
 *
 * Page modules register on window.MusePages and are dispatched by
 * musehub.ts → dispatchPageModule() after every page load / HTMX swap.
 */

import './musehub.ts';
import './audio-player.ts';
import './piano-roll.ts';
import './midi-player.ts';

import { initRepoPage } from './pages/repo-page.ts';
import { initIssueList } from './pages/issue-list.ts';
import { initNewRepo } from './pages/new-repo.ts';
import { initPianoRollPage } from './pages/piano-roll-page.ts';
import { initListen } from './pages/listen.ts';
import { initCommitDetail } from './pages/commit-detail.ts';
import { initCommit } from './pages/commit.ts';
import { initUserProfile } from './pages/user-profile.ts';
import { initTimeline } from './pages/timeline.ts';
import { initAnalysis } from './pages/analysis.ts';
import { initInsights } from './pages/insights.ts';
import { initSearch }   from './pages/search.ts';
import { initArrange }  from './pages/arrange.ts';
import { initActivity }     from './pages/activity.ts';
import { initPRDetail }     from './pages/pr-detail.ts';
import { initCommits }      from './pages/commits.ts';
import { initIssueDetail }   from './pages/issue-detail.ts';
import { initReleaseDetail } from './pages/release-detail.ts';
import { initGraph }         from './pages/graph.ts';
import { initDomainDetail }  from './pages/domain-detail.ts';
import { initDiff }          from './pages/diff.ts';
import { initSettings }      from './pages/settings.ts';
import { initExplore }       from './pages/explore.ts';
import { initBranches }      from './pages/branches.ts';
import { initTags }          from './pages/tags.ts';
import { initSessions }      from './pages/sessions.ts';
import { initReleaseList }   from './pages/release-list.ts';
import { initBlob }          from './pages/blob.ts';
import { initScore }         from './pages/score.ts';
import { initForks }         from './pages/forks.ts';
import { initNotifications } from './pages/notifications.ts';
import { initFeed }          from './pages/feed.ts';
import { initCompare }       from './pages/compare.ts';
import { initTree }          from './pages/tree.ts';
import { initContext }       from './pages/context.ts';
import { initMcpDocs }      from './pages/mcp-docs.ts';
import { initDomains }      from './pages/domains.ts';

// Register page modules — keyed by the "page" field in the #page-data JSON.
type PageData = Record<string, unknown>;

const MusePages: Record<string, (data: PageData) => void | Promise<void>> = {
  'repo':          (d) => initRepoPage(d),
  'issue-list':    (d) => initIssueList(d),
  'new-repo':      (d) => initNewRepo(d),
  'piano-roll':    (d) => void initPianoRollPage(d),
  'listen':        (d) => void initListen(d),
  'commit-detail': () => initCommitDetail(),
  'commit':        (d) => initCommit(d),
  'user-profile':  (d) => void initUserProfile(d),
  'timeline':      () => initTimeline(),
  'analysis':      () => initAnalysis(),
  'insights':      () => initInsights(),
  'search':        () => initSearch(),
  'global-search': () => initSearch(),
  'arrange':       () => initArrange(),
  'activity':      () => initActivity(),
  'pr-detail':     () => initPRDetail(),
  'commits':       () => initCommits(),
  'issue-detail':    () => initIssueDetail(),
  'release-detail':  () => initReleaseDetail(),
  'graph':           () => initGraph(),
  'domain-detail':   (d) => initDomainDetail(d),
  'diff':            () => initDiff(),
  'settings':        () => initSettings(),
  'explore':         () => initExplore(),
  'branches':        () => initBranches(),
  'tags':            () => initTags(),
  'sessions':        () => initSessions(),
  'release-list':    () => initReleaseList(),
  'blob':            () => initBlob(),
  'score':           () => initScore(),
  'forks':           () => initForks(),
  'notifications':   () => initNotifications(),
  'feed':            () => initFeed(),
  'compare':         () => initCompare(),
  'tree':            (d) => initTree(d),
  'context':         (d) => initContext(d),
  'mcp-docs':        () => initMcpDocs(),
  'domains':         () => initDomains(),
};

// Attach to window so musehub.ts dispatchPageModule() can reach it.
(window as unknown as { MusePages: typeof MusePages }).MusePages = MusePages;
