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
    const { latitude, longitude, category, location: address } = panel.closest('form').elements;
    canvas.hidden = false;
    locate.hidden = !navigator.geolocation;
    // Local viewport around Santa Clara Norte, not an administrative boundary.
    const localBounds = L.latLngBounds([14.230, 121.353], [14.241, 121.367]);
    const map = L.map(canvas, {
        scrollWheelZoom: false,
        maxBounds: localBounds,
        maxBoundsViscosity: 1,
        minZoom: 16,
        maxZoom: 19
    }).setView([14.23540, 121.35962], 17);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    let marker;
    let selection = 0;
    let pending;

    const indicator = panel.querySelector('[data-map-indicator]');
    const symbols = {
        FIRE: '🔥', MEDICAL: '🚑', VIOLENCE: '⚠️', ACCIDENT: '🚗',
        DISASTER: '🌊', ROBBERY: '🔒', VAWC: '🛡️', CHILD: '🧒',
        HEALTH: '✚', GARBAGE: '🗑️', NOISE: '🔊', DISPUTE: '💬',
        PROPERTY: '🏠', INFRASTRUCTURE: '🚧', ELECTRICITY: '⚡',
        WATER: '💧', ANIMAL: '🐾', SANITATION: '🧼', UNKNOWN: '📍'
    };

    function updateIndicator() {
        const symbol = symbols[category.value] || symbols.UNKNOWN;
        const label = category.selectedOptions[0]?.textContent.trim() || 'Other incident';
        indicator.textContent = symbol + ' ' + label;
        if (!marker) return;
        const pin = document.createElement('span');
        pin.className = 'incident-map-pin';
        pin.textContent = symbol;
        pin.setAttribute('aria-hidden', 'true');
        marker.setIcon(L.divIcon({
            className: 'incident-map-marker', html: pin,
            iconSize: [36, 44], iconAnchor: [18, 44], tooltipAnchor: [0, -38]
        }));
        const tooltip = document.createElement('span');
        tooltip.textContent = label;
        marker.setTooltipContent(tooltip);
        marker.getElement().setAttribute('aria-label', label);
    }

    function showPin(point) {
        if (marker) marker.setLatLng(point);
        else marker = L.marker(point, {icon: L.divIcon()}).addTo(map).bindTooltip('');
        updateIndicator();
    }

    category.addEventListener('change', updateIndicator);
    updateIndicator();

    async function pin(point) {
        const version = ++selection;
        pending?.abort();
        const controller = new AbortController();
        pending = controller;
        showPin(point);
        latitude.value = point.lat.toFixed(6);
        longitude.value = point.lng.toFixed(6);
        const previous = address.value;
        status.textContent = 'Pin set. Looking up the addressâ€¦';
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
            if (localBounds.contains([lat, lng])) map.setView([lat, lng], 17);
        }
    }
    function selectLocalPoint(point) {
        if (!localBounds.contains(point)) {
            status.textContent = 'Choose a pin within the Sta. Clara Norte map area.';
            return;
        }
        pin(point);
    }

    map.on('click', event => selectLocalPoint(event.latlng));
    locate.addEventListener('click', () => {
        const version = selection;
        locate.disabled = true;
        status.textContent = 'Finding your current locationâ€¦';
        navigator.geolocation.getCurrentPosition(({coords}) => {
            locate.disabled = false;
            if (version !== selection) return;
            const point = L.latLng(coords.latitude, coords.longitude);
            if (localBounds.contains(point)) map.setView(point, 18);
            selectLocalPoint(point);
        }, () => {
            locate.disabled = false;
            if (version === selection) status.textContent = 'Current location unavailable. Click the map to place a pin.';
        }, {timeout: 10000});
    });
})();
