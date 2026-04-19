#!/usr/bin/env bash
# Live smoke test — run after every finadvisor deploy.
#
# Waits for the backend to be serving real content (not the Caddy on-demand
# launcher's "Starting..." placeholder) before running the suite.
#
# Usage:
#   ./product/scripts/smoke_live.sh                    # fast + strategy (default)
#   ./product/scripts/smoke_live.sh --with-plan        # include full plan gen (slow)
#   URL=https://staging.x ./product/scripts/smoke_live.sh
set -euo pipefail

URL="${URL:-https://finadvisor.gkamal.online}"
CHEAT="${SUBPRIME_OTP_CHEAT:-242424}"

WITH_PLAN=0
for a in "$@"; do
    [[ "$a" == "--with-plan" ]] && WITH_PLAN=1
done

cd "$(dirname "$0")/../.."

echo "→ Waiting for ${URL} to serve real content…"
for i in {1..40}; do
    body=$(curl -sLm 5 "${URL}/step/1" 2>/dev/null || true)
    if echo "$body" | grep -q "Choose your plan"; then
        echo "   ready after ${i} attempts"
        break
    fi
    sleep 3
    if [[ $i -eq 40 ]]; then
        echo "   backend never became ready" >&2
        exit 1
    fi
done

echo "→ Smoke-testing ${URL} (plan_gen=${WITH_PLAN})"
# By default we skip the plan-generation test — it's flaky against Together
# Qwen3-235B (agent loop occasionally hangs mid-tool-calls) and is much slower
# than the other checks. Pass --with-plan to include it.
DESELECT=()
if [[ $WITH_PLAN -eq 0 ]]; then
    DESELECT+=("--deselect" "product/tests/test_smoke_live.py::test_full_plan_generation_against_live_llm")
fi

SUBPRIME_URL="${URL}" SUBPRIME_OTP_CHEAT="${CHEAT}" \
    uv run pytest product/tests/test_smoke_live.py -m smoke -v "${DESELECT[@]}"
