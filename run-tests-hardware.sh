#!/usr/bin/env bash
# Run the hardware test suite against a real ESPARGOS board and cameras.
#
# Does NOT set QT_QPA_PLATFORM=offscreen — Qt multimedia needs the real display
# to enumerate cameras (Logitech C920) and deliver frames.
# Demo sub-processes spawned by the tests still use offscreen internally.
#
# ESPARGOS IP can be supplied as:
#   - First positional argument:  ./run-tests-hardware.sh 192.168.1.x
#   - Environment variable:       ESPARGOS_IP=192.168.1.x ./run-tests-hardware.sh
#
# Optional flags:
#   --camera-backend qt|picamera2|auto   (default: auto = test both)
#
# Extra args after the IP are forwarded to pytest.
#
# Usage:
#   ./run-tests-hardware.sh 192.168.1.x
#   ./run-tests-hardware.sh 192.168.1.x --camera-backend picamera2
#   ./run-tests-hardware.sh 192.168.1.x -k test_calibration -v
#   ESPARGOS_IP=192.168.1.x ./run-tests-hardware.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# Resolve ESPARGOS IP
if [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ESPARGOS_IP="$1"
    shift
elif [[ -z "${ESPARGOS_IP:-}" ]]; then
    echo "Error: ESPARGOS IP required."
    echo ""
    echo "Usage: $0 <espargos-ip> [--camera-backend qt|picamera2|auto] [pytest-args...]"
    echo "  or:  ESPARGOS_IP=192.168.x.x $0 [pytest-args...]"
    exit 1
fi

source .venv/bin/activate

exec pytest -m hardware \
    --espargos-ip "$ESPARGOS_IP" \
    demos/demos-menu/tests/hardware/ \
    "$@"
