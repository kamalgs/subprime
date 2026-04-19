/**
 * Chart.js helpers for Benji wizard.
 *
 * initDonutChart(canvasId)  — asset allocation doughnut
 * initCorpusChart(canvasId) — corpus projection grouped bar chart
 *
 * Both functions destroy any existing Chart instance on the canvas before
 * creating a new one, so they are safe to call after HTMX re-renders.
 */

/**
 * Format a rupee amount as a compact string (e.g. "₹2.50 Cr", "₹5.50 L").
 * Used for Y-axis and tooltip labels.
 *
 * @param {number} value
 * @returns {string}
 */
function _formatInr(value) {
    if (!value && value !== 0) return '₹0';
    var crore = 10000000;
    var lakh  = 100000;
    if (value >= crore) {
        return '₹' + (value / crore).toFixed(2) + ' Cr';
    }
    if (value >= lakh) {
        return '₹' + (value / lakh).toFixed(2) + ' L';
    }
    return '₹' + Math.round(value).toLocaleString('en-IN');
}

/**
 * Destroy any existing Chart.js instance on the given canvas element.
 *
 * @param {HTMLCanvasElement} canvas
 */
function _destroyExisting(canvas) {
    var existing = Chart.getChart(canvas);
    if (existing) {
        existing.destroy();
    }
}

/**
 * Initialise an asset-allocation doughnut chart with center label.
 *
 * Reads from canvas data attributes:
 *   data-inner-labels / data-inner-values / data-inner-colors — asset classes
 *   data-outer-labels / data-outer-values / data-outer-colors — sub-categories (optional)
 *
 * When sub-categories are present a two-ring nested donut is rendered with the
 * asset-class ring weighted heavier. The center always shows the top segment.
 *
 * @param {string} canvasId
 */
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

    // Largest inner segment — used for center text
    var topIdx = 0;
    innerValues.forEach(function(v, i) { if (v > innerValues[topIdx]) topIdx = i; });

    // Plugin: draw percentage + label in the donut center
    var centerPlugin = {
        id: 'centerText',
        afterDraw: function(chart) {
            var ctx = chart.ctx;
            var area = chart.chartArea;
            if (!area) return;
            var cx = (area.left + area.right) / 2;
            var cy = (area.top + area.bottom) / 2;
            var r = Math.min(area.right - area.left, area.bottom - area.top);
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            // Large coloured percentage
            ctx.fillStyle = innerColors[topIdx] || '#4f46e5';
            ctx.font = 'bold ' + Math.round(r * 0.17) + 'px system-ui, -apple-system, sans-serif';
            ctx.fillText(innerValues[topIdx] + '%', cx, cy - Math.round(r * 0.08));
            // Small grey label
            ctx.fillStyle = '#9ca3af';
            ctx.font = Math.round(r * 0.09) + 'px system-ui, -apple-system, sans-serif';
            ctx.fillText(innerLabels[topIdx] || '', cx, cy + Math.round(r * 0.12));
            ctx.restore();
        }
    };

    var datasets = [{
        label: 'Asset Class',
        data: innerValues,
        backgroundColor: innerColors,
        borderWidth: 3,
        borderColor: '#ffffff',
        hoverBorderWidth: 3,
        hoverOffset: 10,
        borderRadius: hasOuter ? 0 : 4,
        spacing: 1,
        weight: hasOuter ? 1.5 : 1,
    }];

    if (hasOuter) {
        datasets.push({
            label: 'Sub-category',
            data: outerValues,
            backgroundColor: outerColors,
            borderWidth: 2,
            borderColor: '#ffffff',
            hoverOffset: 6,
            spacing: 1,
            weight: 0.65,
        });
    }

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: hasOuter ? outerLabels : innerLabels,
            datasets: datasets,
        },
        options: {
            cutout: hasOuter ? '42%' : '63%',
            responsive: true,
            maintainAspectRatio: true,
            animation: {
                animateRotate: true,
                animateScale: false,
                duration: 600,
                easing: 'easeOutQuart',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.88)',
                    titleColor: '#f9fafb',
                    bodyColor: '#e5e7eb',
                    padding: 10,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        label: function(ctx) {
                            var lbl = ctx.datasetIndex === 0
                                ? (innerLabels[ctx.dataIndex] || ctx.label)
                                : (outerLabels[ctx.dataIndex] || ctx.label);
                            return '  ' + lbl + ': ' + ctx.parsed + '%';
                        },
                    },
                },
            },
        },
        plugins: [centerPlugin],
    });
}

/**
 * Initialise corpus projection charts.
 *
 * Renders two independent bar charts — one for nominal future value, one for
 * inflation-adjusted present value — each with its own auto-scaled Y-axis so
 * neither set of bars appears squished relative to the other.
 *
 * Both canvases must carry:
 *   data-scenarios — JSON array of scenario objects:
 *     { label, cagr, future_value, present_value,
 *       future_value_fmt, present_value_fmt, color }
 *
 * @param {string} futureCanvasId
 * @param {string} presentCanvasId
 */
function initCorpusChart(futureCanvasId, presentCanvasId) {
    _renderCorpusBar(futureCanvasId, 'future_value',  'future_value_fmt',  'Future Value');
    _renderCorpusBar(presentCanvasId, 'present_value', 'present_value_fmt', "In Today's \u20B9");
}

/**
 * Render a single scenario bar chart onto a canvas.
 *
 * @param {string} canvasId
 * @param {string} valueKey       — key on each scenario object for bar height
 * @param {string} fmtKey         — key for pre-formatted tooltip string
 * @param {string} title          — chart title shown above the bars
 */
function _renderCorpusBar(canvasId, valueKey, fmtKey, title) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    _destroyExisting(canvas);

    var scenarios = JSON.parse(canvas.dataset.scenarios || '[]');
    if (!scenarios.length) return;

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: scenarios.map(function(s) { return s.label; }),
            datasets: [{
                label: title,
                data:            scenarios.map(function(s) { return s[valueKey]; }),
                backgroundColor: scenarios.map(function(s) { return s.color + 'cc'; }),
                borderColor:     scenarios.map(function(s) { return s.color; }),
                borderWidth: 1,
                borderRadius: 8,
                _fmts:  scenarios.map(function(s) { return s[fmtKey]; }),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: title,
                    font: { size: 12, weight: '600' },
                    color: '#4b5563',
                    padding: { bottom: 6 },
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.88)',
                    titleColor: '#f9fafb',
                    bodyColor: '#e5e7eb',
                    padding: 10,
                    cornerRadius: 8,
                    callbacks: {
                        title: function(items) {
                            var s = scenarios[items[0].dataIndex];
                            return s.label + ' \u2014 ' + s.cagr + '% p.a.';
                        },
                        label: function(ctx) {
                            return '  ' + ctx.dataset._fmts[ctx.dataIndex];
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(v) { return _formatInr(v); },
                        font: { size: 10 },
                    },
                    grid: { color: '#f3f4f6' },
                },
                x: {
                    ticks: { font: { size: 12, weight: 'bold' } },
                    grid: { display: false },
                },
            },
        },
    });
}
