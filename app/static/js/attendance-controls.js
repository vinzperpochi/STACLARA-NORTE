/* Native checkboxes keep duty days independent and submit every checked value. */
(() => {
  document.querySelectorAll('[data-duty-days]').forEach(group => {
    const inputs = Array.from(group.querySelectorAll('input[name="weekdays"]'));
    const summary = group.querySelector('[data-duty-summary]');
    if (!inputs.length) return;
    function update() {
      const selected = inputs.filter(input => input.checked);
      inputs[0].setCustomValidity(selected.length ? '' : 'Select at least one duty day. You can select multiple days.');
      summary.textContent = selected.length
        ? `${selected.length} ${selected.length === 1 ? 'day' : 'days'} selected: ${selected.map(input => input.closest('label').querySelector('strong').textContent).join(', ')}.`
        : 'No duty days selected. Choose at least one day before saving.';
      group.dataset.empty = selected.length ? 'false' : 'true';
    }
    inputs.forEach(input => input.addEventListener('change', update));
    group.querySelectorAll('[data-duty-preset]').forEach(button => {
      button.addEventListener('click', () => {
        const preset = button.dataset.dutyPreset;
        inputs.forEach(input => {
          input.checked = preset === 'all' || (preset === 'weekdays' && Number(input.value) < 5);
        });
        inputs[0].dispatchEvent(new Event('change', {bubbles: true}));
      });
    });
    group.closest('form')?.addEventListener('reset', () => setTimeout(update, 0));
    update();
  });
})();
