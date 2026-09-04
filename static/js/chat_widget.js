/**
 * Fresh Trace AI Storefront Assistant Widget
 */
document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('ftAiToggleBtn');
    const closeBtn = document.getElementById('ftAiCloseBtn');
    const clearBtn = document.getElementById('ftAiClearBtn');
    const panel = document.getElementById('ftAiPanel');
    const icon = document.getElementById('ftAiIcon');
    const form = document.getElementById('ftAiForm');
    const input = document.getElementById('ftAiInput');
    const messagesContainer = document.getElementById('ftAiMessages');
    const chipsContainer = document.getElementById('ftAiChips');

    if (!toggleBtn || !panel || !form) return;

    // Helper to get CSRF token
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    // Toggle Chat Window
    toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (panel.style.display === 'flex') {
            panel.style.display = 'none';
            icon.className = 'fa-solid fa-robot';
        } else {
            panel.style.display = 'flex';
            icon.className = 'fa-solid fa-xmark';
            input.focus();
            scrollToBottom();
        }
    });

    closeBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        panel.style.display = 'none';
        icon.className = 'fa-solid fa-robot';
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
        if (panel.style.display === 'flex' && !panel.contains(e.target) && !toggleBtn.contains(e.target)) {
            panel.style.display = 'none';
            icon.className = 'fa-solid fa-robot';
        }
    });

    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    // Format simple markdown into HTML
    function formatMarkdown(text) {
        if (!text) return '';
        let escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Bold **text**
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Italic *text*
        escaped = escaped.replace(/\*(.*?)\*/g, '<em>$1</em>');
        // Line breaks
        escaped = escaped.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
        return escaped;
    }

    // Append Message
    function appendMessage(sender, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `ft-msg ${sender === 'user' ? 'ft-msg-user' : 'ft-msg-bot'}`;
        if (sender === 'user') {
            msgDiv.textContent = text;
        } else {
            msgDiv.innerHTML = formatMarkdown(text);
        }
        messagesContainer.appendChild(msgDiv);
        scrollToBottom();
        return msgDiv;
    }

    // Show Typing Indicator
    function showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'ftTypingIndicator';
        indicator.className = 'ft-msg ft-msg-bot ft-typing-dots';
        indicator.innerHTML = '<span class="ft-typing-dot"></span><span class="ft-typing-dot"></span><span class="ft-typing-dot"></span>';
        messagesContainer.appendChild(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('ftTypingIndicator');
        if (indicator) indicator.remove();
    }

    // Send Message
    async function sendMessage(text) {
        if (!text || !text.trim()) return;
        const cleanText = text.trim();
        appendMessage('user', cleanText);
        input.value = '';
        showTypingIndicator();

        try {
            const res = await fetch('/chat/message/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ message: cleanText })
            });

            removeTypingIndicator();

            if (res.ok) {
                const data = await res.json();
                appendMessage('bot', data.reply || 'Here is what I found for you.');

                // If cart was updated, sync cart badge count
                if (data.cart_count !== undefined) {
                    const badges = document.querySelectorAll('#cartBadge, .cart-badge-count');
                    badges.forEach(badge => {
                        badge.textContent = data.cart_count;
                        badge.classList.remove('d-none');
                    });
                }
            } else {
                appendMessage('bot', "I'm having a little trouble connecting right now. Please try again in a moment!");
            }
        } catch (err) {
            removeTypingIndicator();
            appendMessage('bot', "Network error. Please check your connection and try again.");
            console.error('Chat error:', err);
        }
    }

    // Submit handler
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        sendMessage(input.value);
    });

    // Chip click handlers
    if (chipsContainer) {
        chipsContainer.addEventListener('click', function (e) {
            const btn = e.target.closest('.ft-chip-btn');
            if (btn) {
                const query = btn.getAttribute('data-query');
                if (query) {
                    sendMessage(query);
                }
            }
        });
    }

    // Clear Chat
    if (clearBtn) {
        clearBtn.addEventListener('click', async function (e) {
            e.stopPropagation();
            try {
                await fetch('/chat/clear/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                messagesContainer.innerHTML = `
                    <div class="ft-msg ft-msg-bot">
                        Conversation cleared! 🌿 How can I help you find fresh organic produce today?
                    </div>
                `;
            } catch (err) {
                console.error('Clear chat error:', err);
            }
        });
    }
});
