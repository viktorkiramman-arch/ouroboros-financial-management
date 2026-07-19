(function () {
    'use strict';

    function $(selector, root) { return (root || document).querySelector(selector); }
    function $all(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    function csrf() { return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''; }
    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, function (ch) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[ch];
        });
    }

    var root = document.documentElement;
    var shell = $('#appShell');
    var storedCollapsed = localStorage.getItem('ouroboros-sidebar-collapsed') === '1';
    if (shell && storedCollapsed) shell.classList.add('sidebar-collapsed');

    $all('[data-toggle-sidebar]').forEach(function (button) {
        button.addEventListener('click', function () {
            if (!shell) return;
            if (window.matchMedia('(max-width: 820px)').matches) {
                shell.classList.toggle('sidebar-open');
                return;
            }
            shell.classList.toggle('sidebar-collapsed');
            localStorage.setItem('ouroboros-sidebar-collapsed', shell.classList.contains('sidebar-collapsed') ? '1' : '0');
        });
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (form && form.matches('form[data-confirm]')) {
            var message = form.getAttribute('data-confirm') || 'Continue?';
            if (!window.confirm(message)) event.preventDefault();
        }
    });

    var Currency = {
        base: root.dataset.baseCurrency || 'USD',
        baseSymbol: root.dataset.baseSymbol || '$',
        display: root.dataset.displayCurrency || root.dataset.baseCurrency || 'USD',
        displaySymbol: root.dataset.displaySymbol || root.dataset.baseSymbol || '$',
        rate: 1,
        source: 'local',
        online: navigator.onLine,
        ready: false,
        format: function (amount, symbol, code) {
            var sign = amount < 0 ? '-' : '';
            var abs = Math.abs(Number(amount || 0));
            var formatted = abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            var suffix = code && code !== 'USD' ? ' ' + code : '';
            return sign + (symbol || '') + formatted + suffix;
        },
        fromCents: function (cents) {
            return (Number(cents || 0) / 100) * this.rate;
        },
        moneyFromCents: function (cents) {
            var symbol = this.ready ? this.displaySymbol : this.baseSymbol;
            var code = this.ready ? this.display : this.base;
            var value = this.ready ? this.fromCents(cents) : Number(cents || 0) / 100;
            return this.format(value, symbol, code);
        },
        convertNumber: function (value) {
            return Number(value || 0) * (this.ready ? this.rate : 1);
        },
        apply: function () {
            var self = this;
            $all('[data-money-cents]').forEach(function (node) {
                node.textContent = self.moneyFromCents(node.getAttribute('data-money-cents'));
            });
            var pill = $('[data-fx-pill]');
            if (pill) {
                if (this.base === this.display) {
                    pill.textContent = this.base + ' values';
                } else if (this.ready) {
                    pill.textContent = this.base + ' converted live to ' + this.display + ' · rate ' + Number(this.rate).toFixed(4);
                } else {
                    pill.textContent = this.base + ' values · waiting for live ' + this.display;
                }
            }
        },
        load: function () {
            var self = this;
            if (this.base === this.display) {
                this.rate = 1;
                this.ready = true;
                this.apply();
                window.dispatchEvent(new CustomEvent('currency:updated', { detail: this }));
                return;
            }
            if (!navigator.onLine) {
                this.ready = false;
                this.apply();
                return;
            }
            fetch('/api/currency/rate?base=' + encodeURIComponent(this.base) + '&target=' + encodeURIComponent(this.display), { credentials: 'same-origin' })
                .then(function (response) { return response.json().then(function (json) { return { ok: response.ok, json: json }; }); })
                .then(function (result) {
                    if (!result.ok || !result.json.ok) throw new Error(result.json.error || 'Rate unavailable');
                    self.rate = Number(result.json.rate || 1);
                    self.displaySymbol = result.json.symbol || self.displaySymbol;
                    self.source = result.json.cached ? 'cached' : result.json.provider;
                    self.ready = true;
                    self.apply();
                    window.dispatchEvent(new CustomEvent('currency:updated', { detail: self }));
                    window.dispatchEvent(new Event('finance:rerender'));
                })
                .catch(function () {
                    self.ready = false;
                    self.apply();
                });
        }
    };
    window.FinanceCurrency = Currency;

    function updateOnlineStatus() {
        var online = navigator.onLine;
        Currency.online = online;
        $all('[data-online-card]').forEach(function (card) {
            card.classList.toggle('online', online);
            card.classList.toggle('offline', !online);
            var label = $('[data-online-label]', card);
            var detail = $('[data-online-detail]', card);
            if (label) label.textContent = online ? 'Online features ready' : 'Offline mode';
            if (detail) detail.textContent = online ? 'Live currency and optional web features can run.' : 'Local data still works. No cloud save is used.';
        });
        $all('[data-online-label]').forEach(function (label) { label.textContent = online ? 'Online' : 'Offline'; });
        if (online) Currency.load();
        else Currency.apply();
    }
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);

    function mountVirtualTransactions(container) {
        var scriptId = container.getAttribute('data-source');
        var script = document.getElementById(scriptId);
        var rows = [];
        try { rows = JSON.parse(script ? script.textContent : '[]'); } catch (_) { rows = []; }
        var scroll = $('.virtual-scroll', container);
        var spacer = $('.virtual-spacer', container);
        var win = $('.virtual-window', container);
        var countNode = $('[data-virtual-count]', container);
        var rowHeight = Number(container.getAttribute('data-row-height') || 58);
        var buffer = 8;
        if (countNode) countNode.textContent = rows.length.toLocaleString() + ' row(s)';
        if (!scroll || !spacer || !win) return;
        spacer.style.height = (rows.length * rowHeight) + 'px';

        function rowHtml(row) {
            var amountClass = row.is_income ? 'positive' : 'negative';
            return '<div class="virtual-row" style="height:' + rowHeight + 'px">' +
                '<div class="virtual-cell">' + escapeHtml(row.date) + '</div>' +
                '<div class="virtual-cell"><strong>' + escapeHtml(row.description) + '</strong></div>' +
                '<div class="virtual-cell"><span class="pill">' + escapeHtml(row.category) + '</span></div>' +
                '<div class="virtual-cell">' + escapeHtml(row.member || 'Unassigned') + '</div>' +
                '<div class="virtual-cell right ' + amountClass + '"><span data-money-cents="' + Number(row.amount_cents || 0) + '"></span></div>' +
                '<div class="virtual-cell virtual-actions"><a href="' + escapeHtml(row.edit_url) + '">Edit</a>' +
                '<form method="post" action="' + escapeHtml(row.delete_url) + '" data-confirm="Delete this transaction?">' +
                '<input type="hidden" name="csrf_token" value="' + escapeHtml(csrf()) + '">' +
                '<button class="link-button danger" type="submit">Delete</button></form></div>' +
                '</div>';
        }

        function render() {
            var top = scroll.scrollTop;
            var height = scroll.clientHeight || 560;
            var start = Math.max(0, Math.floor(top / rowHeight) - buffer);
            var end = Math.min(rows.length, Math.ceil((top + height) / rowHeight) + buffer);
            var html = '';
            for (var i = start; i < end; i += 1) html += rowHtml(rows[i]);
            win.style.transform = 'translateY(' + (start * rowHeight) + 'px)';
            win.innerHTML = html || '<div class="empty-state">No transactions to show.</div>';
            Currency.apply();
        }
        scroll.addEventListener('scroll', function () { requestAnimationFrame(render); });
        window.addEventListener('resize', render);
        window.addEventListener('currency:updated', render);
        render();
    }

    function mountChat() {
        var form = $('#advisorForm');
        var input = $('#advisorInput');
        var log = $('#advisorLog');
        if (!form || !input || !log) return;
        function addMessage(text, who) {
            var div = document.createElement('div');
            div.className = 'chat-message ' + who;
            div.textContent = text;
            log.appendChild(div);
            log.scrollTop = log.scrollHeight;
        }
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            var message = input.value.trim();
            if (!message) return;
            input.value = '';
            addMessage(message, 'user');
            addMessage('Thinking locally...', 'ai');
            var pending = log.lastElementChild;
            fetch('/api/advisor/chat', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
                body: JSON.stringify({ message: message })
            }).then(function (response) { return response.json(); })
              .then(function (data) { pending.textContent = data.ok ? data.reply : (data.error || 'I could not answer that.'); })
              .catch(function () { pending.textContent = 'Ouroboros Advisor could not answer. Refresh and try again.'; });
        });
        $all('[data-chat-prompt]').forEach(function (button) {
            button.addEventListener('click', function () {
                input.value = button.getAttribute('data-chat-prompt') || '';
                input.focus();
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        updateOnlineStatus();
        Currency.apply();
        $all('[data-virtual-transactions]').forEach(mountVirtualTransactions);
        mountChat();
    });
})();
