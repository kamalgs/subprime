/**
 * Chart.js helpers for FinAdvisor wizard.
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
 * Initialise an asset-allocation doughnut chart.
 *
 * Reads from canvas data attributes:
 *   data-labels  — JSON array of label strings
 *   data-values  — JSON array of numeric percentages
 *   data-colors  — JSON array of hex colour strings
 *
 * @param {string} canvasId
 */
function initDonutChart(canvasId) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    _destroyExisting(canvas);

    // Inner ring: asset classes
    var innerLabels = JSON.parse(canvas.dataset.innerLabels || canvas.dataset.labels || '[]');
    var innerValues = JSON.parse(canvas.dataset.innerValues || canvas.dataset.values || '[]');
    var innerColors = JSON.parse(canvas.dataset.innerColors || canvas.dataset.colors || '[]');

    // Outer ring: sub-categories (may be same as inner if no subs)
    var outerLabels = JSON.parse(canvas.dataset.outerLabels || '[]');
    var outerValues = JSON.parse(canvas.dataset.outerValues || '[]');
    var outerColors = JSON.parse(canvas.dataset.outerColors || '[]');

    var hasOuter = outerLabels.length > 0 && (outerLabels.length !== innerLabels.length ||
        outerLabels.some(function(l, i) { return l !== innerLabels[i]; }));

    var datasets = [{
        label: 'Asset Class',
        data: innerValues,
        backgroundColor: innerColors,
        borderWidth: 2,
        borderColor: '#fff',
        weight: 1,
    }];

    if (hasOuter) {
        datasets.push({
            label: 'Category',
            data: outerValues,
            backgroundColor: outerColors,
            borderWidth: 1,
            borderColor: '#fff',
            weight: 1,
        });
    }

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: hasOuter ? outerLabels : innerLabels,
            datasets: datasets,
        },
        options: {
            cutout: hasOuter ? '40%' : '60%',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            var ds = ctx.datasetIndex === 0 ? 'Asset Class' : 'Category';
                            var lbl = ctx.datasetIndex === 0 ? innerLabels[ctx.dataIndex] : outerLabels[ctx.dataIndex];
                            return ds + ' — ' + lbl + ': ' + ctx.parsed + '%';
                        },
                    },
                },
            },
        },
    });
}

/**
 * Initialise a corpus projection grouped bar chart.
 *
 * Reads from canvas data attribute:
 *   data-scenarios — JSON array of scenario objects:
 *     { label, cagr, future_value, present_value,
 *       future_value_fmt, present_value_fmt, color }
 *
 * Layout: two groups on the X axis — "Future Value" and "In Today's ₹".
 * Each group has Bear/Base/Bull bars side by side.
 *
 * @param {string} canvasId
 */
function initCorpusChart(canvasId) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    _destroyExisting(canvas);

    var scenarios = JSON.parse(canvas.dataset.scenarios || '[]');
    if (!scenarios.length) return;

    // X-axis: two groups
    var labels = ['Future Value', "In Today's \u20B9"];

    // One dataset per scenario (Bear, Base, Bull)
    var datasets = scenarios.map(function (s) {
        return {
            label: s.label + ' (' + s.cagr + '% p.a.)',
            data: [s.future_value, s.present_value],
            backgroundColor: s.color + 'cc',
            borderColor: s.color,
            borderWidth: 1,
            borderRadius: 6,
            // Store formatted values for tooltips
            _fmts: [s.future_value_fmt, s.present_value_fmt],
        };
    });

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        boxWidth: 14,
                        padding: 12,
                        font: { size: 12 },
                    },
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            var fmts = ctx.dataset._fmts;
                            return ctx.dataset.label + ': ' + (fmts ? fmts[ctx.dataIndex] : _formatInr(ctx.parsed.y));
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function (value) {
                            return _formatInr(value);
                        },
                        font: { size: 11 },
                    },
                    grid: {
                        color: '#f3f4f6',
                    },
                },
                x: {
                    ticks: { font: { size: 12, weight: 'bold' } },
                    grid: { display: false },
                },
            },
        },
    });
}
