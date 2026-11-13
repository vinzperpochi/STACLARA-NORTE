(() => {
    const dialog = document.querySelector('[data-resident-guide]');
    if (!dialog || typeof dialog.showModal !== 'function') return;

    const trigger = document.querySelector('[data-resident-guide-open]');
    const steps = [...dialog.querySelectorAll('[data-guide-step]')];
    const progress = dialog.querySelector('[data-guide-progress]');
    const back = dialog.querySelector('[data-guide-back]');
    const next = dialog.querySelector('[data-guide-next]');
    const key = 'scn-resident-guide-v1:' + dialog.dataset.residentGuide;
    let index = 0;

    function render() {
        steps.forEach((step, position) => { step.hidden = position !== index; });
        progress.textContent = 'Hakbang ' + (index + 1) + ' sa ' + steps.length;
        back.hidden = index === 0;
        next.textContent = index === steps.length - 1 ? 'Tapos na' : 'Susunod';
    }

    function openGuide() {
        index = 0;
        render();
        dialog.showModal();
        dialog.querySelector('h2').focus();
    }

    trigger?.addEventListener('click', openGuide);
    back.addEventListener('click', () => {
        index -= 1;
        render();
        if (index === 0) next.focus();
    });
    next.addEventListener('click', () => {
        if (index === steps.length - 1) {
            dialog.close();
            return;
        }
        index += 1;
        render();
    });
    dialog.querySelector('[data-guide-skip]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => {
        try { localStorage.setItem(key, 'seen'); } catch {}
        trigger?.focus();
    });

    try {
        if (!localStorage.getItem(key)) openGuide();
    } catch {
        // The manual tutorial remains available when browser storage is disabled.
    }
})();
