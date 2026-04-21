#!/usr/bin/env bash
# Query HyperDX's ClickHouse for deploy health checks.
#
# Usage:
#   scripts/hyperdx_query.sh errors <color> [window_minutes]   # default 5 min
#   scripts/hyperdx_query.sh p95    <color> [window_minutes]
#   scripts/hyperdx_query.sh log_errors <color> [window_minutes]
#
# Returns a single numeric line on stdout. Exits non-zero on query failure.

set -euo pipefail

ACTION="${1:?usage: hyperdx_query.sh errors|p95|log_errors <color> [window_m]}"
COLOR="${2:?color required}"
WINDOW="${3:-5}"

SERVICE="finadvisor-web-${COLOR}"

run_sql() {
    local q="$1"
    sudo docker exec "$(sudo docker ps --filter 'name=hyperdx' -q)" \
        curl -sS "http://localhost:8123/?query=$(printf '%s' "$q" | sed 's/ /+/g; s|/|%2F|g; s|=|%3D|g; s|<|%3C|g; s|>|%3E|g; s|(|%28|g; s|)|%29|g;')" \
        2>/dev/null
}

# ClickHouse datetime arithmetic: subtractMinutes(now(), N)
case "$ACTION" in
    errors)
        q="SELECT count() FROM otel_traces WHERE ServiceName='${SERVICE}' AND StatusCode='Error' AND Timestamp > subtractMinutes(now(), ${WINDOW})"
        ;;
    p95)
        q="SELECT quantile(0.95)(Duration/1e6) FROM otel_traces WHERE ServiceName='${SERVICE}' AND SpanName='subprime.plan.generate' AND Timestamp > subtractMinutes(now(), ${WINDOW})"
        ;;
    log_errors)
        q="SELECT count() FROM otel_logs WHERE ServiceName='${SERVICE}' AND SeverityText='ERROR' AND TimestampTime > subtractMinutes(now(), ${WINDOW})"
        ;;
    *)
        echo "unknown action: $ACTION" >&2
        exit 2
        ;;
esac

result="$(run_sql "$q")" || { echo "query failed" >&2; exit 1; }
# strip whitespace and newlines
echo "$result" | tr -d '[:space:]'
