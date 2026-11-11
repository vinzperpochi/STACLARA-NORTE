(() => {
  'use strict';
  const select = document.getElementById('choose-document');
  const fee = document.querySelector('[data-document-fee]:not(option)');
  if (!select || !fee) return;
  const update = () => {
    const option = select.selectedOptions[0];
    fee.textContent = option?.dataset.documentFee || 'To be confirmed by the barangay';
  };
  select.addEventListener('change', update);
  update();
})();
