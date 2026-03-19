/**
 * sessions.ts — MuseHub sessions page module.
 */

export function initSessions(): void {
  const filterTabs  = document.querySelectorAll<HTMLAnchorElement>('.sess-filter-tab');
  const searchInput = document.getElementById('sess-search') as HTMLInputElement | null;
  const list        = document.getElementById('session-rows');
  let activeFilter  = 'all';

  function applyFilters(): void {
    const q = searchInput ? searchInput.value.toLowerCase() : '';
    const cards = list ? list.querySelectorAll<HTMLElement>('.sess-card') : [];
    cards.forEach(card => {
      const status = (card.dataset.status || '').toLowerCase();
      const text   = (card.dataset.intent || '').toLowerCase() + ' ' + (card.dataset.location || '').toLowerCase();
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
