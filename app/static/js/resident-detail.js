/* Preserve the initials placeholder when an old photo file is unavailable. */
document.querySelectorAll('[data-resident-photo]').forEach((photo) => {
  const showPlaceholder = () => {
    photo.hidden = true;
    const note = photo.closest('[data-photo-block], .rd-identity')?.querySelector('[data-resident-photo-note]');
    if (note) note.hidden = false;
  };
  photo.addEventListener('error', showPlaceholder);
  if (photo.complete && photo.naturalWidth === 0) showPlaceholder();
});
