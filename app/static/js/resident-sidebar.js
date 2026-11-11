/* Keep the current page visible within the workspace navigation scroll area. */
(() => {
  const navigation = document.querySelector('body:is(.workspace-resident,.workspace-official,.workspace-admin) #portal-sidebar nav[aria-label$="workspace"]');
  const active = navigation?.querySelector('a[aria-current="page"]');
  if (!active) return;
  const showCurrent = () => {
    if (!navigation.getClientRects().length) return;
    const bounds = navigation.getBoundingClientRect();
    const item = active.getBoundingClientRect();
    if (item.bottom > bounds.bottom - 8) navigation.scrollTop += item.bottom - bounds.bottom + 8;
    else if (item.top < bounds.top + 8) navigation.scrollTop -= bounds.top - item.top + 8;
  };
  showCurrent();
  document.querySelectorAll('[data-portal-drawer-open]').forEach(button => button.addEventListener('click', () => requestAnimationFrame(showCurrent)));
})();
