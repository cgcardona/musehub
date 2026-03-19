/**
 * release-list.ts — MuseHub releases list page module.
 */

export function initReleaseList(): void {
  const filterTabs  = document.querySelectorAll<HTMLAnchorElement>('.rel-filter-tab');
  const searchInput = document.getElementById('rel-search') as HTMLInputElement | null;
  const list        = document.getElementById('release-rows');
  let activeFilter  = 'all';

  function applyFilters(): void {
    const q = searchInput ? searchInput.value.toLowerCase() : '';
    const cards = list ? list.querySelectorAll<HTMLElement>('.rel-card') : [];
    cards.forEach(card => {
      const status = (card.dataset.status || '').toLowerCase();
      const text   = (card.dataset.title  || '').toLowerCase();
      const statusMatch = activeFilter === 'all' || status === activeFilter;
      const searchMatch = !q || text.includes(q);
      card.style.display = statusMatch && searchMatch ? '' : 'none';
    });
  }

  filterTabs.forEach(tab => {
    tab.addEventListener('click', e => {
      e.preventDefault();
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeFilter = tab.dataset.filter || 'all';
      applyFilters();
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }
}
