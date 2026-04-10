#!/usr/bin/env bash
# Run all three test tiers in sequence:
#   1. Unit tests       (always)
#   2. Integration tests (always, requires Xvfb)
#   3. Hardware tests   (only if ESPARGOS_IP is set or supplied as first arg)
#
# Usage:
#   ./run-tests-all.sh                           # unit + integration only
#   ./run-tests-all.sh 192.168.1.x               # + hardware tests
#   ESPARGOS_IP=192.168.1.x ./run-tests-all.sh   # + hardware tests
#   ./run-tests-all.sh 192.168.1.x --camera-backend picamera2
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve optional ESPARGOS IP (first arg if it looks like an IP)
ESPARGOS_IP="${ESPARGOS_IP:-}"
EXTRA_ARGS=("$@")
if [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ESPARGOS_IP="$1"
    EXTRA_ARGS=("${@:2}")
fi

PASS=0
FAIL=0

run_suite() {
    local label="$1"; shift
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if "$@"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "  ✗ $label FAILED"
    fi
}

run_suite "Unit tests" \
    "$SCRIPT_DIR/run-tests-unit.sh"

run_suite "Integration tests" \
    "$SCRIPT_DIR/run-tests-integration.sh"

if [[ -n "$ESPARGOS_IP" ]]; then
    run_suite "Hardware tests (ESPARGOS: $ESPARGOS_IP)" \
        "$SCRIPT_DIR/run-tests-hardware.sh" "$ESPARGOS_IP" "${EXTRA_ARGS[@]}"
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Hardware tests SKIPPED (no ESPARGOS_IP)"
    echo "  Run: $0 <espargos-ip>"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

echo ""
echo "Results: $PASS suite(s) passed, $FAIL suite(s) failed"
[[ $FAIL -eq 0 ]]
