(() => {
  const form = document.getElementById('rfidRegistrationForm');
  if (!form) return;
  const dialog = document.getElementById('rfidScanDialog');
  const title = document.getElementById('rfidScanTitle');
  const symbol = document.getElementById('rfidScanSymbol');
  const status = document.getElementById('rfidScanStatus');
  const readerLabel = document.getElementById('rfidReaderLabel');
  const hint = document.getElementById('rfidScanHint');
  const steps = ['rfidStepConnect', 'rfidStepScan', 'rfidStepConfirm'].map(id => document.getElementById(id));
  const attached = document.getElementById('rfidAttachedStatus');
  const capture = document.getElementById('rfidCaptureId');
  const save = document.getElementById('rfidSaveButton');
  const scan = document.getElementById('rfidScanButton');
  const done = document.getElementById('rfidScanDone');
  const again = document.getElementById('rfidScanAgain');
  const cancel = document.getElementById('rfidScanCancel');
  const role = form.elements.barangay_role;
  const other = document.getElementById('rfidOtherRole');
  const accountPicker = document.getElementById('rfidAccountPicker');
  const accountSelect = document.getElementById('rfidUserAccount');
  const reactivation = document.getElementById('rfidReactivation');
  const reactivateCheck = document.getElementById('rfidReactivateCheck');
  const reactivationId = document.getElementById('rfidReactivationId');
  const reactivationName = document.getElementById('rfidReactivationName');
  const reactivationLink = document.getElementById('rfidReactivationLink');
  const savedAssignment = document.getElementById('rfidSavedAssignment');
  const savedAssignmentText = document.getElementById('rfidSavedAssignmentText');
  const savedAssignmentLink = document.getElementById('rfidSavedAssignmentLink');
  const base = form.dataset.startUrl.replace(/\/start$/, '');
  const csrf = form.elements.csrf_token.value;
  let token = capture.value || '', timer, generation = 0;

  async function api(url, data) {
    const response = await fetch(url, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: {'Content-Type':'application/json', 'X-CSRFToken':csrf}, body:data === undefined ? undefined : JSON.stringify(data)});
    let result;
    try { result = await response.json(); } catch { throw new Error('Cannot reach the registration service. Check the server and try again.'); }
    if (!response.ok) throw new Error(result.message || 'Registration request failed.');
    return result;
  }
  function readerPresentation(value) {
    dialog.dataset.reader = value;
    if (readerLabel) readerLabel.textContent = {connecting: 'Connecting', ready: 'Reader ready', captured: 'Card detected', error: 'Needs attention'}[value];
    const activeStep = value === 'captured' ? 2 : (value === 'ready' ? 1 : 0);
    steps.forEach((step, index) => {
      if (!step) return;
      if (index === activeStep && value !== 'error') step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    });
  }
  function stage(value, heading, message) {
    dialog.dataset.stage = value;
    symbol.textContent = value === 'captured' ? '✓' : (value === 'error' ? '!' : '');
    title.textContent = heading;
    status.textContent = message;
    readerPresentation(value === 'waiting' ? 'connecting' : value);
    if (hint) hint.textContent = value === 'captured'
      ? 'Check the card details above, then select Use this card. Save the registration form to finish.'
      : value === 'error'
        ? 'No card has been added. Check the reader connection and select Scan again when you’re ready.'
        : 'You’re in control. Confirm Use this card after scanning, then save the form to finish registration.';
  }
  function clearCard() {
    capture.value = ''; save.disabled = true;
    attached.textContent = 'No card confirmed yet.';
    attached.classList.remove('rfid-card-attached');
    scan.textContent = 'Scan RFID Card/Tag';
  }
  function stop(discard = true) {
    generation++; clearTimeout(timer);
    const previous = token;
    token = ''; scan.disabled = false;
    return discard && previous ? api(`${base}/${encodeURIComponent(previous)}/cancel`, {}).catch(() => {}) : Promise.resolve();
  }
  function showError(message) {
    stage('error', 'Scan not confirmed', message);
    done.hidden = true; again.hidden = false; cancel.textContent = 'Close';
  }
  function roleChanged() { other.hidden = role.value !== 'Others'; form.elements.other_role.required = !other.hidden; }
  role.addEventListener('change', roleChanged);
  roleChanged();
  function registeredSelection() {
    const existing = form.querySelector('[name="account_mode"]:checked')?.value === 'existing';
    const selected = accountSelect.selectedOptions?.[0];
    return existing && selected?.value && selected.dataset.rfidRegistered === 'yes' ? selected : null;
  }
  function updateSavedAssignment() {
    const selected = registeredSelection();
    const wasVisible = !savedAssignment.hidden;
    savedAssignment.hidden = !selected;
    if (selected) {
      const info = selected.dataset;
      savedAssignmentText.textContent = `${info.personnelName || 'This personnel'} · RFID ending ${info.rfidSuffix} · ${info.rfidActive === 'yes' ? 'Active' : 'Revoked'}. This is the saved database assignment.`;
      savedAssignmentLink.href = info.personnelUrl || '#';
      if (token || capture.value) { stop(); clearCard(); }
      attached.textContent = `Saved RFID ending ${info.rfidSuffix} already belongs to this account. Open Manage saved record for changes.`;
      scan.disabled = true; save.disabled = true;
    } else {
      if (wasVisible && !capture.value) clearCard();
      scan.disabled = false; save.disabled = !capture.value;
    }
  }
  function updateReactivation(reset = false) {
    const existing = form.querySelector('[name="account_mode"]:checked')?.value === 'existing';
    const selected = accountSelect.selectedOptions?.[0];
    const normalize = value => (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
    const enteredName = normalize(`${form.elements.first_name.value} ${form.elements.last_name.value}`);
    let details = null;
    if (existing && selected?.value && selected.dataset.personnelActive === 'no' && !registeredSelection()) details = selected.dataset;
    else if (!existing && reactivation.dataset.mode === 'none' && reactivation.dataset.personnelId && normalize(reactivation.dataset.personnelName) === enteredName) details = reactivation.dataset;
    const id = details?.personnelId || '';
    if (reset || reactivationId.value !== id) reactivateCheck.checked = false;
    reactivation.hidden = !id;
    reactivateCheck.disabled = !id;
    reactivateCheck.required = Boolean(id);
    reactivationId.value = id;
    reactivationName.textContent = details?.personnelName || '';
    reactivationLink.href = details?.personnelUrl || '#';
  }
  function accountModeChanged(reset = false) {
    const existing = form.querySelector('[name="account_mode"]:checked')?.value === 'existing';
    accountPicker.hidden = !existing;
    accountSelect.disabled = !existing;
    accountSelect.required = existing;
    form.querySelectorAll('.rfid-account-option').forEach(option => option.classList.toggle('is-selected', option.querySelector('input').checked));
    updateReactivation(reset);
    updateSavedAssignment();
  }
  form.querySelectorAll('[name="account_mode"]').forEach(input => input.addEventListener('change', () => accountModeChanged(true)));
  accountModeChanged();
  accountSelect.addEventListener('change', () => {
    const selected = accountSelect.selectedOptions[0];
    if (!selected?.value) { updateReactivation(true); updateSavedAssignment(); return; }
    form.elements.first_name.value = selected.dataset.firstName || '';
    form.elements.last_name.value = selected.dataset.lastName || '';
    form.elements.email.value = selected.dataset.email || '';
    const position = selected.dataset.position || '';
    role.value = Array.from(role.options).some(option => option.value === position) ? position : (position ? 'Others' : '');
    form.elements.other_role.value = role.value === 'Others' ? position : '';
    roleChanged();
    updateReactivation(true);
    updateSavedAssignment();
  });
  [form.elements.first_name, form.elements.last_name].forEach(input => input.addEventListener('input', () => updateReactivation()));

  async function startScan() {
    if (registeredSelection()) { updateSavedAssignment(); return; }
    const cancellation = stop(); clearCard();
    const version = generation;
    stage('waiting', 'Scan RFID Card/Tag', 'Connecting to reader… Make sure the scanner is powered on and connected.');
    done.hidden = true; done.disabled = false; again.hidden = true;
    cancel.textContent = 'Cancel'; scan.disabled = true;
    if (!dialog.open) dialog.showModal();
    try {
      await cancellation;
      if (version !== generation) return;
      const started = await api(form.dataset.startUrl, {});
      if (version !== generation) { api(`${base}/${encodeURIComponent(started.capture_id)}/cancel`, {}).catch(() => {}); return; }
      token = started.capture_id;
      async function poll() {
        try {
          const result = await api(`${base}/${encodeURIComponent(token)}`);
          if (version !== generation) return;
          if (result.state === 'captured') {
            const name = `${form.elements.first_name.value} ${form.elements.last_name.value}`.trim();
            stage('captured', 'Card detected — confirm', `Card ending ${result.suffix} was scanned successfully. ${name ? `Use this card for ${name}?` : 'Attach this card to the registration form?'}`);
            attached.textContent = 'Card detected. Confirm Use this card in the scan window.';
            // Detection alone never enables Save or attaches a capture token.
            done.hidden = false; again.hidden = false;
            return;
          }
          if (result.state !== 'waiting') { showError('Scan session expired or ended. Scan again to continue.'); return; }
          readerPresentation(result.ready ? 'ready' : 'connecting');
          title.textContent = result.ready ? 'Tap your RFID card' : 'Scan RFID Card/Tag';
          status.textContent = result.message || (result.ready ? 'Waiting for card… Tap your card on the scanner.' : 'Connecting to reader… Make sure the scanner is powered on and connected.');
          timer = setTimeout(poll, 1000);
        } catch (error) { if (version === generation) showError(error.message); }
      }
      poll();
    } catch (error) { if (version === generation) showError(error.message); }
  }
  scan.addEventListener('click', startScan);
  again.addEventListener('click', startScan);
  cancel.addEventListener('click', () => { stop(); clearCard(); dialog.close(); });
  done.addEventListener('click', async () => {
    if (!token || dialog.dataset.stage !== 'captured') return;
    const version = generation;
    done.disabled = true;
    try {
      const result = await api(`${base}/${encodeURIComponent(token)}`);
      if (version !== generation) return;
      if (result.state !== 'captured') throw new Error('This card capture expired. Scan it again before confirming.');
      capture.value = token; save.disabled = false;
      attached.textContent = `✓ Card scanned · ending ${result.suffix}. Not saved yet — click Save personnel, schedule & RFID within 5 minutes.`;
      attached.classList.add('rfid-card-attached');
      scan.textContent = 'Scan a different card';
      dialog.close(); scan.focus();
    } catch (error) { if (version === generation) { clearCard(); showError(error.message); } }
    finally { done.disabled = false; }
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); stop(); clearCard(); dialog.close(); });
  dialog.addEventListener('close', () => { scan.disabled = Boolean(registeredSelection()); });
  form.addEventListener('submit', event => {
    if (registeredSelection()) { event.preventDefault(); updateSavedAssignment(); return; }
    if (!capture.value) { event.preventDefault(); attached.textContent = 'Scan and confirm a card before saving.'; }
  });
  window.addEventListener('pagehide', () => {
    if (!token || capture.value) return;
    fetch(`${base}/${encodeURIComponent(token)}/cancel`, {method:'POST',keepalive:true,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:'{}'}).catch(() => {});
  });
})();
