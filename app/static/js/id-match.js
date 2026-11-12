(() => {
    function normalize(text) {
        return text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()
            .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    }

    function birthFormats(date) {
        const [year, month, day] = date.split('-');
        const monthName = new Intl.DateTimeFormat('en', {month:'long', timeZone:'UTC'})
            .format(new Date(date + 'T00:00:00Z'));
        const shortMonth = monthName.slice(0, 3);
        const d = String(Number(day));
        const m = String(Number(month));
        return [
            `${year} ${month} ${day}`, `${month} ${day} ${year}`, `${day} ${month} ${year}`,
            `${m} ${d} ${year}`, `${d} ${m} ${year}`,
            ...[day, d].flatMap(value => [monthName, shortMonth].flatMap(name => [
                `${value} ${name} ${year}`, `${name} ${value} ${year}`
            ]))
        ].map(normalize);
    }

    function comparison(result, first, last, birth) {
        if (!result.text || result.confidence < 50) {
            return 'Could not read the ID clearly. Use a sharper photo or continue with official review.';
        }
        const given = normalize(first);
        const surname = normalize(last);
        if (!given || !surname || !/^\d{4}-\d{2}-\d{2}$/.test(birth) || !Number.isFinite(Date.parse(birth))) {
            return 'ID read. First name, last name, and date of birth are needed to compare.';
        }
        const text = ` ${normalize(result.text)} `;
        const found = phrase => text.includes(` ${phrase} `);
        const nameMatches = found(given) && found(surname);
        const dateMatches = birthFormats(birth).some(found);
        return nameMatches && dateMatches
            ? 'Details matched: name and date of birth. Official ID review is still required.'
            : `Review needed. Name: ${nameMatches ? 'matched' : 'not matched'}. Date of birth: ${dateMatches ? 'matched' : 'not matched'}.`;
    }

    async function recognize(file, path) {
        const assets = new URL(path, location.href);
        const asset = name => new URL(name, assets).href;
        const bitmap = await createImageBitmap(file);
        let worker;
        try {
            const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height));
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(bitmap.width * scale));
            canvas.height = Math.max(1, Math.round(bitmap.height * scale));
            canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            worker = await window.Tesseract.createWorker('eng', 1, {
                workerPath: asset('worker.min.js'),
                corePath: asset('tesseract-core-lstm.wasm.js'),
                langPath: assets.href.replace(/\/$/, ''),
                workerBlobURL: false,
                cacheMethod: 'none'
            });
            return (await worker.recognize(canvas)).data;
        } finally {
            bitmap.close();
            if (worker) await worker.terminate();
        }
    }

    const unavailable = 'Automatic ID reading is unavailable. The photo can still be reviewed manually.';
    document.querySelectorAll('[data-id-review]').forEach(review => {
        const button = review.querySelector('button');
        const status = review.querySelector('[role="status"]');
        button.addEventListener('click', async () => {
            button.disabled = true;
            status.textContent = 'Reading ID photo…';
            try {
                const response = await fetch(review.dataset.idImage, {cache:'no-store', redirect:'error'});
                if (!response.ok || !/^image\/(jpeg|png)(;|$)/i.test(response.headers.get('Content-Type') || '')) {
                    throw new Error('ID image unavailable');
                }
                const result = await recognize(await response.blob(), review.dataset.ocrAssets);
                status.textContent = comparison(result, review.dataset.first, review.dataset.last, review.dataset.birth);
            } catch {
                status.textContent = unavailable;
            } finally {
                button.disabled = false;
            }
        });
    });

    const status = document.getElementById('id-match-status');
    const fileInput = document.querySelector('input[type="file"][name="philsys_card"]');
    if (!status || !fileInput?.form) return;
    const [first, last, birth] = ['first_name','last_name','birth_date']
        .map(name => fileInput.form.elements.namedItem(name));
    if (!first || !last || !birth) return;
    const instructions = status.textContent.trim();
    let scan = 0;
    let result = null;
    function compare() {
        if (result) status.textContent = comparison(result, first.value, last.value, birth.value);
    }
    [first, last, birth].forEach(field => field.addEventListener('input', compare));
    fileInput.addEventListener('change', async () => {
        const current = ++scan;
        const file = fileInput.files[0];
        result = null;
        if (!file) {
            status.textContent = instructions;
            return;
        }
        if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 5 * 1024 * 1024) {
            status.textContent = 'Choose a JPG or PNG ID photo up to 5 MB to compare details.';
            return;
        }
        status.textContent = 'Reading ID photo…';
        try {
            const data = await recognize(file, status.dataset.ocrAssets);
            if (current === scan) {
                result = data;
                compare();
            }
        } catch {
            if (current === scan) status.textContent = unavailable;
        }
    });
})();
