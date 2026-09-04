
// Fresh Trace — global JS helpers shared by cart.js / tracking.js / checkout.js

function getCookie(name) {
    const cookies = document.cookie.split(';').map(c => c.trim());
    const match = cookies.find(c => c.startsWith(name + '='));
    return match ? decodeURIComponent(match.split('=')[1]) : null;
}

const CSRF_TOKEN = getCookie('csrftoken');

function showToast(message, isError = false) {
    // Suppress success toasts for cart additions to avoid popup banners
    if (!isError && typeof message === 'string' && message.toLowerCase().includes('cart')) {
        return;
    }
    const el = document.createElement('div');
    el.className = `alert alert-${isError ? 'danger' : 'success'} position-fixed top-0 end-0 m-3 shadow ft-toast`;
    el.style.zIndex = 2050;
    el.innerHTML = `<i class="fa-solid ${isError ? 'fa-circle-xmark' : 'fa-circle-check'} me-2"></i>${message}`;
    document.body.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, 2500);
}

// ---------------------------------------------------------
// Mobile sidebar toggle — Handles .ft-sidebar (driver,
// farmer, admin, employee) responsive drawer on mobile.
// Also handles backdrop, close buttons, and escape key.
// ---------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    initSidebarDrawer();

    // ---------------------------------------------------------
    // 1. Scroll Reveal IntersectionObserver
    // ---------------------------------------------------------
    initScrollReveal();

    // ---------------------------------------------------------
    // 2. Product Detail Image Zoom Lens
    // ---------------------------------------------------------
    initProductImageZoom();
});

function initSidebarDrawer() {
    const sidebar = document.querySelector('.ft-sidebar');
    if (!sidebar) return;

    // Create backdrop if not present
    let backdrop = document.querySelector('.ft-sidebar-backdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.className = 'ft-sidebar-backdrop';
        // Ensure backdrop sits above Leaflet map tiles (z-index 400) but below sidebar (1060)
        backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.35);z-index:1055;opacity:0;visibility:hidden;transition:opacity 0.3s ease,visibility 0.3s ease;cursor:pointer;';
        document.body.appendChild(backdrop);
    }

    function openSidebar() {
        sidebar.classList.add('ft-sidebar-open');
        backdrop.style.opacity = '1';
        backdrop.style.visibility = 'visible';
        document.body.classList.add('overflow-hidden');
    }

    function closeSidebar() {
        sidebar.classList.remove('ft-sidebar-open');
        backdrop.style.opacity = '0';
        backdrop.style.visibility = 'hidden';
        document.body.classList.remove('overflow-hidden');
    }

    function toggleSidebar() {
        if (sidebar.classList.contains('ft-sidebar-open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    }

    // ── Attach direct listeners to ALL toggle buttons on the page ──
    const TOGGLE_SELECTORS = [
        '.ft-sidebar-toggle',
        '.ft-sidebar-toggle-btn',
        '#sidebarToggleTop',
        '#btn-toggle-driver-menu',
        '[data-ft-sidebar-toggle]'
    ];

    function attachToggleListeners() {
        TOGGLE_SELECTORS.forEach(selector => {
            document.querySelectorAll(selector).forEach(btn => {
                if (!btn._ftSidebarBound) {
                    btn._ftSidebarBound = true;
                    btn.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        toggleSidebar();
                    });
                }
            });
        });
    }

    // Run immediately and again after a short delay (for dynamically rendered buttons)
    attachToggleListeners();
    setTimeout(attachToggleListeners, 300);

    // ── Close button inside sidebar ──
    document.querySelectorAll('.ft-sidebar-close').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            closeSidebar();
        });
    });

    // ── Click outside on backdrop ──
    backdrop.addEventListener('click', closeSidebar);

    // ── Escape key ──
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar.classList.contains('ft-sidebar-open')) {
            closeSidebar();
        }
    });
}

/* =========================================================
   SCROLL REVEAL OBSERVER
   ========================================================= */
function initScrollReveal() {
    const reveals = document.querySelectorAll('.reveal-on-scroll');
    if (!reveals.length) return;

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-revealed');
                    obs.unobserve(entry.target);
                }
            });
        }, {
            root: null,
            threshold: 0.12,
            rootMargin: '0px 0px -40px 0px'
        });

        reveals.forEach(el => observer.observe(el));
    } else {
        // Fallback if IntersectionObserver not supported
        reveals.forEach(el => el.classList.add('is-revealed'));
    }
}

/* =========================================================
   INTERACTIVE PRODUCT IMAGE ZOOM LENS
   ========================================================= */
function initProductImageZoom() {
    const zoomContainers = document.querySelectorAll('.ft-zoom-container');
    zoomContainers.forEach(container => {
        const img = container.querySelector('.ft-zoom-image');
        if (!img) return;

        container.addEventListener('mousemove', function (e) {
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const xPercent = (x / rect.width) * 100;
            const yPercent = (y / rect.height) * 100;

            img.style.transformOrigin = `${xPercent}% ${yPercent}%`;
        });

        container.addEventListener('mouseleave', function () {
            img.style.transformOrigin = 'center center';
        });
    });
}

/* =========================================================
   GLOBAL CART & TOAST HELPERS
   ========================================================= */
function updateCartBadge(count) {
    const badges = document.querySelectorAll('.cart-count-badge, .navbar .badge.bg-success');
    badges.forEach(badge => {
        badge.textContent = count;
        badge.classList.remove('badge-bounce');
        void badge.offsetWidth; // trigger reflow
        badge.classList.add('badge-bounce');
        setTimeout(() => badge.classList.remove('badge-bounce'), 700);
    });
}
window.updateCartBadge = updateCartBadge;