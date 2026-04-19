/**
 * Plan-generation UI helpers — loaded once by base.html so they remain
 * available across HTMX partial swaps. Called from inline onclick handlers
 * in the strategy dashboard button.
 */

(function () {
    var PLAN_STEPS = [
        { pct: 10, text: "Analysing your profile\u2026",          delay: 0 },
        { pct: 25, text: "Matching fund categories\u2026",        delay: 4000 },
        { pct: 45, text: "Selecting specific funds\u2026",        delay: 10000 },
        { pct: 65, text: "Computing projections\u2026",           delay: 20000 },
        { pct: 80, text: "Building your personalised plan\u2026", delay: 35000 },
        { pct: 92, text: "Almost there\u2026",                    delay: 55000 },
    ];

    window.startPlanGeneration = function () {
        var loading = document.getElementById('plan-loading');
        var bar = document.getElementById('plan-progress-bar');
        var text = document.getElementById('plan-progress-text');
        if (!loading || !bar || !text) return;
        loading.classList.remove('hidden');
        (window._planTimers || []).forEach(clearTimeout);
        window._planTimers = PLAN_STEPS.map(function (s) {
            return setTimeout(function () {
                bar.style.width = s.pct + '%';
                text.textContent = s.text;
            }, s.delay);
        });
    };

    window.resetPlanGeneration = function () {
        var loading = document.getElementById('plan-loading');
        var bar = document.getElementById('plan-progress-bar');
        var text = document.getElementById('plan-progress-text');
        (window._planTimers || []).forEach(clearTimeout);
        window._planTimers = [];
        if (bar)  bar.style.width = '0%';
        if (text) text.textContent = 'Something went wrong. Try again.';
        if (loading) loading.classList.remove('hidden');
        var btn = document.getElementById('generate-plan-btn');
        if (btn) btn.disabled = false;
    };

    /**
     * Click handler for the Generate Plan button. Robust against HTMX partial
     * swaps because this function is defined at page load, not inside a
     * swapped-in script tag.
     */
    window.triggerPlanGeneration = function () {
        var btn = document.getElementById('generate-plan-btn');
        if (btn) btn.disabled = true;
        window.startPlanGeneration();

        // htmx.ajax returns a Promise that resolves on 2xx, rejects on network/HTTP errors.
        // A 200 response with HX-Redirect header is handled automatically by htmx.
        if (typeof htmx === 'undefined') {
            console.error('htmx not loaded — cannot fire plan generation');
            window.resetPlanGeneration();
            return;
        }
        var p = htmx.ajax('POST', '/api/generate-plan', { swap: 'none', source: '#generate-plan-btn' });
        if (p && typeof p.catch === 'function') {
            p.catch(function (err) {
                console.error('plan-generation request failed', err);
                window.resetPlanGeneration();
            });
        }
    };
})();
