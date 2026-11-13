(() => {
    const panel = document.querySelector('[data-incident-map]');
    if (!panel) return;
    const status = panel.querySelector('[data-map-status]');
    if (!window.L) {
        status.textContent = 'Map unavailable. Enter the location or landmark above.';
        return;
    }
    const canvas = panel.querySelector('[data-map-canvas]');
    const locate = panel.querySelector('[data-locate-incident]');
    const { latitude, longitude, location: address } = panel.closest('form').elements;
    canvas.hidden = false;
    locate.hidden = !navigator.geolocation;
    const map = L.map(canvas, {scrollWheelZoom: false}).setView([14.24, 121.37], 14);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    let marker;
    let selection = 0;
    let pending;

    function showPin(point) {
        if (marker) marker.setLatLng(point);
        else marker = L.circleMarker(point, {radius: 9, color: '#075b21', fillOpacity: 1}).addTo(map);
    }

    async function pin(point) {
        const version = ++selection;
        pending?.abort();
        const controller = new AbortController();
        pending = controller;
        showPin(point);
        latitude.value = point.lat.toFixed(6);
        longitude.value = point.lng.toFixed(6);
        const previous = address.value;
        status.textContent = 'Pin set. Looking up the address…';
        const url = new URL(panel.dataset.reverseUrl, location.href);
        url.searchParams.set('lat', latitude.value);
        url.searchParams.set('lon', longitude.value);
        try {
            const response = await fetch(url, {signal: controller.signal});
            if (!response.ok) throw new Error('Address unavailable');
            const result = await response.json();
            if (version !== selection) return;
            if (typeof result.display_name !== 'string' || !result.display_name.trim()) throw new Error('Address unavailable');
            if (address.value === previous) address.value = result.display_name.slice(0, address.maxLength);
            status.textContent = 'Pin saved. Review the location or landmark before submitting.';
        } catch {
            if (version === selection) status.textContent = 'Pin saved. Enter the location or landmark manually.';
        }
    }

    if (latitude.value && longitude.value) {
        const lat = Number(latitude.value);
        const lng = Number(longitude.value);
        if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
            showPin([lat, lng]);
            map.setView([lat, lng], 16);
        }
    }
    map.on('click', event => pin(event.latlng.wrap()));
    locate.addEventListener('click', () => {
        const version = selection;
        locate.disabled = true;
        status.textContent = 'Finding your current location…';
        navigator.geolocation.getCurrentPosition(({coords}) => {
            locate.disabled = false;
            if (version !== selection) return;
            const point = L.latLng(coords.latitude, coords.longitude);
            map.setView(point, 17);
            pin(point);
        }, () => {
            locate.disabled = false;
            if (version === selection) status.textContent = 'Current location unavailable. Click the map to place a pin.';
        }, {timeout: 10000});
    });
})();
