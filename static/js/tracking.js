/**
 * Fresh Trace — Live Order Tracking & Rider Delivery Management System
 * Flipkart Minutes & Swiggy Instamart-style Real-time Road Navigation & Tracking
 */

// Helper: Custom Leaflet Marker Icons (Clean Minimalist Flipkart/Instamart Style)
function createCustomMarkerIcon(type, title, pillLabel) {
    if (type === 'rider') {
        return L.divIcon({
            className: 'ft-map-marker-wrap ft-rider-marker-wrap',
            html: `
                <div class="ft-pin-wrapper">
                    ${pillLabel ? `<div class="ft-pin-pill-label pill-rider">${pillLabel}</div>` : ''}
                    <div class="ft-vehicle-halo-container">
                        <div class="ft-vehicle-radar-disk"></div>
                        <div class="ft-vehicle-radar-core"></div>
                        <div class="ft-vehicle-icon-box black-mode" title="${title || 'Rider'}">
                            <i class="fa-solid fa-motorcycle"></i>
                        </div>
                    </div>
                </div>
            `,
            iconSize: [60, 68],
            iconAnchor: [30, 46],
            popupAnchor: [0, -44]
        });
    } else if (type === 'customer') {
        return L.divIcon({
            className: 'ft-map-marker-wrap ft-customer-marker-wrap',
            html: `
                <div class="ft-pin-wrapper">
                    ${pillLabel ? `<div class="ft-pin-pill-label pill-customer">${pillLabel}</div>` : ''}
                    <div class="ft-marker-bubble ft-customer-bubble" title="${title || 'Customer Drop-off'}">
                        <i class="fa-solid fa-location-dot"></i>
                    </div>
                </div>
            `,
            iconSize: [60, 60],
            iconAnchor: [30, 42],
            popupAnchor: [0, -38]
        });
    } else if (type === 'farm' || type === 'pickup') {
        return L.divIcon({
            className: 'ft-map-marker-wrap ft-farm-marker-wrap',
            html: `
                <div class="ft-pin-wrapper">
                    ${pillLabel ? `<div class="ft-pin-pill-label pill-pickup">${pillLabel}</div>` : ''}
                    <div class="ft-marker-bubble ft-farm-bubble" title="${title || 'Pickup Store'}">
                        <i class="fa-solid fa-store"></i>
                    </div>
                </div>
            `,
            iconSize: [60, 60],
            iconAnchor: [30, 42],
            popupAnchor: [0, -38]
        });
    }
    return L.Icon.Default();
}

// Distance calculation between coordinates (Haversine formula in metres)
function calculateHaversineMetres(lat1, lon1, lat2, lon2) {
    if (!lat1 || !lon1 || !lat2 || !lon2) return 0;
    const R = 6371000;
    const toRad = deg => (deg * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

// Format distance string
function formatDistance(metres) {
    if (!metres || metres <= 0) return '0 m';
    if (metres >= 1000) {
        return (metres / 1000).toFixed(1) + ' km';
    }
    return Math.round(metres) + ' m';
}

// Format ETA string
function formatEta(distanceMetres, speedKmh = 25) {
    if (!distanceMetres || distanceMetres <= 50) return 'Arriving now';
    const speedMps = (speedKmh * 1000) / 3600;
    const seconds = distanceMetres / speedMps;
    const minutes = Math.max(1, Math.round((seconds / 60) + 2)); // 2 min buffer
    const now = new Date();
    now.setMinutes(now.getMinutes() + minutes);
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${minutes} min${minutes !== 1 ? 's' : ''} (${timeStr})`;
}

// Helper: Fetch real city road route using OSRM Navigation API (with fallback)
function fetchRoadRoute(startLat, startLng, endLat, endLng, callback) {
    if (!startLat || !startLng || !endLat || !endLng) {
        callback({ coords: [], distance: 0, duration: 0 });
        return;
    }
    const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${startLng},${startLat};${endLng},${endLat}?overview=full&geometries=geojson`;
    fetch(osrmUrl)
        .then(res => res.json())
        .then(data => {
            if (data.code === 'Ok' && data.routes && data.routes.length > 0) {
                const geoCoords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);
                callback({
                    coords: geoCoords,
                    distance: data.routes[0].distance,
                    duration: data.routes[0].duration
                });
            } else {
                callback({
                    coords: [[startLat, startLng], [endLat, endLng]],
                    distance: calculateHaversineMetres(startLat, startLng, endLat, endLng),
                    duration: 0
                });
            }
        })
        .catch(() => {
            callback({
                coords: [[startLat, startLng], [endLat, endLng]],
                distance: calculateHaversineMetres(startLat, startLng, endLat, endLng),
                duration: 0
            });
        });
}

// Helper: Setup modern high-res street tiles with fallback
function setupModernMapTiles(map) {
    const tileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        subdomains: 'abcd',
        maxZoom: 20,
        minZoom: 3
    }).addTo(map);

    // Fallback if tile server has issues
    tileLayer.on('tileerror', function() {
        if (!map._hasFallbackTiles) {
            map._hasFallbackTiles = true;
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19
            }).addTo(map);
        }
    });

    // Ensure map tiles never stay blank
    setTimeout(() => map.invalidateSize(), 50);
    setTimeout(() => map.invalidateSize(), 300);
    setTimeout(() => map.invalidateSize(), 800);
    window.addEventListener('resize', () => map.invalidateSize());

    return tileLayer;
}


/* =========================================================================
   1. CUSTOMER TRACK ORDER MAP CONTROLLER (FLIPKART / INSTAMART STYLE)
   ========================================================================= */
function initCustomerTrackingMap(options) {
    let locationApiUrl, updateCustomerLocationUrl, csrfToken, otpAlreadyShown;
    if (typeof options === 'object') {
        locationApiUrl = options.locationApiUrl;
        updateCustomerLocationUrl = options.updateCustomerLocationUrl;
        csrfToken = options.csrfToken;
        otpAlreadyShown = !!options.otpAlreadyVisibleOnLoad;
    } else {
        locationApiUrl = arguments[0];
        updateCustomerLocationUrl = arguments[1];
        csrfToken = arguments[2];
        otpAlreadyShown = !!arguments[3];
    }

    const mapContainer = document.getElementById('tracking-map');
    if (!mapContainer) return;

    // Initialize Leaflet Map
    const map = L.map('tracking-map', {
        zoomControl: true,
        scrollWheelZoom: true,
    }).setView([13.0827, 80.2707], 13);

    setupModernMapTiles(map);

    let riderMarker = null;
    let customerMarker = null;
    let farmMarker = null;
    let routeCasingPolyline = null;
    let routeInnerPolyline = null;
    let farmRoutePolyline = null;
    let initialBoundsSet = false;
    let currentCustLat = null;
    let currentCustLng = null;
    let customerSimTimer = null;
    let lastRiderLat = null;
    let lastRiderLng = null;

    // A. Broadcast customer live location to Django backend
    function broadcastCustomerLocation(lat, lng, accuracy = 10) {
        currentCustLat = lat;
        currentCustLng = lng;

        if (customerMarker) {
            customerMarker.setLatLng([lat, lng]);
        }

        // Re-draw road route if rider exists
        if (lastRiderLat && lastRiderLng) {
            drawRoadRouteBetween(lastRiderLat, lastRiderLng, lat, lng);
        }

        if (!updateCustomerLocationUrl) return;

        fetch(updateCustomerLocationUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({
                latitude: lat,
                longitude: lng,
                accuracy: accuracy
            })
        })
        .then(res => res.json())
        .then(data => {
            const statusBadge = document.getElementById('customer-live-gps-badge');
            if (statusBadge) {
                statusBadge.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle px-3 py-2 rounded-pill d-flex align-items-center gap-2 shadow-sm"><i class="fa-solid fa-satellite-dish animate-pulse text-success"></i> <span>Live Location Shared (±${Math.round(accuracy)}m)</span></span>`;
            }
        })
        .catch(() => { /* silent retry */ });
    }

    // Start Customer GPS Watch
    function startCustomerGpsSharing() {
        if (!('geolocation' in navigator)) return;

        const statusBadge = document.getElementById('customer-live-gps-badge');
        if (statusBadge) {
            statusBadge.innerHTML = `<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-3 py-2 rounded-pill d-flex align-items-center gap-2"><i class="fa-solid fa-spinner fa-spin"></i> Sharing live location...</span>`;
        }

        navigator.geolocation.watchPosition(
            (pos) => {
                const { latitude, longitude, accuracy } = pos.coords;
                broadcastCustomerLocation(latitude, longitude, accuracy);
            },
            (err) => {
                if (statusBadge) {
                    statusBadge.innerHTML = `<span class="badge bg-light text-dark border px-3 py-2 rounded-pill"><i class="fa-solid fa-location-dot text-danger me-1"></i> Static Address Location</span>`;
                }
            },
            { enableHighAccuracy: true, maximumAge: 3000, timeout: 10000 }
        );
    }

    function drawRoadRouteBetween(rLat, rLng, cLat, cLng) {
        fetchRoadRoute(rLat, rLng, cLat, cLng, function(res) {
            const coords = res.coords;
            if (!coords || coords.length === 0) return;

            // 1. Casing polyline (dark outer stroke)
            if (!routeCasingPolyline) {
                routeCasingPolyline = L.polyline(coords, {
                    color: '#1e40af',
                    weight: 8,
                    opacity: 0.85,
                    lineCap: 'round',
                    lineJoin: 'round'
                }).addTo(map);
            } else {
                routeCasingPolyline.setLatLngs(coords);
            }

            // 2. Inner vibrant electric blue polyline
            if (!routeInnerPolyline) {
                routeInnerPolyline = L.polyline(coords, {
                    color: '#3b82f6',
                    weight: 5,
                    opacity: 1,
                    lineCap: 'round',
                    lineJoin: 'round'
                }).addTo(map);
            } else {
                routeInnerPolyline.setLatLngs(coords);
            }

            // If OSRM computed distance, update live ETA & distance
            if (res.distance > 0) {
                const distEl = document.getElementById('order-distance');
                if (distEl) distEl.textContent = formatDistance(res.distance);
                const etaEl = document.getElementById('order-eta');
                if (etaEl) etaEl.textContent = formatEta(res.distance);
            }
        });
    }

    // B. Poll Order Location API to track Rider & Updates
    function updateMap(data) {
        if (!data || !data.success) return;

        // 1. Update text fields and badges
        const statusBadge = document.getElementById('order-status-badge');
        if (statusBadge) {
            statusBadge.textContent = data.status_display || data.status;
            if (data.status === 'out_for_delivery') {
                statusBadge.className = 'badge bg-primary text-uppercase px-3 py-2 rounded-pill shadow-sm';
            } else if (data.status === 'delivered') {
                statusBadge.className = 'badge bg-success text-uppercase px-3 py-2 rounded-pill shadow-sm';
            }
        }

        const riderNameEl = document.getElementById('driver-name');
        if (riderNameEl && data.rider && data.rider.driver_name) {
            riderNameEl.textContent = data.rider.driver_name;
        }

        const riderPhoneEl = document.getElementById('driver-phone');
        if (riderPhoneEl && data.rider && data.rider.phone) {
            riderPhoneEl.textContent = data.rider.phone;
            riderPhoneEl.href = `tel:${data.rider.phone}`;
        }

        const distEl = document.getElementById('order-distance');
        if (distEl && data.distance_display) {
            distEl.textContent = data.distance_display;
        }

        const etaEl = document.getElementById('order-eta');
        if (etaEl && data.eta_display) {
            etaEl.textContent = data.eta_display;
        }

        // Stepper updates
        const stepTransit = document.getElementById('step-transit');
        const stepDelivered = document.getElementById('step-delivered');
        if (stepTransit && data.status === 'out_for_delivery') {
            stepTransit.classList.add('active');
        }
        if (stepDelivered && data.status === 'delivered') {
            if (stepTransit) stepTransit.classList.add('active');
            stepDelivered.classList.add('active');
        }

        // 2. Coordinates
        const customerLat = currentCustLat || (data.customer && data.customer.latitude);
        const customerLng = currentCustLng || (data.customer && data.customer.longitude);
        const riderLat = data.rider && data.rider.latitude;
        const riderLng = data.rider && data.rider.longitude;

        lastRiderLat = riderLat;
        lastRiderLng = riderLng;

        const boundsPoints = [];

        // Customer Drop-off Marker (📍)
        if (customerLat && customerLng) {
            const custPos = [customerLat, customerLng];
            boundsPoints.push(custPos);
            const custName = (data.customer && data.customer.name) || 'Customer';
            const custAddr = (data.customer && data.customer.address) || '';

            if (!customerMarker) {
                customerMarker = L.marker(custPos, {
                    icon: createCustomMarkerIcon('customer', custName, 'Drop-off'),
                    zIndexOffset: 400
                }).addTo(map);
                customerMarker.bindPopup(`
                    <div class="ft-popup-content">
                        <div class="fw-bold text-dark"><i class="fa-solid fa-location-dot me-1 text-danger"></i> ${custName}</div>
                        <small class="text-muted d-block">${custAddr || 'Delivery Address'}</small>
                        <span class="badge bg-danger-subtle text-danger mt-1">Destination</span>
                    </div>
                `);
            } else {
                customerMarker.setLatLng(custPos);
            }
        }

        // Rider Marker (🛵)
        if (riderLat && riderLng) {
            const riderPos = [riderLat, riderLng];
            boundsPoints.push(riderPos);
            const riderName = (data.rider && data.rider.driver_name) || 'Delivery Partner';

            if (!riderMarker) {
                riderMarker = L.marker(riderPos, {
                    icon: createCustomMarkerIcon('rider', riderName, 'Rider'),
                    zIndexOffset: 1000
                }).addTo(map);
                riderMarker.bindPopup(`
                    <div class="ft-popup-content">
                        <div class="fw-bold text-dark"><i class="fa-solid fa-motorcycle me-1"></i> ${riderName}</div>
                        <div class="text-success small fw-semibold"><i class="fa-solid fa-bolt me-1"></i> In Transit</div>
                    </div>
                `);
            } else {
                riderMarker.setLatLng(riderPos);
            }

            // Draw road-snapped route from Rider to Customer
            if (customerLat && customerLng) {
                drawRoadRouteBetween(riderLat, riderLng, customerLat, customerLng);
            }
        }

        // Auto-fit initial bounds
        if (!initialBoundsSet && boundsPoints.length > 0) {
            map.fitBounds(L.latLngBounds(boundsPoints), { padding: [60, 60], maxZoom: 15 });
            initialBoundsSet = true;
            setTimeout(() => map.invalidateSize(), 200);
        }

        // 3. Arrival & OTP Handling
        if (data.arrived) {
            const arrivedIndicator = document.getElementById('arrived-indicator');
            if (arrivedIndicator) arrivedIndicator.style.display = 'block';
        }

        if (data.otp_visible && data.otp) {
            const otpSection = document.getElementById('otp-section');
            const otpCode = document.getElementById('otp-code');
            if (otpSection) otpSection.style.display = 'block';
            if (otpCode) otpCode.textContent = data.otp;

            if (!otpAlreadyShown) {
                otpAlreadyShown = true;
                const modalOtp = document.getElementById('modal-otp-code');
                if (modalOtp) modalOtp.textContent = data.otp;
                const modalEl = document.getElementById('arrivalModal');
                if (modalEl && window.bootstrap) {
                    new bootstrap.Modal(modalEl).show();
                }
            }
        }
    }

    function pollLocation() {
        fetch(locationApiUrl, { headers: { 'Accept': 'application/json' } })
            .then(res => res.json())
            .then(data => updateMap(data))
            .catch(() => { /* silent retry */ });
    }

    // Sync Real Device GPS Button Listener
    const syncCustGpsBtn = document.getElementById('btn-sync-cust-gps');
    if (syncCustGpsBtn) {
        syncCustGpsBtn.addEventListener('click', function() {
            if (!('geolocation' in navigator)) {
                alert('Geolocation is not supported by your browser.');
                return;
            }
            syncCustGpsBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Syncing GPS...';
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const { latitude, longitude, accuracy } = pos.coords;
                    broadcastCustomerLocation(latitude, longitude, accuracy);
                    map.setView([latitude, longitude], 15, { animate: true });
                    syncCustGpsBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Real GPS Synced';
                    setTimeout(() => {
                        syncCustGpsBtn.innerHTML = '<i class="fa-solid fa-location-crosshairs me-1"></i> Sync My Device GPS';
                    }, 2500);
                },
                (err) => {
                    alert('Could not access device GPS. Please grant location permissions in your browser.');
                    syncCustGpsBtn.innerHTML = '<i class="fa-solid fa-location-crosshairs me-1"></i> Sync My Device GPS';
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        });
    }

    // Customer Simulation Toggle (for testing)
    const custSimBtn = document.getElementById('btn-cust-sim-motion');
    if (custSimBtn) {
        let isCustSimulating = false;
        custSimBtn.addEventListener('click', function() {
            if (isCustSimulating) {
                clearInterval(customerSimTimer);
                isCustSimulating = false;
                this.innerHTML = '<i class="fa-solid fa-person-walking me-1"></i> Test Motion';
                this.className = 'btn btn-outline-secondary btn-sm rounded-pill';
                return;
            }

            isCustSimulating = true;
            this.innerHTML = '<i class="fa-solid fa-pause me-1"></i> Pause Motion';
            this.className = 'btn btn-warning btn-sm rounded-pill';

            let baseLat = currentCustLat || 13.050000;
            let baseLng = currentCustLng || 80.212000;
            let step = 0;

            customerSimTimer = setInterval(() => {
                step++;
                const offsetLat = baseLat + Math.sin(step / 3) * 0.002;
                const offsetLng = baseLng + Math.cos(step / 3) * 0.002;
                broadcastCustomerLocation(offsetLat, offsetLng, 5);
            }, 1500);
        });
    }

    pollLocation();
    setInterval(pollLocation, 3500);
    startCustomerGpsSharing();
}


/* =========================================================================
   2. RIDER DELIVERY MAP & GPS STREAMING CONTROLLER (FLIPKART / INSTAMART STYLE)
   ========================================================================= */
function initRiderDeliveryMap(config) {
    const {
        orderId,
        updateLocationUrl,
        orderLocationApiUrl,
        startDeliveryUrl,
        completeDeliveryUrl,
        customerLat: initialCustomerLat,
        customerLng: initialCustomerLng,
        farmLat,
        farmLng,
        csrfToken
    } = config;

    const mapContainer = document.getElementById('rider-map');
    if (!mapContainer) return;

    let customerLat = initialCustomerLat;
    let customerLng = initialCustomerLng;

    // Start rider near farm or offset from customer so distance is accurate
    let currentRiderLat = farmLat || (customerLat ? customerLat + 0.025 : 13.0827);
    let currentRiderLng = farmLng || (customerLng ? customerLng + 0.025 : 80.2707);

    // Initialize Map
    const initialCenter = [(currentRiderLat + (customerLat || currentRiderLat)) / 2, (currentRiderLng + (customerLng || currentRiderLng)) / 2];
    const map = L.map('rider-map', {
        zoomControl: true,
        scrollWheelZoom: true,
    }).setView(initialCenter, 13);

    setupModernMapTiles(map);

    let riderMarker = null;
    let customerMarker = null;
    let routeCasingPolyline = null;
    let routeInnerPolyline = null;
    let activeWatchId = null;
    let simulationTimer = null;
    let cachedRoadCoords = [];

    // Add Customer Marker (Drop-off)
    if (customerLat && customerLng) {
        customerMarker = L.marker([customerLat, customerLng], {
            icon: createCustomMarkerIcon('customer', 'Customer Drop-off', 'Drop-off'),
            zIndexOffset: 500
        }).addTo(map);
        customerMarker.bindPopup('<strong><i class="fa-solid fa-location-dot text-danger"></i> Customer Delivery Address</strong>');
    }

    function updateRiderPosition(lat, lng, accuracy = 10, speed = 0, heading = 0) {
        currentRiderLat = lat;
        currentRiderLng = lng;

        if (!riderMarker) {
            riderMarker = L.marker([lat, lng], {
                icon: createCustomMarkerIcon('rider', 'You', 'You'),
                zIndexOffset: 1000
            }).addTo(map);
            riderMarker.bindPopup('<strong><i class="fa-solid fa-motorcycle text-dark"></i> Your Live Location</strong>');
        } else {
            riderMarker.setLatLng([lat, lng]);
        }

        // Draw / update Road Route to customer
        updateRouteAndCalculations();

        // Send rider coordinates to Django backend
        broadcastGpsToBackend(lat, lng, accuracy, speed, heading);
    }

    function updateRouteAndCalculations() {
        if (customerLat && customerLng && currentRiderLat && currentRiderLng) {
            fetchRoadRoute(currentRiderLat, currentRiderLng, customerLat, customerLng, function(res) {
                const coords = res.coords;
                if (!coords || coords.length === 0) return;
                cachedRoadCoords = coords;

                // 1. Casing polyline (deep royal blue border)
                if (!routeCasingPolyline) {
                    routeCasingPolyline = L.polyline(coords, {
                        color: '#1e40af',
                        weight: 8,
                        opacity: 0.85,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                } else {
                    routeCasingPolyline.setLatLngs(coords);
                }

                // 2. Inner vibrant electric blue polyline
                if (!routeInnerPolyline) {
                    routeInnerPolyline = L.polyline(coords, {
                        color: '#3b82f6',
                        weight: 5,
                        opacity: 1,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }).addTo(map);
                } else {
                    routeInnerPolyline.setLatLngs(coords);
                }

                // Update live distance & ETA readouts
                const distM = res.distance || calculateHaversineMetres(currentRiderLat, currentRiderLng, customerLat, customerLng);
                const distDisplay = formatDistance(distM);
                const etaDisplay = formatEta(distM);

                const distEl = document.getElementById('rider-distance');
                if (distEl) distEl.textContent = distDisplay;
                const etaEl = document.getElementById('rider-eta');
                if (etaEl) etaEl.textContent = etaDisplay;
            });
        }
    }

    function broadcastGpsToBackend(lat, lng, accuracy, speed, heading) {
        if (!updateLocationUrl) return;

        fetch(updateLocationUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                latitude: lat,
                longitude: lng,
                accuracy: accuracy,
                speed: speed,
                heading: heading,
                order_id: orderId
            })
        })
        .then(res => res.json())
        .then(data => {
            const statusEl = document.getElementById('gps-broadcast-status');
            if (statusEl) {
                statusEl.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle px-3 py-2 rounded-pill"><i class="fa-solid fa-satellite-dish me-1 animate-pulse"></i> Live GPS Broadcasting (±${Math.round(accuracy)}m)</span>`;
            }
            if (data.arrived_order_ids && data.arrived_order_ids.includes(orderId)) {
                const arrivalAlert = document.getElementById('rider-arrival-alert');
                if (arrivalAlert) arrivalAlert.style.display = 'block';
            }
        })
        .catch(() => { /* silent retry */ });
    }

    // Poll for live Customer position updates
    function pollCustomerLiveLocation() {
        if (!orderLocationApiUrl) return;

        fetch(orderLocationApiUrl, { headers: { 'Accept': 'application/json' } })
            .then(res => res.json())
            .then(data => {
                if (data && data.customer && data.customer.latitude && data.customer.longitude) {
                    const newLat = data.customer.latitude;
                    const newLng = data.customer.longitude;

                    if (newLat !== customerLat || newLng !== customerLng) {
                        customerLat = newLat;
                        customerLng = newLng;

                        if (customerMarker) {
                            customerMarker.setLatLng([customerLat, customerLng]);
                        } else {
                            customerMarker = L.marker([customerLat, customerLng], {
                                icon: createCustomMarkerIcon('customer', 'Customer Live Location', 'Drop-off'),
                                zIndexOffset: 500
                            }).addTo(map);
                        }

                        updateRouteAndCalculations();

                        const custBadge = document.getElementById('customer-live-status-pill');
                        if (custBadge) {
                            custBadge.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle rounded-pill px-2 py-1"><i class="fa-solid fa-satellite-dish me-1 animate-pulse"></i> Customer Live Location Active</span>`;
                        }
                    }
                }
            })
            .catch(() => { /* silent fail */ });
    }

    // Start watching real device GPS
    function startRealGpsWatch() {
        if (!('geolocation' in navigator)) return;

        const statusEl = document.getElementById('gps-broadcast-status');
        if (statusEl) {
            statusEl.innerHTML = `<span class="badge bg-warning-subtle text-dark border border-warning-subtle px-3 py-2 rounded-pill"><i class="fa-solid fa-spinner fa-spin me-1"></i> Requesting GPS Access...</span>`;
        }

        activeWatchId = navigator.geolocation.watchPosition(
            (pos) => {
                const { latitude, longitude, accuracy, speed, heading } = pos.coords;
                updateRiderPosition(latitude, longitude, accuracy, speed, heading);
            },
            (err) => {
                if (statusEl) {
                    statusEl.innerHTML = `<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-3 py-2 rounded-pill"><i class="fa-solid fa-triangle-exclamation me-1"></i> GPS Denied/Offline (Simulation available)</span>`;
                }
            },
            { enableHighAccuracy: true, maximumAge: 3000, timeout: 10000 }
        );
    }

    // Auto-fit initial bounds
    const allPoints = [];
    if (customerLat && customerLng) allPoints.push([customerLat, customerLng]);
    if (currentRiderLat && currentRiderLng) allPoints.push([currentRiderLat, currentRiderLng]);
    if (farmLat && farmLng) allPoints.push([farmLat, farmLng]);
    if (allPoints.length > 0) {
        map.fitBounds(L.latLngBounds(allPoints), { padding: [60, 60], maxZoom: 15 });
        setTimeout(() => map.invalidateSize(), 250);
    }

    // Initial position render
    updateRiderPosition(currentRiderLat, currentRiderLng, 15);

    // ================= ACTION BUTTONS =================

    // 1. [ Start Delivery ]
    const startDeliveryBtn = document.getElementById('btn-start-delivery');
    if (startDeliveryBtn) {
        startDeliveryBtn.addEventListener('click', function(e) {
            e.preventDefault();
            this.disabled = true;
            this.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Starting Delivery...';

            fetch(startDeliveryUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                }
            })
            .catch(() => {
                document.getElementById('form-start-delivery')?.submit();
            });
        });
    }

    // 2. [ Navigate ] (Google Maps external turn-by-turn navigation)
    const navigateBtn = document.getElementById('btn-navigate');
    if (navigateBtn) {
        navigateBtn.addEventListener('click', function() {
            if (customerLat && customerLng) {
                const navUrl = `https://www.google.com/maps/dir/?api=1&origin=${currentRiderLat},${currentRiderLng}&destination=${customerLat},${customerLng}&travelmode=two-wheeler`;
                window.open(navUrl, '_blank', 'noopener,noreferrer');
            } else {
                alert('Customer delivery location coordinates are not available for direct navigation.');
            }
        });
    }

    // 3. [ Mark Delivered ] (OTP modal)
    const markDeliveredBtn = document.getElementById('btn-mark-delivered');
    if (markDeliveredBtn) {
        markDeliveredBtn.addEventListener('click', function() {
            const modalEl = document.getElementById('completeDeliveryModal');
            if (modalEl && window.bootstrap) {
                new bootstrap.Modal(modalEl).show();
            }
        });
    }

    // Sync My Real GPS Button Listener
    const syncRiderGpsBtn = document.getElementById('btn-sync-rider-gps');
    if (syncRiderGpsBtn) {
        syncRiderGpsBtn.addEventListener('click', function() {
            if (!('geolocation' in navigator)) {
                alert('Geolocation is not supported by your browser.');
                return;
            }
            syncRiderGpsBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Syncing GPS...';
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const { latitude, longitude, accuracy, speed, heading } = pos.coords;
                    updateRiderPosition(latitude, longitude, accuracy, speed || 0, heading || 0);
                    map.setView([latitude, longitude], 15, { animate: true });
                    syncRiderGpsBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Real GPS Synced';
                    setTimeout(() => {
                        syncRiderGpsBtn.innerHTML = '<i class="fa-solid fa-location-crosshairs me-1"></i> Sync My Real GPS';
                    }, 2500);
                },
                (err) => {
                    alert('Could not access device GPS. Please grant location permissions in your browser.');
                    syncRiderGpsBtn.innerHTML = '<i class="fa-solid fa-location-crosshairs me-1"></i> Sync My Real GPS';
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        });
    }

    // 4. Center Map
    const centerBtn = document.getElementById('btn-center-map');
    if (centerBtn) {
        centerBtn.addEventListener('click', function() {
            map.setView([currentRiderLat, currentRiderLng], 16, { animate: true });
        });
    }

    // 5. GPS Simulation Tool (Step along real road route!)
    const simStartBtn = document.getElementById('btn-sim-motion');
    if (simStartBtn) {
        let isSimulating = false;
        simStartBtn.addEventListener('click', function() {
            if (isSimulating) {
                clearInterval(simulationTimer);
                isSimulating = false;
                this.innerHTML = '<i class="fa-solid fa-play me-1"></i> Simulate Rider Motion';
                this.className = 'btn btn-outline-primary btn-sm rounded-pill';
                return;
            }

            if (!customerLat || !customerLng) return;
            isSimulating = true;
            this.innerHTML = '<i class="fa-solid fa-pause me-1"></i> Pause Simulation';
            this.className = 'btn btn-warning btn-sm rounded-pill';

            // If we have road coordinates, step along the road
            const roadPath = cachedRoadCoords.length > 5 ? cachedRoadCoords : null;
            let step = 0;
            const totalSteps = roadPath ? roadPath.length : 25;
            const startLat = currentRiderLat;
            const startLng = currentRiderLng;

            simulationTimer = setInterval(() => {
                step++;
                if (step >= totalSteps) {
                    clearInterval(simulationTimer);
                    isSimulating = false;
                    simStartBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Arrived at Customer!';
                    simStartBtn.className = 'btn btn-success btn-sm rounded-pill disabled';
                    updateRiderPosition(customerLat, customerLng, 5, 0, 0);
                    return;
                }

                let nextLat, nextLng;
                if (roadPath) {
                    nextLat = roadPath[step][0];
                    nextLng = roadPath[step][1];
                } else {
                    const progress = step / totalSteps;
                    nextLat = startLat + (customerLat - startLat) * progress;
                    nextLng = startLng + (customerLng - startLng) * progress;
                }

                updateRiderPosition(nextLat, nextLng, 8, 7.5, 45); // ~27 km/h
            }, 900);
        });
    }

    startRealGpsWatch();
    setInterval(pollCustomerLiveLocation, 3500);
}
