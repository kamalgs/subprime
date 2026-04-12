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

    var labels = JSON.parse(canvas.dataset.labels || '[]');
    var values = JSON.parse(canvas.dataset.values || '[]');
    var colors = JSON.parse(canvas.dataset.colors || '[]');

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#fff',
            }],
        },
        options: {
            cutout: '60%',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 12,
                        font: { size: 11 },
                    },
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            return ctx.label + ': ' + ctx.parsed + '%';
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
 * Renders two datasets per scenario group:
 *   - "Future Value"  (solid scenario colour)
 *   - "Today's ₹"    (lighter version of the same colour)
 *
 * @param {string} canvasId
 */
function initCorpusChart(canvasId) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    _destroyExisting(canvas);

    var scenarios = JSON.parse(canvas.dataset.scenarios || '[]');
    if (!scenarios.length) return;

    var labels = scenarios.map(function (s) { return s.label + ' (' + s.cagr + '% p.a.)'; });

    // Future values dataset
    var futureValues = scenarios.map(function (s) { return s.future_value; });
    var futureColors = scenarios.map(function (s) { return s.color; });

    // Present values dataset — lighter colours (add ~60% opacity via hex)
    var presentValues = scenarios.map(function (s) { return s.present_value; });
    var presentColors = scenarios.map(function (s) {
        // Append 99 (≈60% opacity) to hex colour for a lighter shade
        return s.color + '99';
    });

    // Build per-bar colour arrays for Chart.js
    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Future Value',
                    data: futureValues,
                    backgroundColor: futureColors,
                    borderColor: futureColors,
                    borderWidth: 1,
                    borderRadius: 6,
                },
                {
                    label: "Today's \u20B9",
                    data: presentValues,
                    backgroundColor: presentColors,
                    borderColor: presentColors,
                    borderWidth: 1,
                    borderRadius: 6,
                },
            ],
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
                            var s = scenarios[ctx.dataIndex];
                            if (ctx.datasetIndex === 0) {
                                return 'Future Value: ' + s.future_value_fmt;
                            }
                            return "Today\u2019s \u20B9: " + s.present_value_fmt;
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
                    ticks: { font: { size: 12 } },
                    grid: { display: false },
                },
            },
        },
    });
}
