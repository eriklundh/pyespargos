#!/usr/bin/env bash
# Run the fast headless unit test suite.
# No display, no hardware, no network required.
# Extra args are forwarded to pytest (e.g. -k, -x, -v).
#
# Usage:
#   ./run-tests-unit.sh
#   ./run-tests-unit.sh -v
#   ./run-tests-unit.sh -k test_scanner
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv/bin/activate
exec env QT_QPA_PLATFORM=offscreen \
    pytest demos/demos-menu/tests/unit/ "$@"
