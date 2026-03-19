/**
 * issue-list.ts — MuseHub issue list page module.
 *
 * Handles:
 *  - Body preview helper
 *  - Issue template picker (pre-fills new-issue form)
 *  - Bulk selection toolbar
 *  - Repo nav hydration
 *
 * Data expected in #page-data:
 *   { "page": "issue-list", "repo_id": "..." }
 *
 * Registered as: window.MusePages['issue-list']
 */

import { initRepoPage, type RepoPageData } from './repo-page.ts';

export function bodyPreview(text: string, maxLen = 120): string {
  if (!text) return '';
  const stripped = text.replace(/[#*`>\-_]/g, '').trim();
  return stripped.length > maxLen ? stripped.slice(0, maxLen) + '…' : stripped;
}

const ISSUE_TEMPLATES = [
  { id: 'blank', icon: '📝', title: 'Blank Issue', description: 'Start with a clean slate.', body: '' },
  { id: 'bug', icon: '🐛', title: 'Bug Report', description: "Something isn't working as expected.", body: '## What happened?\n\n\n## Steps to reproduce\n\n1. \n2. \n3. \n\n## Expected behaviour\n\n\n## Actual behaviour\n\n' },
  { id: 'feature', icon: '✨', title: 'Feature Request', description: 'Suggest a new musical idea or capability.', body: '## Summary\n\n\n## Motivation\n\n\n## Proposed approach\n\n' },
  { id: 'arrangement', icon: '🎵', title: 'Arrangement Issue', description: 'Track needs musical arrangement work.', body: '## Track / Section\n\n\n## Current arrangement\n\n\n## Desired arrangement\n\n\n## Musical context\n\n' },
  { id: 'theory', icon: '🎼', title: 'Music Theory', description: 'Related to harmony, rhythm, or theory decisions.', body: '## Theory concern\n\n\n## Affected section / instrument\n\n\n## Suggested resolution\n\n' },
];

const selectedIssues = new Set<string>();

export function showTemplatePicker(): void {
  const panel = document.getElementById('create-issue-panel');
  const picker = document.getElementById('template-picker');
  if (!panel || !picker) return;
  picker.style.display = '';
  panel.style.display = 'none';
}

export function selectTemplate(tplId: string): void {
  const tpl = ISSUE_TEMPLATES.find((t) => t.id === tplId);
  if (!tpl) return;
  const bodyEl = document.getElementById('issue-body') as HTMLTextAreaElement | null;
  if (bodyEl) bodyEl.value = tpl.body;
  const picker = document.getElementById('template-picker');
  if (picker) picker.style.display = 'none';
  const panel = document.getElementById('create-issue-panel');
  if (panel) panel.style.display = '';
  const titleEl = document.getElementById('issue-title') as HTMLInputElement | null;
  if (titleEl) titleEl.focus();
}

export function toggleIssueSelect(issueId: string, checked: boolean): void {
  if (checked) { selectedIssues.add(issueId); } else { selectedIssues.delete(issueId); }
  updateBulkToolbar();
}

function updateBulkToolbar(): void {
  const toolbar = document.getElementById('bulk-toolbar');
  const countEl = document.getElementById('bulk-count');
  if (!toolbar || !countEl) return;
  const n = selectedIssues.size;
  if (n > 0) {
    toolbar.classList.add('visible');
    countEl.textContent = n === 1 ? '1 issue selected' : `${n} issues selected`;
  } else {
    toolbar.classList.remove('visible');
  }
}

export function deselectAll(): void {
  selectedIssues.clear();
  document.querySelectorAll('.issue-row-check').forEach((c) => { (c as HTMLInputElement).checked = false; });
  updateBulkToolbar();
}

export function bulkClose(): void { if (selectedIssues.size > 0 && confirm(`Close ${selectedIssues.size} issue(s)?`)) location.reload(); }
export function bulkReopen(): void { if (selectedIssues.size > 0 && confirm(`Reopen ${selectedIssues.size} issue(s)?`)) location.reload(); }
export function bulkAssignLabel(): void { const s = document.getElementById('bulk-label-select') as HTMLSelectElement; if (!s?.value) { alert('Please select a label first.'); return; } if (selectedIssues.size > 0) location.reload(); }
export function bulkAssignMilestone(): void { const s = document.getElementById('bulk-milestone-select') as HTMLSelectElement; if (!s?.value) { alert('Please select a milestone first.'); return; } if (selectedIssues.size > 0) location.reload(); }

export function initIssueList(data: RepoPageData): void {
  initRepoPage(data);

  // Filter form auto-submit: label checkboxes, milestone/assignee selects, sort radios
  document.querySelectorAll<HTMLElement>('[data-filter-select]').forEach((el) => {
    el.addEventListener('change', () => (el.closest('form') as HTMLFormElement)?.requestSubmit());
  });

  // Author input with debounce
  const searchInput = document.querySelector<HTMLInputElement>('[data-search-input]');
  if (searchInput) {
    let t: ReturnType<typeof setTimeout>;
    searchInput.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => (searchInput.closest('form') as HTMLFormElement)?.requestSubmit(), 300);
    });
  }

  // Issue row checkbox — delegated so it works after HTMX swaps
  document.addEventListener('change', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLInputElement>('[data-issue-toggle]');
    if (!el) return;
    toggleIssueSelect(el.dataset.issueToggle!, (el as HTMLInputElement).checked);
  });

  // Bulk action buttons
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-bulk-action]');
    if (!el) return;
    const action = el.dataset.bulkAction;
    if (action === 'assign-label') bulkAssignLabel();
    else if (action === 'assign-milestone') bulkAssignMilestone();
    else if (action === 'close') bulkClose();
    else if (action === 'reopen') bulkReopen();
    else if (action === 'deselect') deselectAll();
  });

  // Template picker actions
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!el) return;
    const action = el.dataset.action;
    if (action === 'show-template-picker') {
      showTemplatePicker();
    } else if (action === 'hide-template-picker') {
      const picker = document.getElementById('template-picker');
      if (picker) picker.style.display = 'none';
    } else if (action === 'select-template') {
      const tid = el.dataset.templateId;
      if (tid) selectTemplate(tid);
    }
  });
}
