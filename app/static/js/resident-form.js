document.querySelectorAll('[data-profile-image]').forEach((input) => {
  let previewUrl;
  input.addEventListener('change', () => {
    const block = input.closest('[data-photo-block]');
    const avatar = block?.querySelector('[data-resident-avatar]');
    const file = input.files?.[0];
    input.setCustomValidity('');
    if (!file || !avatar) return;
    if (file.size > 5 * 1024 * 1024) {
      input.setCustomValidity('Select an image no larger than 5 MB.');
      input.reportValidity();
      return;
    }
    input.setCustomValidity('');
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    let photo = avatar.querySelector('img');
    if (!photo) { photo = document.createElement('img'); photo.alt = 'Selected profile photo preview'; avatar.append(photo); }
    photo.hidden = false;
    photo.src = previewUrl;
    const note = block.querySelector('[data-resident-photo-note]');
    if (note) note.hidden = true;
  });
});
