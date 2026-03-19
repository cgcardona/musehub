/**
 * branches.ts — MuseHub branches page module.
 */

export function initBranches(): void {
  const searchInput = document.getElementById('branch-search') as HTMLInputElement | null;
  const branchList  = document.getElementById('branch-list');
  const typeTabs    = document.querySelectorAll<HTMLAnchorElement>('.branch-type-tab');
  let activeFilter  = 'all';

  function applyFilters(): void {
    const q = searchInput ? searchInput.value.toLowerCase() : '';
    const cards = branchList ? branchList.querySelectorAll<HTMLElement>('.branch-card') : [];
    cards.forEach(card => {
      const name = (card.dataset.branchName || '').toLowerCase();
      const type = (card.dataset.branchType || '').toLowerCase();
      const nameMatch = !q || name.includes(q);
      const typeMatch = activeFilter === 'all' || type === activeFilter;
      card.style.display = nameMatch && typeMatch ? '' : 'none';
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }

  typeTabs.forEach(tab => {
    tab.addEventListener('click', e => {
      e.preventDefault();
      typeTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeFilter = tab.dataset.filter || 'all';
      applyFilters();
    });
  });
}
