(() => {
  'use strict';
  const view = document.querySelector('[data-profile-view]'), edit = document.querySelector('[data-profile-edit-form]');
  const showTab = key => { const trigger = document.getElementById('tab-' + key); if (trigger && window.bootstrap) bootstrap.Tab.getOrCreateInstance(trigger).show(); };
  document.querySelectorAll('[data-profile-tab-link]').forEach(link => link.addEventListener('click', () => showTab(link.dataset.profileTabLink)));
  if (edit && !edit.hidden) showTab('contact'); else showTab(location.hash.slice(1));
  document.querySelector('[data-profile-edit]')?.addEventListener('click', () => { view.hidden = true; edit.hidden = false; edit.querySelector('input:not([type="hidden"])')?.focus(); });
  document.querySelector('[data-profile-cancel]')?.addEventListener('click', () => { edit.reset(); edit.hidden = true; view.hidden = false; edit.dataset.dirty = ''; });
  const form = document.querySelector('[data-photo-form]');
  if (!form) return;
  const input = form.querySelector('[data-photo-input]'), canvas = form.querySelector('canvas'), status = form.querySelector('[data-photo-status]'), crop = form.querySelector('[data-photo-crop]'), controls = [...form.querySelectorAll('[data-photo-control]')];
  let url, picture;
  const draw = () => {
    if (!picture) return;
    const settings = Object.fromEntries(controls.map(c => [c.dataset.photoControl, Number(c.value)]));
    const size = Math.min(picture.naturalWidth, picture.naturalHeight) / settings.zoom;
    const x = Math.max(0, Math.min(picture.naturalWidth-size, settings.x*picture.naturalWidth-size/2));
    const y = Math.max(0, Math.min(picture.naturalHeight-size, settings.y*picture.naturalHeight-size/2));
    const ctx = canvas.getContext('2d'); ctx.clearRect(0,0,400,400);
    if (crop.checked) ctx.drawImage(picture, Math.round(x), Math.round(y), Math.round(x+size)-Math.round(x), Math.round(y+size)-Math.round(y), 0,0,400,400);
    else { const scale = Math.min(400/picture.naturalWidth,400/picture.naturalHeight); const w=picture.naturalWidth*scale,h=picture.naturalHeight*scale; ctx.drawImage(picture,(400-w)/2,(400-h)/2,w,h); }
    controls.forEach(c => c.disabled = !crop.checked); canvas.hidden = false;
  };
  const clear = () => { if (url) URL.revokeObjectURL(url); url = null; picture = null; canvas.hidden = true; input.setCustomValidity(''); };
  input.addEventListener('change', () => {
    clear(); const file=input.files?.[0]; if (!file) return;
    let error='';
    if (!['image/jpeg','image/png','image/webp'].includes(file.type) || !/\.(jpe?g|png|webp)$/i.test(file.name)) error='Choose a JPG, PNG or WebP image.';
    else if (!file.size || file.size>5*1024*1024) error='Choose a nonempty image no larger than 5 MB.';
    input.setCustomValidity(error); status.textContent=error || 'Loading selected image preview…'; if (error) return;
    const selectedPicture=new Image(); picture=selectedPicture;
    selectedPicture.onload=()=>{if(picture!==selectedPicture)return; if (picture.naturalWidth*picture.naturalHeight>20000000) {input.setCustomValidity('Image dimensions are too large.'); status.textContent='Use an image with at most 20 million pixels.'; canvas.hidden=true; return;} draw(); status.textContent='Selected image preview — not saved yet.'; };
    selectedPicture.onerror=()=>{if(picture!==selectedPicture)return;input.setCustomValidity('This file cannot be decoded as an image.');status.textContent='Select a valid image.';};
    const reader=new FileReader();reader.onload=()=>{if(picture===selectedPicture)selectedPicture.src=reader.result;};reader.readAsDataURL(file);
  });
  controls.forEach(c=>c.addEventListener('input',draw)); crop.addEventListener('change',draw);
  const zone=form.querySelector('[data-photo-drop]');
  ['dragenter','dragover'].forEach(name=>zone.addEventListener(name,event=>{event.preventDefault();zone.classList.add('is-dragging');}));
  ['dragleave','drop'].forEach(name=>zone.addEventListener(name,event=>{event.preventDefault();zone.classList.remove('is-dragging');}));
  zone.addEventListener('drop',event=>{if(event.dataTransfer.files.length===1){input.files=event.dataTransfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}});
  document.getElementById('photoModal')?.addEventListener('hidden.bs.modal',()=>{form.reset();clear();controls.forEach(c=>c.disabled=false);status.textContent='Select a picture to preview it before saving.';});
  form.addEventListener('submit',()=>{if(form.checkValidity()){form.querySelector('[data-photo-save]').disabled=true;status.textContent='Saving your photo…';}});
  window.addEventListener('pagehide',clear);
})();
