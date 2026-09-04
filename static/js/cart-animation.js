/**
 * cart-animation.js
 * Handles flying-dot animation, navbar badge update, and button "Added" state
 */
(function () {
    if (window._cartAnimationInitialized) return;
    window._cartAnimationInitialized = true;

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function triggerFlyingDot(sourceEl, targetEl, callback) {
        if (!sourceEl || !targetEl) {
            if (callback) callback();
            return;
        }

        const sourceRect = sourceEl.getBoundingClientRect();
        const targetRect = targetEl.getBoundingClientRect();

        const dot = document.createElement('div');
        dot.className = 'flying-dot';

        // Check if there is an image inside or nearby
        const parentCard = sourceEl.closest('.card, .row, .col-12, .col-md-6, .col-lg-3, .col-6') || document;
        const img = parentCard.querySelector('img') || document.getElementById('productMainImage') || document.querySelector('.ft-zoom-image');

        if (img && (img.src || img.currentSrc)) {
            dot.style.width = '48px';
            dot.style.height = '48px';
            dot.style.background = '#ffffff';
            dot.style.borderRadius = '50%';
            dot.style.overflow = 'hidden';
            dot.style.border = '2px solid #10b981';
            dot.style.boxShadow = '0 8px 20px rgba(16, 185, 129, 0.4)';
            dot.innerHTML = `<img src="${img.src || img.currentSrc}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
        }

        const dotW = img ? 48 : 20;
        const dotH = dotW;
        const startX = sourceRect.left + (sourceRect.width / 2) - (dotW / 2);
        const startY = sourceRect.top + (sourceRect.height / 2) - (dotH / 2);

        dot.style.left = startX + 'px';
        dot.style.top = startY + 'px';
        dot.style.opacity = '1';

        document.body.appendChild(dot);
        void dot.offsetWidth; // force reflow

        const endX = (targetRect.left + (targetRect.width / 2)) - (startX + (dotW / 2));
        const endY = (targetRect.top + (targetRect.height / 2)) - (startY + (dotH / 2));

        requestAnimationFrame(() => {
            dot.style.transform = `translate3d(${endX}px, ${endY}px, 0) scale(0.2) rotate(30deg)`;
            dot.style.opacity = '0.3';
        });

        setTimeout(() => {
            if (dot.parentNode) {
                dot.parentNode.removeChild(dot);
            }
            if (callback) callback();
        }, 600);
    }

    function updateBadgeAndAnimate(count) {
        const badges = document.querySelectorAll('#cartBadgeCount, .cart-badge, .cart-count-badge');
        badges.forEach(badge => {
            if (count !== undefined && count !== null) {
                badge.textContent = count;
            }
            badge.classList.remove('pulse', 'badge-pulse', 'badge-bounce');
            void badge.offsetWidth;
            badge.classList.add('badge-pulse');
            setTimeout(() => badge.classList.remove('pulse', 'badge-pulse', 'badge-bounce'), 600);
        });

        const iconWraps = document.querySelectorAll('#navCartIcon, .cart-icon-wrap');
        iconWraps.forEach(wrap => {
            wrap.classList.remove('bounce', 'cart-icon-bounce');
            void wrap.offsetWidth;
            wrap.classList.add('cart-icon-bounce');
            setTimeout(() => wrap.classList.remove('bounce', 'cart-icon-bounce'), 600);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.btn-add-cart');
            if (!btn) return;

            e.preventDefault();

            const productId = btn.dataset.productId;
            const variantId = btn.dataset.variantId || '';
            const addUrl = btn.dataset.addUrl || (productId ? `/orders/cart/add/${productId}/` : '/orders/cart/add/');

            // Quantity support
            const qtyInputId = btn.dataset.qtyInput;
            let quantity = 1;
            if (qtyInputId) {
                const qtyEl = document.getElementById(qtyInputId);
                if (qtyEl) quantity = parseInt(qtyEl.value) || 1;
            } else {
                const parent = btn.closest('.card, .row') || document;
                const qtyEl = parent.querySelector('.card-qty-input, input[name="quantity"], #qtyInput');
                if (qtyEl) quantity = parseInt(qtyEl.value) || 1;
            }

            const navCartTarget = document.getElementById('navCartIcon') || document.querySelector('.cart-icon-wrap') || document.getElementById('cartBadgeCount');

            // Trigger flying dot
            triggerFlyingDot(btn, navCartTarget, function () {
                updateBadgeAndAnimate();
            });

            // Prepare POST body
            const formData = new FormData();
            if (variantId) formData.append('variant_id', variantId);
            formData.append('quantity', quantity);

            const csrfToken = getCookie('csrftoken') || (document.querySelector('meta[name="csrf-token"]') ? document.querySelector('meta[name="csrf-token"]').content : '');

            fetch(addUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: formData,
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok' || data.success === true) {
                    const newCount = data.cart_count !== undefined ? data.cart_count : data.total_items;
                    updateBadgeAndAnimate(newCount);

                    if (data.items && window.renderNavCartDropdown) {
                        window.renderNavCartDropdown(data.items, newCount, data.cart_subtotal, productId);
                    }
                    if (window.openNavCartDropdown) {
                        setTimeout(() => window.openNavCartDropdown(4500), 500);
                    }

                    btn.classList.add('is-added', 'btn-cart-added');
                    btn.disabled = true;

                    setTimeout(() => {
                        btn.classList.remove('is-added', 'btn-cart-added');
                        btn.disabled = false;
                    }, 1800);
                } else {
                    alert(data.error || 'Could not add item to cart.');
                }
            })
            .catch(err => {
                console.error('Cart animation add error:', err);
            });
        });
    });
})();
