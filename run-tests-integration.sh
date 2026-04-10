#!/usr/bin/env bash
# Run the integration test suite under a virtual X display (Xvfb).
# Requires: xvfb-run (sudo apt install xvfb)
# No ESPARGOS board or cameras required.
# Extra args are forwarded to pytest.
#
# Usage:
#   ./run-tests-integration.sh
#   ./run-tests-integration.sh -v
#   ./run-tests-integration.sh -k test_window
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv/bin/activate
exec env LIBGL_ALWAYS_SOFTWARE=1 QT_QUICK_BACKEND=software \
    xvfb-run -a \
    pytest -m integration \
    demos/demos-menu/tests/integration/ "$@"
