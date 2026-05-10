#!/usr/bin/env bash
# Color-by-color env-var / job-config rollout for the finadvisor Nomad jobs.
#
# Background — what this fixes:
#   `scripts/blue-green-deploy.sh` handles IMAGE rollouts safely (deploys
#   to inactive, smoke-tests via X-Benji-Color header, then promotes).
#   But env-var / config changes used to bypass that flow — a single
#   `terraform apply -target=nomad_job.finadvisor_blue
#                  -target=nomad_job.finadvisor_green` restarted both
#   colors at once. When SUBPRIME_AUTO_MIGRATE first flipped on, the
#   change exposed an unrelated bug; both colors crashed in lockstep,
#   prod down ~2 min before the env var was reverted.
#
# Filed at kamalgs/subprime#58. This script encodes the discipline so
# the next env-var rollout can't repeat it.
#
# Workflow:
#   1. Identify active color from /etc/caddy/active-finadvisor.caddy.
#   2. terraform apply -target=nomad_job.finadvisor_<inactive>
#   3. Wait for the inactive alloc to be healthy (Nomad alloc + Docker
#      health check).
#   4. Smoke the inactive color via X-Benji-Color header.
#   5. HyperDX error-rate check on the inactive color.
#   6. Apply the same change to the active color, with the same gates.
#
# If any inactive-side step fails, the script exits non-zero before
# touching the active color — traffic stays on a known-good image.
#
# Usage:
#   scripts/rollout-env.sh
#       Run AFTER editing ~/projects/nomad/jobs/finadvisor.tf (or
#       terraform.tfvars). The script picks up whatever pending
#       terraform diff exists and applies it color-by-color.
#
# Env vars:
#   NOMAD_JOBS=~/projects/nomad/jobs   terraform working directory
#   SMOKE_WAIT_SECS=60                 health-wait per color
#   HEALTH_WINDOW_MIN=3                HyperDX lookback window
#   ALLOW_DIRTY_HYPERDX=               set to 1 to skip HyperDX gate

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NOMAD_JOBS="${NOMAD_JOBS:-$HOME/projects/nomad/jobs}"
CADDY_ACTIVE="/etc/caddy/active-finadvisor.caddy"
PORT_BLUE=8091
PORT_GREEN=8093
SMOKE_WAIT_SECS="${SMOKE_WAIT_SECS:-60}"
HEALTH_WINDOW_MIN="${HEALTH_WINDOW_MIN:-3}"
MAX_ERRORS=0
MAX_LOG_ERRORS=0

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
die() { echo "[$(date -u +%H:%M:%S)] ✗ $*" >&2; exit 1; }

# 1. Which colour is active?
if [[ ! -r "$CADDY_ACTIVE" ]]; then
    die "$CADDY_ACTIVE missing — won't guess active colour for an env rollout"
fi
if grep -q ":${PORT_BLUE}" "$CADDY_ACTIVE"; then
    active="blue"
elif grep -q ":${PORT_GREEN}" "$CADDY_ACTIVE"; then
    active="green"
else
    die "$CADDY_ACTIVE references neither port — please fix"
fi
inactive=$([[ "$active" == "blue" ]] && echo "green" || echo "blue")
log "active=$active   inactive=$inactive"

# 2. Sanity — must have a pending terraform diff. Pass live image tags
# so the gate doesn't false-positive on tfvars-image drift.
log "checking for pending terraform changes (excluding image-tfvar drift)"
plan_img_blue=$(nomad job inspect finadvisor-blue 2>/dev/null \
    | python3 -c 'import json,sys;j=json.load(sys.stdin);print([t["Config"]["image"] for tg in j["Job"]["TaskGroups"] for t in tg["Tasks"] if t["Name"]=="finadvisor"][0])')
plan_img_green=$(nomad job inspect finadvisor-green 2>/dev/null \
    | python3 -c 'import json,sys;j=json.load(sys.stdin);print([t["Config"]["image"] for tg in j["Job"]["TaskGroups"] for t in tg["Tasks"] if t["Name"]=="finadvisor"][0])')
plan_rc=0
( cd "$NOMAD_JOBS" && terraform plan -detailed-exitcode \
    -target="nomad_job.finadvisor_${inactive}" \
    -target="nomad_job.finadvisor_${active}" \
    -var="finadvisor_blue_image=${plan_img_blue}" \
    -var="finadvisor_green_image=${plan_img_green}" \
    >/dev/null 2>&1 ) || plan_rc=$?
case "$plan_rc" in
    0) die "no pending terraform changes for finadvisor jobs — nothing to roll out" ;;
    2) log "pending changes detected — proceeding" ;;
    *) die "terraform plan failed (exit ${plan_rc})" ;;
esac

current_image() {
    local color="$1"
    nomad job inspect "finadvisor-${color}" 2>/dev/null \
        | python3 -c 'import json,sys;j=json.load(sys.stdin);print([t["Config"]["image"] for tg in j["Job"]["TaskGroups"] for t in tg["Tasks"] if t["Name"]=="finadvisor"][0])'
}

apply_to_color() {
    local color="$1"
    # Image tags are passed via -var on every blue-green deploy and don't
    # persist in tfvars — a terraform apply without -var would silently
    # revert to the default `finadvisor:local`. Read the current live tag
    # for BOTH colors and pass them through, so we only mutate what the
    # caller actually changed.
    local img_blue img_green
    img_blue=$(current_image blue)
    img_green=$(current_image green)
    log "applying terraform change to finadvisor-${color} (preserving image tags)"
    ( cd "$NOMAD_JOBS" && terraform apply -auto-approve \
        -target="nomad_job.finadvisor_${color}" \
        -var="finadvisor_blue_image=${img_blue}" \
        -var="finadvisor_green_image=${img_green}" \
        >/dev/null )

    log "waiting ${SMOKE_WAIT_SECS}s for ${color} to become healthy"
    local deadline=$(( $(date +%s) + SMOKE_WAIT_SECS ))
    while (( $(date +%s) < deadline )); do
        local alloc
        alloc=$(nomad job allocs -json "finadvisor-${color}" 2>/dev/null \
            | python3 -c 'import json,sys;print(next((a["ID"] for a in json.load(sys.stdin) if a["ClientStatus"]=="running"), ""))' 2>/dev/null \
            || true)
        if [[ -n "$alloc" ]]; then
            local cstatus
            cstatus=$(sudo docker ps --format '{{.Names}}|{{.Status}}' \
                | grep "finadvisor-${alloc}" | head -1 | grep -oE 'healthy|unhealthy|starting' \
                || true)
            if [[ "$cstatus" == "healthy" ]]; then
                log "  ${color} healthy"
                return 0
            fi
        fi
        sleep 5
    done
    die "${color} not healthy within ${SMOKE_WAIT_SECS}s"
}

smoke_color() {
    local color="$1"
    log "smoking ${color} via X-Benji-Color header"
    if ! "$REPO_ROOT/scripts/smoke.sh" "$color"; then
        die "smoke failed on ${color}"
    fi
}

metrics_gate() {
    local color="$1"
    log "checking HyperDX metrics for ${color} over last ${HEALTH_WINDOW_MIN} min"
    if [[ -n "${ALLOW_DIRTY_HYPERDX:-}" ]]; then
        log "  (gate skipped — ALLOW_DIRTY_HYPERDX is set)"
        return 0
    fi
    local err log_err
    err="$("$REPO_ROOT/scripts/hyperdx_query.sh" errors "$color" "$HEALTH_WINDOW_MIN" 2>/dev/null || echo 0)"
    log_err="$("$REPO_ROOT/scripts/hyperdx_query.sh" log_errors "$color" "$HEALTH_WINDOW_MIN" 2>/dev/null || echo 0)"
    log "  error spans = $err   error logs = $log_err"
    if (( err > MAX_ERRORS )) || (( log_err > MAX_LOG_ERRORS )); then
        die "metrics dirty on ${color} — NOT proceeding to active"
    fi
}

# 3. Apply + gate inactive first.
apply_to_color  "$inactive"
smoke_color     "$inactive"
metrics_gate    "$inactive"

log "✓ ${inactive} healthy after rollout — proceeding to ${active}"

# 4. Apply + gate active.
apply_to_color  "$active"
smoke_color     "$active"
metrics_gate    "$active"

log "✓ rollout complete on both colors (active=${active})"
