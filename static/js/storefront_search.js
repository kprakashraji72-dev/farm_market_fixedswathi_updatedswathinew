/**
 * Fresh Trace Storefront Live Typeahead Search
 */
document.addEventListener('DOMContentLoaded', function () {
    const searchInputs = document.querySelectorAll('input[name="q"], .ft-store-search-input');

    searchInputs.forEach(input => {
        let dropdown = document.createElement('div');
        dropdown.className = 'ft-search-dropdown shadow-lg';
        dropdown.style.display = 'none';
        dropdown.style.position = 'absolute';
        dropdown.style.top = '100%';
        dropdown.style.left = '0';
        dropdown.style.right = '0';
        dropdown.style.zIndex = '1050';
        dropdown.style.backgroundColor = '#ffffff';
        dropdown.style.borderRadius = '0.75rem';
        dropdown.style.border = '1px solid #e2e8f0';
        dropdown.style.marginTop = '6px';
        dropdown.style.maxHeight = '360px';
        dropdown.style.overflowY = 'auto';

        const parent = input.parentElement;
        if (getComputedStyle(parent).position === 'static') {
            parent.style.position = 'relative';
        }
        parent.appendChild(dropdown);

        let debounceTimer = null;

        input.addEventListener('input', function () {
            const query = input.value.trim();
            clearTimeout(debounceTimer);

            if (query.length < 2) {
                dropdown.style.display = 'none';
                dropdown.innerHTML = '';
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/search-suggest/?q=${encodeURIComponent(query)}`);
                    if (res.ok) {
                        const data = await res.json();
                        renderResults(data.results || [], dropdown, query);
                    }
                } catch (err) {
                    console.error('Search suggest error:', err);
                }
            }, 180);
        });

        // Hide dropdown when clicking outside
        document.addEventListener('click', function (e) {
            if (!parent.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });

        // Focus again
        input.addEventListener('focus', function () {
            if (dropdown.children.length > 0 && input.value.trim().length >= 2) {
                dropdown.style.display = 'block';
            }
        });
    });

    function renderResults(results, dropdown, query) {
        if (!results || results.length === 0) {
            dropdown.innerHTML = `
                <div class="p-3 text-center text-muted" style="font-size: 0.85rem;">
                    No fresh produce found matching "<strong>${escapeHtml(query)}</strong>"
                </div>
            `;
            dropdown.style.display = 'block';
            return;
        }

        let html = '<div class="list-group list-group-flush rounded-3">';
        results.forEach(item => {
            html += `
                <a href="${item.url}" class="list-group-item list-group-item-action d-flex align-items-center justify-content-between p-2.5" style="font-size: 0.88rem; border-color: #f1f5f9;">
                    <div class="d-flex align-items-center gap-2.5">
                        <img src="${item.image_url}" alt="${escapeHtml(item.name)}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 0.5rem; border: 1px solid #e2e8f0;">
                        <div>
                            <div class="fw-semibold text-dark mb-0">${escapeHtml(item.name)}</div>
                            <div class="extra-small text-muted">${escapeHtml(item.farm)} • <span class="text-success">${escapeHtml(item.category)}</span></div>
                        </div>
                    </div>
                    <div class="text-end">
                        <div class="fw-bold text-success">${escapeHtml(item.price_formatted)} <span class="text-muted extra-small">/${escapeHtml(item.unit)}</span></div>
                        ${item.in_stock ? '<span class="badge bg-success-subtle text-success extra-small">In Stock</span>' : '<span class="badge bg-secondary-subtle text-muted extra-small">Out of Stock</span>'}
                    </div>
                </a>
            `;
        });
        html += '</div>';

        dropdown.innerHTML = html;
        dropdown.style.display = 'block';
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text).replace(/[&<>"']/g, function (m) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
        });
    }
});
