/**
 * branches.ts — MuseHub branches page module.
 *
 * Handles client-side filtering (by type tab) and search across branch rows.
 */

export function initBranches(): void {
  const searchInput = document.getElementById('branch-search') as HTMLInputElement | null;
  const branchList  = document.getElementById('branch-list');
  const typeTabs    = document.querySelectorAll<HTMLAnchorElement>('.br-tab');
  let activeFilter  = 'all';

  function applyFilters(): void {
    const q = searchInput ? searchInput.value.toLowerCase() : '';
    const rows = branchList ? branchList.querySelectorAll<HTMLElement>('.br-row') : [];
    rows.forEach(row => {
      const name = (row.dataset['branchName'] || '').toLowerCase();
      const type = (row.dataset['branchType'] || '').toLowerCase();
      const nameMatch = !q || name.includes(q);
      const typeMatch = activeFilter === 'all' || type === activeFilter;
      row.style.display = nameMatch && typeMatch ? '' : 'none';
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }

  typeTabs.forEach(tab => {
    tab.addEventListener('click', e => {
      e.preventDefault();
      typeTabs.forEach(t => t.classList.remove('br-tab--active'));
      tab.classList.add('br-tab--active');
      activeFilter = tab.dataset['filter'] || 'all';
      applyFilters();
    });
  });
}
