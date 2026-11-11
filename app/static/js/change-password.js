(() => {
  const form = document.querySelector('[data-change-password]');
  if (!form) return;
  const password = form.querySelector('#new_password');
  const confirmation = form.querySelector('#password_confirmation');
  form.querySelectorAll('[data-cp-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.cpToggle);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', `${show ? 'Hide' : 'Show'} ${input.labels[0].textContent.replace('*','').trim().toLowerCase()}`);
      const use = button.querySelector('use');
      use.setAttribute('href', use.getAttribute('href').replace(/#eye(?:-slash)?$/, show ? '#eye-slash' : '#eye'));
    });
  });
  function update() {
    const value = password.value;
    const enough = value.length >= Number(password.dataset.min);
    const complex = /[a-z]/.test(value) && /[A-Z]/.test(value) && /[0-9]/.test(value);
    const score = !enough ? 0 : !complex ? 1 : value.length >= 16 && /[^a-zA-Z0-9]/.test(value) ? 4 : 3;
    form.querySelector('[data-cp-strength-label]').textContent = !enough ? 'Too Short' : !complex ? 'Needs uppercase, lowercase & numbers' : score === 4 ? 'Strong' : 'Good';
    form.querySelectorAll('[data-cp-strength-bar]').forEach((bar, index) => { bar.style.backgroundColor = index < score ? (score === 1 ? '#c48610' : '#12902b') : '#e2ede3'; });
    confirmation.setCustomValidity(confirmation.value && confirmation.value !== value ? 'Passwords must match.' : '');
  }
  password.addEventListener('input', update);
  confirmation.addEventListener('input', update);
  form.addEventListener('submit', event => {
    update();
    if (!form.reportValidity()) { event.preventDefault(); return; }
    form.querySelector('.cp-save').disabled = true;
  });
  window.addEventListener('pageshow', () => { form.querySelector('.cp-save').disabled = false; });
  update();
})();
