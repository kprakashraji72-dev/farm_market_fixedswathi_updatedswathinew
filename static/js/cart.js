// Fresh Trace — Add to Cart (AJAX) + Increase/Decrease Quantity (AJAX) + Dynamic Navbar Cart Dropdown

(function () {
    if (window._ftCartInitialized) return;
    window._ftCartInitialized = true;

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content && meta.content !== 'NOTPROVIDED') {
            return meta.content;
        }
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        if (match) {
            return decodeURIComponent(match[1]);
        }
        const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function updateCartBadge(count) {
        const badges = document.querySelectorAll('.cart-count-badge, .navbar .badge.bg-success');
        badges.forEach(badge => {
            badge.textContent = count;
            badge.classList.remove('badge-bounce');
            void badge.offsetWidth; // force reflow
            badge.classList.add('badge-bounce');
            setTimeout(() => badge.classList.remove('badge-bounce'), 700);
        });

        const countEls = document.querySelectorAll('.dropdown-cart-count');
        countEls.forEach(el => el.textContent = count);
    }
    window.updateCartBadge = updateCartBadge;

    function renderNavCartDropdown(items, count, subtotal, latestProductId = null) {
        updateCartBadge(count);

        const emptyContainer = document.getElementById('nav-cart-empty');
        const itemsWrapper = document.getElementById('nav-cart-items-wrapper');
        const listContainer = document.getElementById('nav-cart-items-list');
        const subtotalEl = document.getElementById('nav-cart-subtotal-val');

        if (!items || items.length === 0 || count === 0) {
            if (emptyContainer) emptyContainer.classList.remove('d-none');
            if (itemsWrapper) itemsWrapper.classList.add('d-none');
            return;
        }

        if (emptyContainer) emptyContainer.classList.add('d-none');
        if (itemsWrapper) itemsWrapper.classList.remove('d-none');
        if (subtotalEl && subtotal) subtotalEl.textContent = subtotal;

        if (listContainer) {
            let html = '';
            items.forEach(item => {
                const isNew = latestProductId && String(item.product_id || item.id) === String(latestProductId);
                const imgHtml = item.image_url
                    ? `<img src="${item.image_url}" alt="${item.name}" class="rounded-3 border flex-shrink-0" style="width: 44px; height: 44px; object-fit: cover;">`
                    : `<div class="rounded-3 bg-light border d-flex align-items-center justify-content-center flex-shrink-0 text-muted" style="width: 44px; height: 44px;"><i class="fa-solid fa-leaf text-success"></i></div>`;

                const farmHtml = item.farm_name
                    ? `<div class="text-muted extra-small text-truncate"><i class="fa-solid fa-wheat-awn text-success me-1"></i>${item.farm_name}</div>`
                    : '';

                html += `
                <div class="d-flex align-items-center gap-2.5 p-2 border-bottom border-light rounded-3 position-relative nav-cart-item ${isNew ? 'nav-cart-item-new' : ''}" data-item-key="${item.key}" style="transition: background 0.2s ease;">
                    ${imgHtml}
                    <div class="flex-grow-1 min-w-0" style="min-width: 0;">
                        <h6 class="mb-0 text-dark small text-truncate fw-semibold lh-sm" title="${item.name}">${item.name}</h6>
                        ${farmHtml}
                        <div class="d-flex align-items-center justify-content-between mt-1">
                            <span class="text-muted extra-small">${item.quantity} × ₹${item.unit_price}</span>
                            <span class="fw-bold text-success small">₹${item.line_total}</span>
                        </div>
                    </div>
                </div>`;
            });
            listContainer.innerHTML = html;
        }
    }
    window.renderNavCartDropdown = renderNavCartDropdown;

    function openNavCartDropdown(autoCloseDelay = 4500) {
        const dropdownBtn = document.getElementById('navCartDropdownBtn');
        if (!dropdownBtn) return;
        if (window.bootstrap && bootstrap.Dropdown) {
            const bsDropdown = bootstrap.Dropdown.getOrCreateInstance(dropdownBtn);
            bsDropdown.show();
            if (autoCloseDelay > 0) {
                clearTimeout(window._cartDropdownTimeout);
                window._cartDropdownTimeout = setTimeout(() => {
                    bsDropdown.hide();
                }, autoCloseDelay);
            }
        }
    }
    window.openNavCartDropdown = openNavCartDropdown;

    function flyDropToCart(startElement) {
        const cartTarget = document.getElementById('navCartDropdownBtn') 
            || document.querySelector('.navbar .fa-cart-shopping') 
            || document.querySelector('.cart-count-badge');
            
        if (!startElement || !cartTarget) return;

        // Find the best image element inside card or container
        let imgSource = null;
        if (startElement.tagName === 'IMG') {
            imgSource = startElement;
        } else {
            const parentCard = startElement.closest('.card, .row, .col-12, .col-md-6, .col-lg-3, .col-6, .ft-cart-card') || document;
            imgSource = parentCard.querySelector('img') || document.getElementById('productMainImage') || document.querySelector('.ft-zoom-image');
        }

        const sourceRect = (imgSource && imgSource.getBoundingClientRect().width > 0)
            ? imgSource.getBoundingClientRect()
            : startElement.getBoundingClientRect();

        const cartRect = cartTarget.getBoundingClientRect();

        const flyer = document.createElement('div');
        flyer.className = 'flying-cart-item';
        
        if (imgSource && imgSource.tagName === 'IMG' && (imgSource.src || imgSource.currentSrc)) {
            flyer.innerHTML = `<img src="${imgSource.src || imgSource.currentSrc}" alt="Produce" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
        } else {
            flyer.innerHTML = `<div style="width:100%;height:100%;background:#10b981;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:1.25rem;"><i class="fa-solid fa-basket-shopping"></i></div>`;
        }

        const startW = Math.min(70, Math.max(50, sourceRect.width * 0.45));
        const startH = startW;
        const startX = sourceRect.left + (sourceRect.width / 2) - (startW / 2);
        const startY = sourceRect.top + (sourceRect.height / 2) - (startH / 2);

        flyer.style.top = startY + 'px';
        flyer.style.left = startX + 'px';
        flyer.style.width = startW + 'px';
        flyer.style.height = startH + 'px';
        flyer.style.opacity = '1';

        document.body.appendChild(flyer);
        void flyer.offsetWidth; // force reflow

        const endX = (cartRect.left + (cartRect.width / 2)) - (startX + (startW / 2));
        const endY = (cartRect.top + (cartRect.height / 2)) - (startY + (startH / 2));

        requestAnimationFrame(() => {
            flyer.style.transform = `translate3d(${endX}px, ${endY}px, 0) scale(0.2) rotate(35deg)`;
            flyer.style.opacity = '0.3';
        });

        setTimeout(() => {
            if (flyer.parentNode) {
                flyer.parentNode.removeChild(flyer);
            }

            // Trigger cart bounce upon drop
            const navCartIcon = document.querySelector('.navbar .fa-cart-shopping');
            if (navCartIcon) {
                navCartIcon.classList.remove('cart-icon-bounce');
                void navCartIcon.offsetWidth;
                navCartIcon.classList.add('cart-icon-bounce');
                setTimeout(() => navCartIcon.classList.remove('cart-icon-bounce'), 700);
            }

            const badges = document.querySelectorAll('.cart-count-badge, .navbar .badge.bg-success');
            badges.forEach(b => {
                b.classList.remove('badge-bounce');
                void b.offsetWidth;
                b.classList.add('badge-bounce');
                setTimeout(() => b.classList.remove('badge-bounce'), 700);
            });
        }, 650);
    }
    window.flyDropToCart = flyDropToCart;

    document.addEventListener('click', function (e) {
        // --- Add to Cart ---
        const addBtn = e.target.closest('.add-to-cart-btn');
        if (addBtn) {
            const productId = addBtn.dataset.productId;
            if (!productId) return;

            const qtyInputId = addBtn.dataset.qtyInput;
            const quantity = qtyInputId ? (document.getElementById(qtyInputId)?.value || 1) : 1;

            let body = `quantity=${encodeURIComponent(quantity)}`;
            const variantGroupName = addBtn.dataset.variantSelect;
            if (variantGroupName) {
                const checked = document.querySelector(`input[name="${variantGroupName}"]:checked`);
                if (!checked) {
                    alert('Please choose a size/weight option.');
                    return;
                }
                body += `&variant_id=${encodeURIComponent(checked.value)}`;
            }

            // Trigger flying drop-into-cart animation immediately
            flyDropToCart(addBtn);

            // Save original button state
            const originalHtml = addBtn.innerHTML;
            const originalDisabled = addBtn.disabled;
            addBtn.disabled = true;

            const csrfToken = getCsrfToken();

            fetch(`/orders/cart/add/${productId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: body,
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Button transition to "✓ Added"
                    addBtn.classList.add('btn-cart-added');
                    addBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Added';

                    // Update navbar badge & mini dropdown data
                    if (data.items) {
                        renderNavCartDropdown(data.items, data.cart_count, data.cart_subtotal, productId);
                    } else {
                        updateCartBadge(data.cart_count);
                    }

                    // Open the mini-cart dropdown action preview right as drop animation lands
                    setTimeout(() => {
                        openNavCartDropdown(4500);
                    }, 500);

                    // Revert button after 1.8 seconds
                    setTimeout(() => {
                        addBtn.classList.remove('btn-cart-added');
                        addBtn.innerHTML = originalHtml;
                        addBtn.disabled = originalDisabled;
                    }, 1800);
                } else {
                    addBtn.innerHTML = originalHtml;
                    addBtn.disabled = originalDisabled;
                    alert(data.error || 'Could not add to cart.');
                }
            })
            .catch(err => {
                console.error('Cart add error:', err);
                addBtn.innerHTML = originalHtml;
                addBtn.disabled = originalDisabled;
            });
        }

        // --- Quantity +/- on the Cart page ---
        const qtyBtn = e.target.closest('.qty-btn');
        if (qtyBtn) {
            const productId = qtyBtn.dataset.productId;
            const action = qtyBtn.dataset.action; // 'increase' | 'decrease'

            fetch(`/orders/cart/update/${productId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `action=${encodeURIComponent(action)}`,
            })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    alert(data.error || 'Could not update quantity.');
                    return;
                }
                updateCartBadge(data.cart_count);
                if (data.items) {
                    renderNavCartDropdown(data.items, data.cart_count, data.cart_subtotal);
                }

                const subtotalEl = document.getElementById('cart-subtotal');
                if (subtotalEl) subtotalEl.textContent = data.cart_subtotal;
                const totalDisplay = document.getElementById('cart-total-display');
                if (totalDisplay) totalDisplay.textContent = data.cart_subtotal;

                if (data.removed) {
                    document.querySelectorAll(`[data-product-row="${productId}"]`).forEach(el => el.remove());
                    maybeShowEmptyCart();
                    return;
                }
                document.querySelectorAll(`.qty-value[data-product-id="${productId}"]`).forEach(el => {
                    el.textContent = data.quantity;
                });
                document.querySelectorAll(`.line-total[data-product-id="${productId}"]`).forEach(el => {
                    el.textContent = `₹${data.line_total}`;
                });
            })
            .catch(err => console.error('Cart update error:', err));
        }

        // --- Product Card Quantity Stepper (- 1 +) ---
        const minusBtn = e.target.closest('.card-qty-minus');
        if (minusBtn) {
            e.preventDefault();
            e.stopPropagation();
            const targetId = minusBtn.dataset.target;
            const input = targetId ? document.getElementById(targetId) : minusBtn.parentElement?.querySelector('input');
            const valSpan = targetId ? document.getElementById('val-' + targetId) : minusBtn.parentElement?.querySelector('.card-qty-val');
            if (input) {
                let val = parseInt(input.value) || 1;
                if (val > 1) {
                    val -= 1;
                    input.value = val;
                    if (valSpan) valSpan.textContent = val;
                }
            }
            return;
        }

        const plusBtn = e.target.closest('.card-qty-plus');
        if (plusBtn) {
            e.preventDefault();
            e.stopPropagation();
            const targetId = plusBtn.dataset.target;
            const input = targetId ? document.getElementById(targetId) : plusBtn.parentElement?.querySelector('input');
            const valSpan = targetId ? document.getElementById('val-' + targetId) : plusBtn.parentElement?.querySelector('.card-qty-val');
            if (input) {
                let val = parseInt(input.value) || 1;
                let max = parseInt(input.max) || 999;
                if (val < max) {
                    val += 1;
                    input.value = val;
                    if (valSpan) valSpan.textContent = val;
                }
            }
            return;
        }

        // --- Remove from Cart ---
        const removeBtn = e.target.closest('.remove-btn');
        if (removeBtn) {
            const productId = removeBtn.dataset.productId;
            fetch(`/orders/cart/remove/${productId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
            .then(res => res.json())
            .then(data => {
                if (!data.success) return;
                updateCartBadge(data.cart_count);
                if (data.items) {
                    renderNavCartDropdown(data.items, data.cart_count, data.cart_subtotal);
                }
                const subtotalEl = document.getElementById('cart-subtotal');
                if (subtotalEl) subtotalEl.textContent = data.cart_subtotal;
                const totalDisplay = document.getElementById('cart-total-display');
                if (totalDisplay) totalDisplay.textContent = data.cart_subtotal;
                document.querySelectorAll(`[data-product-row="${productId}"]`).forEach(el => el.remove());
                maybeShowEmptyCart();
            })
            .catch(err => console.error('Cart remove error:', err));
        }
    });

    function maybeShowEmptyCart() {
        const container = document.getElementById('cart-items-body');
        if (container && container.querySelectorAll('[data-product-row]').length === 0) {
            document.getElementById('cart-table-wrapper')?.classList.add('d-none');
            document.getElementById('cart-empty-msg')?.classList.remove('d-none');
        }
    }
})();

