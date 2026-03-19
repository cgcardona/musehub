/**
 * tags.ts — MuseHub tags page module.
 */

export function initTags(): void {
  const input   = document.getElementById('tag-search') as HTMLInputElement | null;
  const tagList = document.getElementById('tag-list');
  if (!input || !tagList) return;

  input.addEventListener('input', () => {
    const q = input.value.toLowerCase();
    tagList.querySelectorAll<HTMLElement>('.tag-card').forEach(card => {
      const name = (card.dataset.tagName || '').toLowerCase();
      card.style.display = !q || name.includes(q) ? '' : 'none';
    });
  });
}
