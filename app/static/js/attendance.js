(() => {
    const root = document.querySelector('[data-attendance-live]');
    if (!root) return;

    const filters = new URLSearchParams(location.search);
    const olderPage = ['page', 'feed_page', 'leave_page'].some(key => Number(filters.get(key)) > 1);
    if (olderPage) return;

    const endpoint = new URL(root.dataset.activityUrl, location.origin);
    for (const key of ['q', 'department', 'personnel_id']) {
        if (filters.has(key)) endpoint.searchParams.set(key, filters.get(key));
    }

    let dirty = false;
    root.addEventListener('input', () => { dirty = true; });
    const canRefresh = () => !document.hidden && !dirty && !root.querySelector('details[open]')
        && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);

    async function poll() {
        if (canRefresh()) {
            try {
                const response = await fetch(endpoint, { cache: 'no-store', redirect: 'error' });
                if (response.ok) {
                    const { version } = await response.json();
                    if (Number.isInteger(version) && version !== Number(root.dataset.attendanceLive) && canRefresh()) {
                        location.reload();
                        return;
                    }
                }
            } catch {
                // Keep the dashboard available and retry after a transient network error.
            }
        }
        setTimeout(poll, 2000);
    }

    setTimeout(poll, 2000);
})();
