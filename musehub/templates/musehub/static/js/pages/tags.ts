/**
 * tags.ts — MuseHub tags page module.
 *
 * Client-side search filtering across tag rows.
 */

export function initTags(): void {
  const input   = document.getElementById('tag-search') as HTMLInputElement | null;
  const tagList = document.getElementById('tag-list');
  if (!input || !tagList) return;

  input.addEventListener('input', () => {
    const q = input.value.toLowerCase();
    tagList.querySelectorAll<HTMLElement>('.tg-row').forEach(row => {
      const name = (row.dataset['tagName'] || '').toLowerCase();
      row.style.display = !q || name.includes(q) ? '' : 'none';
    });
  });
}
