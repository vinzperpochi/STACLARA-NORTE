(() => {
  'use strict';

  const noticeList = document.querySelector('[data-stitch-notice-list]');
  if (noticeList) {
    const notices = [...noticeList.querySelectorAll('[data-stitch-notice]')];
    const search = document.querySelector('[data-stitch-search]');
    const unreadOnly = document.querySelector('[data-stitch-unread]');
    const emptyState = document.querySelector('[data-stitch-empty]');
    const resultCount = document.querySelector('[data-stitch-result-count]');
    const chips = [...document.querySelectorAll('[data-stitch-category-filter]')];
    const clearSearch = document.querySelector('[data-stitch-clear-search]');
    let selectedCategory = 'all';

    // Initialize clear button visibility using display style
    if (clearSearch) clearSearch.style.display = 'none';

    const updateFilters = () => {
      const query = (search?.value || '').trim().toLocaleLowerCase();
      let visible = 0;
      notices.forEach((notice) => {
        const matchesText = !query || (notice.dataset.search || '').toLocaleLowerCase().includes(query);
        const matchesUnread = !unreadOnly?.checked || notice.dataset.read === '0';
        const matchesCategory = selectedCategory === 'all' || notice.dataset.category === selectedCategory;
        const show = matchesText && matchesUnread && matchesCategory;
        
        if (!show && !notice.hidden) {
          // Hiding: add class, then set hidden after animation
          notice.classList.add('stitch-notice-hiding');
          if (window.requestAnimationFrame) {
            if (notice._hideTimeout) clearTimeout(notice._hideTimeout);
            notice._hideTimeout = setTimeout(() => {
              notice.hidden = true;
              notice.classList.remove('stitch-notice-hiding');
            }, 180);
          } else {
            notice.hidden = true;
            notice.classList.remove('stitch-notice-hiding');
          }
        } else if (show && notice.hidden) {
          // Showing: remove hidden and let fade-in animation fire
          if (notice._hideTimeout) clearTimeout(notice._hideTimeout);
          notice.hidden = false;
          notice.classList.remove('stitch-notice-hiding');
        }
        
        if (show) visible += 1;
      });
      if (emptyState) emptyState.hidden = visible !== 0;
      if (resultCount) resultCount.textContent = `${visible} sa ${notices.length} abiso ang ipinapakita`;
      const searchValue = (search?.value || '');
      if (clearSearch) clearSearch.style.display = searchValue.length ? 'block' : 'none';
      if (search) {
        search.classList.toggle('stitch-search-active', !!searchValue.length);
      }
    };

    const counts = notices.reduce((acc, notice) => {
      const category = notice.dataset.category || 'announcement';
      acc.all += 1;
      acc[category] = (acc[category] || 0) + 1;
      return acc;
    }, { all: 0 });
    chips.forEach((chip) => {
      const category = chip.dataset.stitchCategoryFilter;
      const countNode = chip.querySelector('[data-stitch-count]');
      if (countNode) countNode.textContent = String(counts[category] || 0);
      chip.addEventListener('click', () => {
        selectedCategory = category;
        chips.forEach((item) => item.setAttribute('aria-pressed', String(item === chip)));
        updateFilters();
      });
    });
    search?.addEventListener('input', updateFilters);
    search?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        search.value = '';
        if (clearSearch) clearSearch.style.display = 'none';
        updateFilters();
      }
    });
    unreadOnly?.addEventListener('change', updateFilters);
    clearSearch?.addEventListener('click', () => {
      if (search) {
        search.value = '';
        search.focus();
      }
      updateFilters();
    });
    updateFilters();
  }

  const fieldSelect = document.querySelector('[data-stitch-correction-field]');
  const currentValue = document.querySelector('[data-stitch-current-value]');
  if (fieldSelect && currentValue) {
    const showCurrentValue = () => {
      const option = fieldSelect.selectedOptions[0];
      const value = option?.dataset.current || '';
      currentValue.textContent = value || 'Walang kasalukuyang nakatalang halaga.';
    };
    fieldSelect.addEventListener('change', showCurrentValue);
    showCurrentValue();
  }

  const fullscreenButton = document.querySelector('[data-stitch-fullscreen]');
  const identityCard = document.querySelector('[data-stitch-print-card]');
  if (fullscreenButton && identityCard) {
    fullscreenButton.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await identityCard.requestFullscreen();
      } catch (error) {
        fullscreenButton.setAttribute('aria-label', 'Hindi available ang full-screen mode sa browser na ito');
      }
    });
  }
})();
