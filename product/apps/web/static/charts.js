/**
 * Benji chart helpers — Chart.js, theme-aware.
 *
 * Exposes:
 *   initDonutChart(canvasId)                        — asset-allocation nested donut
 *   initCorpusChart(fvCanvasId, pvCanvasId)         — two grouped bar charts
 *
 * All charts re-render on dark-mode toggle (listens for a `classList` change
 * on <html>) so colours stay legible after the user flips theme.
 */

// =============================================================================
//  Utilities
// =============================================================================

function _formatInr(value) {
    if (!value && value !== 0) return '\u20B90';
    var crore = 10000000;
    var lakh  = 100000;
    if (value >= crore) return '\u20B9' + (value / crore).toFixed(2) + ' Cr';
    if (value >= lakh)  return '\u20B9' + (value / lakh).toFixed(2) + ' L';
    return '\u20B9' + Math.round(value).toLocaleString('en-IN');
}

function _destroyExisting(canvas) {
    var existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
}

function _isDark() {
    return document.documentElement.classList.contains('dark');
}

/** Single source of truth for chart colour tokens; depends on current theme. */
function _themeTokens() {
    var dark = _isDark();
    return {
        surface:      dark ? '#1e293b' : '#ffffff',   // card bg (for borders between slices)
        text:         dark ? '#e2e8f0' : '#1f2937',
        textMuted:    dark ? '#94a3b8' : '#6b7280',
        textFaint:    dark ? '#64748b' : '#9ca3af',
        grid:         dark ? '#334155' : '#f1f5f9',
        tooltipBg:    dark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(15, 23, 42, 0.92)',
        tooltipText:  '#f8fafc',
        tooltipBody:  '#e2e8f0',
    };
}

/** Shared tooltip styling applied to every chart. */
function _tooltipOpts(tokens) {
    return {
        backgroundColor: tokens.tooltipBg,
        titleColor: tokens.tooltipText,
        bodyColor: tokens.tooltipBody,
        borderColor: 'rgba(255,255,255,0.06)',
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
        titleFont: { weight: '600', size: 12 },
        bodyFont:  { size: 12 },
        displayColors: true,
    };
}

// =============================================================================
//  Donut chart — asset allocation
// =============================================================================

function initDonutChart(canvasId) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    _destroyExisting(canvas);

    var innerLabels = JSON.parse(canvas.dataset.innerLabels || canvas.dataset.labels || '[]');
    var innerValues = JSON.parse(canvas.dataset.innerValues || canvas.dataset.values || '[]');
    var innerColors = JSON.parse(canvas.dataset.innerColors || canvas.dataset.colors || '[]');
    var outerLabels = JSON.parse(canvas.dataset.outerLabels || '[]');
    var outerValues = JSON.parse(canvas.dataset.outerValues || '[]');
    var outerColors = JSON.parse(canvas.dataset.outerColors || '[]');

    var hasOuter = outerLabels.length > 0 && (outerLabels.length !== innerLabels.length ||
        outerLabels.some(function(l, i) { return l !== innerLabels[i]; }));

    // Default-selected segment = largest inner slice.
    var topIdx = 0;
    innerValues.forEach(function(v, i) { if (v > innerValues[topIdx]) topIdx = i; });
    // Active segment state — updated on hover/tap, rendered by the centre plugin.
    var active = { dataset: 0, index: topIdx };

    var tokens = _themeTokens();

    function activeLabelValueColor() {
        if (active.dataset === 1) {
            return {
                label: outerLabels[active.index] || '',
                value: outerValues[active.index],
                color: outerColors[active.index] || '#4f46e5',
            };
        }
        return {
            label: innerLabels[active.index] || '',
            value: innerValues[active.index],
            color: innerColors[active.index] || '#4f46e5',
        };
    }

    // Centre text — reflects whichever segment is active (idle = largest).
    var centerPlugin = {
        id: 'centerText',
        afterDraw: function(chart) {
            var ctx = chart.ctx;
            var area = chart.chartArea;
            if (!area) return;
            var cx = (area.left + area.right) / 2;
            var cy = (area.top + area.bottom) / 2;
            var r = Math.min(area.right - area.left, area.bottom - area.top);
            var lv = activeLabelValueColor();
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = lv.color;
            ctx.font = 'bold ' + Math.round(r * 0.18) + 'px system-ui, -apple-system, "Segoe UI", sans-serif';
            ctx.fillText(lv.value + '%', cx, cy - Math.round(r * 0.08));
            ctx.fillStyle = tokens.textMuted;
            ctx.font = '500 ' + Math.round(r * 0.085) + 'px system-ui, -apple-system, sans-serif';
            // Truncate long sub-category labels so they fit inside the hole.
            var maxChars = Math.floor(r / 7);
            var label = lv.label.length > maxChars ? lv.label.slice(0, maxChars - 1) + '…' : lv.label;
            ctx.fillText(label, cx, cy + Math.round(r * 0.12));
            ctx.restore();
        }
    };

    var datasets = [{
        label: 'Asset class',
        data: innerValues,
        backgroundColor: innerColors,
        borderWidth: 2,
        borderColor: tokens.surface,
        hoverBorderWidth: 2,
        hoverOffset: 8,
        borderRadius: hasOuter ? 0 : 6,
        spacing: 1,
        weight: hasOuter ? 1.5 : 1,
    }];

    if (hasOuter) {
        datasets.push({
            label: 'Sub-category',
            data: outerValues,
            backgroundColor: outerColors,
            borderWidth: 2,
            borderColor: tokens.surface,
            hoverOffset: 5,
            spacing: 1,
            weight: 0.65,
        });
    }

    var chart = new Chart(canvas, {
        type: 'doughnut',
        data: { labels: hasOuter ? outerLabels : innerLabels, datasets: datasets },
        options: {
            cutout: hasOuter ? '42%' : '64%',
            responsive: true,
            maintainAspectRatio: true,
            animation: { animateRotate: true, animateScale: false, duration: 650, easing: 'easeOutQuart' },
            // Drive the centre label via hover — no tooltip needed (avoids overlap).
            onHover: function(_evt, elements) {
                if (elements && elements.length) {
                    active = { dataset: elements[0].datasetIndex, index: elements[0].index };
                } else {
                    active = { dataset: 0, index: topIdx };
                }
                chart.draw();
            },
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
        },
        plugins: [centerPlugin],
    });

    // Tap support for touch devices — keep active segment after the tap.
    canvas.addEventListener('click', function(evt) {
        var pts = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
        if (pts && pts.length) {
            active = { dataset: pts[0].datasetIndex, index: pts[0].index };
            chart.draw();
        }
    });
}

// =============================================================================
//  Corpus projection — two grouped bar charts (FV + PV)
// =============================================================================

function initCorpusChart(futureCanvasId, presentCanvasId) {
    _renderCorpusBar(futureCanvasId,  'future_value',  'future_value_fmt',  'Future value');
    _renderCorpusBar(presentCanvasId, 'present_value', 'present_value_fmt', "In today's \u20B9");
}

function _renderCorpusBar(canvasId, valueKey, fmtKey, title) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    _destroyExisting(canvas);

    var scenarios = JSON.parse(canvas.dataset.scenarios || '[]');
    if (!scenarios.length) return;

    var tokens = _themeTokens();

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: scenarios.map(function(s) { return s.label; }),
            datasets: [{
                label: title,
                data:            scenarios.map(function(s) { return s[valueKey]; }),
                backgroundColor: scenarios.map(function(s) { return s.color + 'cc'; }),
                borderColor:     scenarios.map(function(s) { return s.color; }),
                borderWidth: 0,
                borderRadius: 6,
                _fmts: scenarios.map(function(s) { return s[fmtKey]; }),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 600, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: title,
                    font: { size: 12, weight: '600' },
                    color: tokens.textMuted,
                    padding: { bottom: 8 },
                },
                tooltip: Object.assign({}, _tooltipOpts(tokens), {
                    callbacks: {
                        title: function(items) {
                            var s = scenarios[items[0].dataIndex];
                            return s.label + ' \u2014 ' + s.cagr + '% p.a.';
                        },
                        label: function(ctx) { return '  ' + ctx.dataset._fmts[ctx.dataIndex]; },
                    },
                }),
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(v) { return _formatInr(v); },
                        color: tokens.textFaint,
                        font: { size: 10 },
                    },
                    grid: { color: tokens.grid, drawBorder: false },
                    border: { display: false },
                },
                x: {
                    ticks: {
                        color: tokens.textMuted,
                        font: { size: 11, weight: '600' },
                    },
                    grid: { display: false },
                    border: { display: false },
                },
            },
        },
    });
}

// =============================================================================
//  Theme-change watcher — re-render charts when user flips dark/light.
// =============================================================================

(function watchTheme() {
    if (typeof MutationObserver === 'undefined') return;
    var last = _isDark();
    new MutationObserver(function() {
        var now = _isDark();
        if (now === last) return;
        last = now;
        // Re-init every chart on the page.
        document.querySelectorAll('canvas').forEach(function(canvas) {
            var chart = Chart.getChart(canvas);
            if (!chart) return;
            var id = canvas.id;
            if (!id) return;
            if (id === 'allocation-chart') {
                initDonutChart(id);
            } else if (id === 'corpus-chart-fv') {
                _renderCorpusBar(id, 'future_value',  'future_value_fmt',  'Future value');
            } else if (id === 'corpus-chart-pv') {
                _renderCorpusBar(id, 'present_value', 'present_value_fmt', "In today's \u20B9");
            }
        });
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
})();
