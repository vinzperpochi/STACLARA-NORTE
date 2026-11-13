window.BarangayMap = {
    create(container) {
        const bounds = L.latLngBounds([14.230, 121.353], [14.241, 121.367]);
        return L.map(container, {
            scrollWheelZoom: false,
            maxBounds: bounds,
            maxBoundsViscosity: 1,
            minZoom: 16,
            maxZoom: 19
        }).setView([14.23540, 121.35962], 17);
    },

    symbols: {
        FIRE: '🔥', MEDICAL: '🚑', VIOLENCE: '⚠️', ACCIDENT: '🚗',
        DISASTER: '🌊', ROBBERY: '🔒', VAWC: '🛡️', CHILD: '🧒',
        HEALTH: '✚', GARBAGE: '🗑️', NOISE: '🔊', DISPUTE: '💬',
        PROPERTY: '🏠', INFRASTRUCTURE: '🚧', ELECTRICITY: '⚡',
        WATER: '💧', ANIMAL: '🐾', SANITATION: '🧼', UNKNOWN: '📍'
    },

    icon(symbol) {
        const pin = document.createElement('span');
        pin.className = 'incident-map-pin';
        pin.textContent = symbol;
        pin.setAttribute('aria-hidden', 'true');
        return L.divIcon({
            className: 'incident-map-marker', html: pin,
            iconSize: [36, 44], iconAnchor: [18, 44], tooltipAnchor: [0, -38]
        });
    }
};
