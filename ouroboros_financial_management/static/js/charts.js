(function () {
    'use strict';
    var registry = [];

    function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
    function colorSet() {
        return {
            primary: css('--primary') || '#0ea5e9',
            primary2: css('--primary-2') || '#14b8a6',
            positive: css('--positive') || '#10b981',
            danger: css('--danger') || '#dc2626',
            warning: css('--warning') || '#f59e0b',
            text: css('--text') || '#0f172a',
            muted: css('--muted') || '#64748b',
            grid: css('--grid') || 'rgba(100, 116, 139, 0.2)'
        };
    }
    function setup(canvas) {
        var rect = canvas.getBoundingClientRect();
        var dpr = window.devicePixelRatio || 1;
        var width = Math.max(320, rect.width || canvas.clientWidth || 600);
        var height = Number(canvas.getAttribute('height')) || 300;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        var ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);
        return { ctx: ctx, width: width, height: height, colors: colorSet() };
    }
    function currencySymbol(data) {
        var fc = window.FinanceCurrency;
        if (fc && fc.ready) return fc.displaySymbol;
        return (data && data.currency) || (fc && fc.baseSymbol) || '$';
    }
    function convert(values) {
        var fc = window.FinanceCurrency;
        return (values || []).map(function (v) { return fc ? fc.convertNumber(Number(v || 0)) : Number(v || 0); });
    }
    function money(value, data) {
        var fc = window.FinanceCurrency;
        if (fc) return fc.format(Number(value || 0), currencySymbol(data), fc.ready ? fc.display : fc.base);
        var abs = Math.abs(Number(value || 0));
        return (value < 0 ? '-' : '') + (data.currency || '$') + abs.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    function niceMax(values) {
        var max = Math.max(1, ...values.map(function (v) { return Math.abs(Number(v || 0)); }));
        var pow = Math.pow(10, Math.floor(Math.log10(max)));
        return Math.ceil(max / pow) * pow;
    }
    function drawAxes(ctx, w, h, pad, max, labels, data, colors) {
        ctx.strokeStyle = colors.grid;
        ctx.lineWidth = 1;
        ctx.fillStyle = colors.muted;
        ctx.font = '12px system-ui, sans-serif';
        ctx.textAlign = 'right';
        for (var i = 0; i <= 4; i++) {
            var y = pad.top + (h - pad.top - pad.bottom) * (i / 4);
            ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
            ctx.fillText(money(max * (1 - i / 4), data), pad.left - 8, y + 4);
        }
        ctx.textAlign = 'center';
        var count = labels.length;
        labels.forEach(function (label, i) {
            if (count > 8 && i % Math.ceil(count / 6) !== 0 && i !== count - 1) return;
            var x = pad.left + (w - pad.left - pad.right) * (count === 1 ? 0.5 : i / (count - 1));
            ctx.fillText(label, x, h - pad.bottom + 24);
        });
    }
    function drawLine(ctx, points, color, fill, baseY) {
        if (!points.length) return;
        ctx.beginPath();
        points.forEach(function (p, i) { if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
        if (fill) {
            ctx.lineTo(points[points.length - 1].x, baseY);
            ctx.lineTo(points[0].x, baseY);
            ctx.closePath();
            ctx.globalAlpha = 0.16; ctx.fillStyle = color; ctx.fill(); ctx.globalAlpha = 1;
        }
        ctx.beginPath();
        points.forEach(function (p, i) { if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
        ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
        points.forEach(function (p) { ctx.beginPath(); ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); });
    }
    function renderIncomeExpense(id, rawData, remember) {
        var canvas = document.getElementById(id); if (!canvas) return;
        if (remember !== false && !registry.some(function (r) { return r.id === id; })) registry.push({ kind: 'income', id: id, data: rawData });
        var data = Object.assign({}, rawData || {});
        var s = setup(canvas), ctx = s.ctx, w = s.width, h = s.height, c = s.colors;
        var labels = data.labels || [];
        if (!labels.length) { empty(ctx, w, h, 'No transaction data yet', c); return; }
        var income = convert(data.income), expenses = convert(data.expenses), net = convert(data.net);
        var max = niceMax(income.concat(expenses, net));
        var pad = { left: 78, right: 24, top: 26, bottom: 58 };
        var plotW = w - pad.left - pad.right, plotH = h - pad.top - pad.bottom;
        drawAxes(ctx, w, h, pad, max, labels, data, c);
        function points(values) {
            return values.map(function (v, i) {
                var x = pad.left + plotW * (labels.length === 1 ? 0.5 : i / (labels.length - 1));
                var y = pad.top + plotH * (1 - Math.max(0, Number(v || 0)) / max);
                return { x: x, y: y };
            });
        }
        if (data.type === 'bar') {
            var group = plotW / labels.length;
            labels.forEach(function (_, i) {
                var x = pad.left + i * group + group * 0.2;
                var bw = Math.max(6, group * 0.22);
                var ih = plotH * (Number(income[i] || 0) / max);
                var eh = plotH * (Number(expenses[i] || 0) / max);
                ctx.fillStyle = c.positive; roundRect(ctx, x, pad.top + plotH - ih, bw, ih, 6); ctx.fill();
                ctx.fillStyle = c.danger; roundRect(ctx, x + bw + 5, pad.top + plotH - eh, bw, eh, 6); ctx.fill();
            });
        } else {
            drawLine(ctx, points(income), c.positive, data.type === 'area', pad.top + plotH);
            drawLine(ctx, points(expenses), c.danger, data.type === 'area', pad.top + plotH);
            drawLine(ctx, points(net.map(function (v) { return Math.max(0, v); })), c.primary, false, pad.top + plotH);
        }
        legend(ctx, w, c, [{ label: 'Income', color: c.positive }, { label: 'Expenses', color: c.danger }, { label: 'Net+', color: c.primary }]);
    }
    function renderCategory(id, rawData, remember) {
        var canvas = document.getElementById(id); if (!canvas) return;
        if (remember !== false && !registry.some(function (r) { return r.id === id; })) registry.push({ kind: 'category', id: id, data: rawData });
        var data = Object.assign({}, rawData || {});
        var s = setup(canvas), ctx = s.ctx, w = s.width, h = s.height, c = s.colors;
        var labels = data.labels || [], values = convert(data.values);
        if (!labels.length) { empty(ctx, w, h, 'No expense categories yet', c); return; }
        if (data.type === 'donut') renderDonut(ctx, w, h, labels, values, data, c);
        else renderBars(ctx, w, h, labels, values, data, c, data.type === 'horizontal');
    }
    function renderDonut(ctx, w, h, labels, values, data, c) {
        var total = values.reduce(function (a, b) { return a + Number(b || 0); }, 0) || 1;
        var cx = w / 2, cy = h / 2 - 8, r = Math.min(w, h) * 0.29, inner = r * 0.58;
        var colors = [c.primary, c.primary2, c.positive, c.warning, c.danger, '#8b5cf6', '#06b6d4', '#f59e0b'];
        var start = -Math.PI / 2;
        values.forEach(function (value, i) {
            var angle = (Number(value || 0) / total) * Math.PI * 2;
            ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, start, start + angle); ctx.closePath(); ctx.fillStyle = colors[i % colors.length]; ctx.fill();
            start += angle;
        });
        ctx.globalCompositeOperation = 'destination-out'; ctx.beginPath(); ctx.arc(cx, cy, inner, 0, Math.PI * 2); ctx.fill(); ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = c.text; ctx.font = '700 14px system-ui'; ctx.textAlign = 'center'; ctx.fillText('Total', cx, cy - 4); ctx.font = '900 20px system-ui'; ctx.fillText(money(total, data), cx, cy + 22);
        legend(ctx, w, c, labels.slice(0, 7).map(function (label, i) { return { label: label, color: colors[i % colors.length] }; }), h - 38);
    }
    function renderBars(ctx, w, h, labels, values, data, c, horizontal) {
        var max = niceMax(values), colors = [c.primary, c.primary2, c.positive, c.warning, c.danger, '#8b5cf6'];
        if (horizontal) {
            var pad = { left: 120, right: 30, top: 24, bottom: 28 }, rowH = (h - pad.top - pad.bottom) / labels.length;
            ctx.font = '12px system-ui';
            labels.forEach(function (label, i) {
                var y = pad.top + i * rowH + rowH * 0.25;
                var bw = (w - pad.left - pad.right) * (Number(values[i] || 0) / max);
                ctx.fillStyle = c.muted; ctx.textAlign = 'right'; ctx.fillText(label.slice(0, 16), pad.left - 10, y + rowH * 0.25);
                ctx.fillStyle = colors[i % colors.length]; roundRect(ctx, pad.left, y, bw, Math.max(10, rowH * 0.45), 7); ctx.fill();
                ctx.fillStyle = c.text; ctx.textAlign = 'left'; ctx.fillText(money(values[i], data), pad.left + bw + 8, y + rowH * 0.3);
            });
        } else {
            var pad2 = { left: 68, right: 20, top: 24, bottom: 62 }, plotH = h - pad2.top - pad2.bottom, group = (w - pad2.left - pad2.right) / labels.length;
            ctx.strokeStyle = c.grid; ctx.fillStyle = c.muted; ctx.font = '12px system-ui'; ctx.textAlign = 'right';
            for (var j = 0; j <= 4; j++) { var gy = pad2.top + plotH * (j / 4); ctx.beginPath(); ctx.moveTo(pad2.left, gy); ctx.lineTo(w - pad2.right, gy); ctx.stroke(); ctx.fillText(money(max * (1 - j / 4), data), pad2.left - 7, gy + 4); }
            labels.forEach(function (label, i) { var bh = plotH * (Number(values[i] || 0) / max), x = pad2.left + i * group + group * 0.22; ctx.fillStyle = colors[i % colors.length]; roundRect(ctx, x, pad2.top + plotH - bh, Math.max(8, group * 0.55), bh, 7); ctx.fill(); ctx.fillStyle = c.muted; ctx.save(); ctx.translate(x + group * 0.26, h - pad2.bottom + 12); ctx.rotate(-Math.PI / 5); ctx.textAlign = 'right'; ctx.fillText(label.slice(0, 12), 0, 0); ctx.restore(); });
        }
    }
    function legend(ctx, w, c, items, y) {
        y = y || 18;
        ctx.font = '12px system-ui'; ctx.textAlign = 'left';
        var x = 18;
        items.forEach(function (item) {
            ctx.fillStyle = item.color; ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = c.muted; ctx.fillText(item.label, x + 10, y + 4);
            x += ctx.measureText(item.label).width + 34;
            if (x > w - 120) { x = 18; y += 18; }
        });
    }
    function empty(ctx, w, h, text, c) { ctx.fillStyle = c.muted; ctx.font = '700 16px system-ui'; ctx.textAlign = 'center'; ctx.fillText(text, w / 2, h / 2); }
    function roundRect(ctx, x, y, w, h, r) { w = Math.max(0, w); h = Math.max(0, h); r = Math.min(r, w / 2, h / 2); ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
    function rerender() { registry.forEach(function (item) { if (item.kind === 'income') renderIncomeExpense(item.id, item.data, false); else renderCategory(item.id, item.data, false); }); }
    window.FinanceCharts = { renderIncomeExpense: renderIncomeExpense, renderCategory: renderCategory, rerender: rerender };
    window.addEventListener('resize', function () { clearTimeout(window.__financeChartResize); window.__financeChartResize = setTimeout(rerender, 180); });
    window.addEventListener('finance:rerender', rerender);
    window.addEventListener('currency:updated', rerender);
})();
