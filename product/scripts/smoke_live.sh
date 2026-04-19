#!/usr/bin/env bash
# Live smoke test — run after every finadvisor deploy.
#
# Usage:
#   ./product/scripts/smoke_live.sh                    # production URL
#   URL=https://staging.x uv …/smoke_live.sh           # override
set -euo pipefail

URL="${URL:-https://finadvisor.gkamal.online}"
CHEAT="${SUBPRIME_OTP_CHEAT:-242424}"

cd "$(dirname "$0")/../.."

echo "→ Smoke-testing ${URL}"
SUBPRIME_URL="${URL}" SUBPRIME_OTP_CHEAT="${CHEAT}" \
    uv run pytest product/tests/test_smoke_live.py -m smoke -v "$@"
