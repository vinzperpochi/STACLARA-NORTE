/* Filter native attendance pickers while keeping their saved option metadata. */
(() => {
  document.querySelectorAll('.ops-attendance select[data-searchable-select]').forEach((select, index) => {
    const options = Array.from(select.options);
    if (options.filter(option => option.value).length <= 10) return;
    const label = select.closest('label');
    if (!label) return;
    const wrapper = document.createElement('div');
    wrapper.className = `ops-searchable-picker ${label.classList.contains('ops-full') ? 'ops-full' : ''}`;
    const filterLabel = document.createElement('label');
    filterLabel.className = 'ops-field';
    const name = label.firstChild?.textContent.trim() || 'choices';
    filterLabel.textContent = `Search ${name.toLowerCase()}`;
    const input = document.createElement('input');
    input.type = 'search';
    input.className = 'form-control';
    input.placeholder = 'Type a name, ID or email';
    input.autocomplete = 'off';
    const status = document.createElement('p');
    status.className = 'ops-muted';
    status.id = `attendance-picker-status-${index}`;
    status.setAttribute('role', 'status');
    input.setAttribute('aria-describedby', status.id);
    filterLabel.append(input);
    label.before(wrapper);
    wrapper.append(filterLabel, label, status);
    function update() {
      const term = input.value.trim().toLocaleLowerCase();
      let matches = 0;
      options.forEach(option => {
        const match = !term || option.textContent.toLocaleLowerCase().includes(term);
        if (option.value && match) matches++;
        option.hidden = Boolean(option.value && !match && !option.selected);
      });
      status.textContent = `${matches} matching ${matches === 1 ? 'choice' : 'choices'}. Current selection stays available.`;
    }
    input.addEventListener('input', update);
    // Enter in this search field must not submit the surrounding registration form.
    input.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
    select.addEventListener('change', update);
    select.form?.addEventListener('reset', () => setTimeout(() => { input.value = ''; update(); }, 0));
    update();
  });
})();
