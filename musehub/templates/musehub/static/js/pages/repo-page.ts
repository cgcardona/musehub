/**
 * repo-page.ts — universal initialiser for every repo-scoped page.
 *
 * Pages that only need repo-nav hydration register `{ "page": "repo" }` (or
 * include `"repo_id"` in their page_json block).  More complex pages extend
 * this and register their own key in MusePages.
 *
 * Also runs highlight.js over any .rh-readme-body code blocks so that fenced
 * code in READMEs gets syntax highlighting without a separate page module.
 *
 * Registered as: window.MusePages['repo']
 */

import hljs from 'highlight.js/lib/core';
import python     from 'highlight.js/lib/languages/python';
import typescript from 'highlight.js/lib/languages/typescript';
import javascript from 'highlight.js/lib/languages/javascript';
import bash       from 'highlight.js/lib/languages/bash';
import rust       from 'highlight.js/lib/languages/rust';
import go         from 'highlight.js/lib/languages/go';
import yaml       from 'highlight.js/lib/languages/yaml';
import json       from 'highlight.js/lib/languages/json';
import toml       from 'highlight.js/lib/languages/ini';  // toml ~= ini

hljs.registerLanguage('python',     python);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('bash',       bash);
hljs.registerLanguage('sh',         bash);
hljs.registerLanguage('shell',      bash);
hljs.registerLanguage('rust',       rust);
hljs.registerLanguage('go',         go);
hljs.registerLanguage('yaml',       yaml);
hljs.registerLanguage('json',       json);
hljs.registerLanguage('toml',       toml);

export interface RepoPageData {
  page?: string;
  repo_id?: string;
  clone_musehub?: string;
  clone_https?: string;
  clone_ssh?: string;
  [key: string]: unknown;
}

function initCloneTabs(urls: Record<string, string>): void {
  const input = document.getElementById('clone-input') as HTMLInputElement | null;
  document.querySelectorAll<HTMLElement>('[data-clone-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-clone-tab]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      if (input) input.value = urls[btn.dataset.cloneTab!] ?? '';
    });
  });
}

function initCopyClone(): void {
  const btn   = document.getElementById('clone-copy-btn') as HTMLButtonElement | null;
  const input = document.getElementById('clone-input') as HTMLInputElement | null;
  if (!btn || !input) return;
  btn.addEventListener('click', () => {
    navigator.clipboard.writeText(input.value).then(() => {
      const orig = btn.innerHTML;
      btn.innerHTML = '✓ Copied!';
      btn.classList.add('clone-copy-flash');
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('clone-copy-flash'); }, 1800);
    });
  });
}

function initStarToggle(): void {
  const starBtn  = document.getElementById('nav-star-btn');
  const statCard = document.getElementById('stat-stars');
  [starBtn, statCard].forEach((el) => {
    el?.addEventListener('click', (e) => {
      e.preventDefault();
      const w = window as unknown as Record<string, unknown>;
      if (typeof w.toggleStar === 'function') {
        (w.toggleStar as () => void)();
      }
    });
  });
}

function highlightReadme(): void {
  document.querySelectorAll<HTMLElement>('.rh-readme-body pre code').forEach((block) => {
    if (block.dataset['highlighted'] !== 'yes') {
      hljs.highlightElement(block);
    }
  });
}

export function initRepoPage(data: RepoPageData): void {
  const repoId = data.repo_id;
  if (repoId && typeof window.initRepoNav === 'function') {
    window.initRepoNav(String(repoId));
  }
  if (data.clone_musehub !== undefined) {
    initCloneTabs({
      musehub: data.clone_musehub ?? '',
      https:   data.clone_https   ?? '',
      ssh:     data.clone_ssh     ?? '',
    });
    initCopyClone();
  }
  initStarToggle();
  highlightReadme();
}
