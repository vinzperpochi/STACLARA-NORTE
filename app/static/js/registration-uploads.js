(() => {
  const inputs = [...document.querySelectorAll('[data-registration-upload]')];
  const urls = new Map();
  function validate(input) {
    const file = input.files?.[0];
    const preview = document.querySelector(`[data-registration-preview="${input.id}"]`);
    if (urls.has(input)) { URL.revokeObjectURL(urls.get(input)); urls.delete(input); }
    if (preview) { preview.hidden = true; preview.removeAttribute('src'); }
    let message = '';
    const profile = input.name === 'profile_photo';
    if (file && (!(profile ? ['image/jpeg','image/png','image/webp'] : ['image/jpeg','image/png']).includes(file.type) || !(profile ? /\.(jpe?g|png|webp)$/i : /\.(jpe?g|png)$/i).test(file.name))) message = profile ? 'Only JPEG, PNG or WebP profile photos are allowed.' : 'Only JPEG and PNG images are allowed.';
    else if (file && file.size > 5 * 1024 * 1024) message = 'Image must be no larger than 5 MB.';
    else if (file && file.size === 0) message = 'Select a nonempty image.';
    input.setCustomValidity(message);
    const error = input.closest('[data-field]')?.querySelector('[data-field-error]');
    input.setAttribute('aria-invalid', String(Boolean(message)));
    if (error) { error.textContent = message; error.classList.toggle('hidden', !message); }
    if (file && !message && preview) { const reader=new FileReader();reader.onload=()=>{if(input.files?.[0]===file){preview.src=reader.result;preview.hidden=false;}};reader.readAsDataURL(file); }
    return !message;
  }
  inputs.forEach(input => input.addEventListener('change', () => validate(input)));
  document.querySelectorAll('[data-registration-clear]').forEach(button => button.addEventListener('click', () => { const input=document.getElementById(button.dataset.registrationClear); if(input){input.value='';validate(input);} }));
  window.addEventListener('pagehide', () => urls.forEach(url => URL.revokeObjectURL(url)));
})();
