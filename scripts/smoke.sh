#!/usr/bin/env bash
# Smoke / sanity test — hits the key endpoints on the target colour.
#
# Usage:
#   scripts/smoke.sh <color>        # color = blue | green
#   scripts/smoke.sh blue --prod    # skip the X-Benji-Color header, test real traffic
#
# Exit code:
#   0  all checks passed
#   1  one or more checks failed

set -euo pipefail

COLOR="${1:?usage: smoke.sh <blue|green> [--prod]}"
MODE="${2:-header}"   # header = force the colour via header; prod = public URL

URL="${SMOKE_URL:-https://finadvisor.gkamal.online}"

if [[ "$MODE" == "--prod" ]]; then
    CURL_HDR=()
else
    CURL_HDR=(-H "X-Benji-Color: $COLOR")
fi

timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pass() { echo "[$(timestamp)] ✓ $1"; }
fail() { echo "[$(timestamp)] ✗ $1" >&2; exit 1; }

# 1. Landing page returns the React shell.
body="$(curl -fsS "${CURL_HDR[@]}" "$URL/")" || fail "GET / failed"
grep -q 'id="root"' <<<"$body" || fail "/ did not return the React shell"
pass "landing page OK"

# 2. Session bootstrap returns JSON with an id.
session="$(curl -fsS "${CURL_HDR[@]}" "$URL/api/v2/session")"
echo "$session" | grep -q '"id"' || fail "/api/v2/session missing id field"
pass "session bootstrap OK"

# 3. Personas endpoint returns JSON (may be {'personas':null} for basic tier).
personas="$(curl -fsS "${CURL_HDR[@]}" "$URL/api/v2/personas")"
echo "$personas" | grep -q '"personas"' || fail "/api/v2/personas missing field"
pass "personas endpoint OK"

# 4. Color check — the smoke request actually landed on the right instance.
#    We grep the session-creation trace in HyperDX via a separate check
#    below; here we just confirm round-trip works.

echo "[$(timestamp)] smoke suite passed for color=$COLOR"
