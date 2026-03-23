/**
 * release-list.ts — MuseHub releases list page module.
 *
 * Client-side filter tabs (All / Stable / Pre-release / Draft) and search.
 */

export function initReleaseList(): void {
  const filterTabs  = document.querySelectorAll<HTMLAnchorElement>('.rl-tab');
  const searchInput = document.getElementById('rel-search') as HTMLInputElement | null;
  const list        = document.getElementById('release-rows');
  let activeFilter  = 'all';

  function applyFilters(): void {
    const q = searchInput ? searchInput.value.toLowerCase() : '';
    const rows = list ? list.querySelectorAll<HTMLElement>('.rl-row') : [];
    rows.forEach(row => {
      const status = (row.dataset['status'] || '').toLowerCase();
      const text   = (row.dataset['title']  || '').toLowerCase();
      const statusMatch = activeFilter === 'all' || status === activeFilter;
      const searchMatch = !q || text.includes(q);
      row.style.display = statusMatch && searchMatch ? '' : 'none';
    });
  }

  filterTabs.forEach(tab => {
    tab.addEventListener('click', e => {
      e.preventDefault();
      filterTabs.forEach(t => t.classList.remove('rl-tab--active'));
      tab.classList.add('rl-tab--active');
      activeFilter = tab.dataset['filter'] || 'all';
      applyFilters();
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }
}
