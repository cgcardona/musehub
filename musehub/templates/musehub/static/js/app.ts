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
};

// Attach to window so musehub.ts dispatchPageModule() can reach it.
(window as unknown as { MusePages: typeof MusePages }).MusePages = MusePages;
