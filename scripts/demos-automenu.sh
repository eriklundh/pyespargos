#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# demos-automenu.sh — install/remove autostart of the ESPARGOS demos menu
#
# Manages a systemd user service that starts demos/menu.py with the graphical
# desktop session (labwc/Wayland) on Raspberry Pi OS 13 (Trixie).
#
# Usage:
#   demos-automenu.sh on  [IP] [-s|--single-array] [--fullscreen]
#   demos-automenu.sh off
#   demos-automenu.sh status
#
# 'on'  — write/replace the unit file, enable linger, enable and start the service.
#         Re-running 'on' with different args replaces the ExecStart args.
# 'off' — stop and disable the service, disable linger.
#
# Requires: systemd user session, loginctl, Python venv at .venv/
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
MENU_SCRIPT="${REPO_ROOT}/demos/menu.py"
SERVICE_NAME="demos-automenu"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/${SERVICE_NAME}.service"

# ── helpers ────────────────────────────────────────────────────────────────────

info()    { echo "  [+] $*"; }
warn()    { echo "  [!] $*" >&2; }
section() { echo; echo "── $* ──"; }

usage() {
    echo "Usage: $(basename "$0") on  [IP] [-s|--single-array] [--fullscreen]"
    echo "       $(basename "$0") off"
    echo "       $(basename "$0") status"
    echo
    echo "  on   Write (or replace) the unit file, enable linger, and start the service."
    echo "  off  Stop, disable the service, and disable linger."
    echo
    echo "Arguments forwarded to demos/menu.py at autostart:"
    echo "  IP                  ESPARGOS board IP address (e.g. 192.168.1.2)"
    echo "  -s, --single-array  Enable single-array mode"
    echo "  --fullscreen        Start the menu window in fullscreen mode"
}

# ── on ─────────────────────────────────────────────────────────────────────────

cmd_on() {
    # Parse optional args to forward to menu.py
    local menu_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -s|--single-array) menu_args+=("-s"); shift ;;
            --fullscreen)      menu_args+=("--fullscreen"); shift ;;
            -*)                warn "Unknown option: $1"; usage; exit 1 ;;
            *)                 menu_args+=("$1"); shift ;;  # positional IP
        esac
    done

    # Validate prereqs
    if [[ ! -x "${VENV_PYTHON}" ]]; then
        echo "ERROR: venv Python not found at ${VENV_PYTHON}"
        echo "       Run: python3 -m venv ${REPO_ROOT}/.venv --system-site-packages"
        exit 1
    fi
    if [[ ! -f "${MENU_SCRIPT}" ]]; then
        echo "ERROR: menu script not found at ${MENU_SCRIPT}"
        exit 1
    fi

    section "Writing unit file"
    mkdir -p "${SERVICE_DIR}"

    # Build ExecStart line — embed resolved paths and any forwarded args
    local exec_start="${VENV_PYTHON} ${MENU_SCRIPT}"
    if (( ${#menu_args[@]} > 0 )); then
        exec_start="${exec_start} ${menu_args[*]}"
    fi

    # %t is a systemd unit specifier (expands to XDG_RUNTIME_DIR = /run/user/<uid>).
    # It starts with % so bash does not expand it in this heredoc.
    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=ESPARGOS Demos Menu
Documentation=https://github.com/eriklundh/pyespargos
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=${exec_start}
Restart=on-failure
RestartSec=5
Environment=WAYLAND_DISPLAY=wayland-1
Environment=XDG_RUNTIME_DIR=%t
Environment=QT_QPA_PLATFORM=wayland

[Install]
WantedBy=graphical-session.target
EOF

    info "Unit file written:  ${SERVICE_FILE}"
    info "ExecStart:          ${exec_start}"

    section "Enabling linger"
    loginctl enable-linger "$(whoami)"
    info "Linger enabled for $(whoami) — user services survive logout"

    section "Enabling and starting service"
    systemctl --user daemon-reload
    systemctl --user enable "${SERVICE_NAME}"

    if systemctl --user is-active --quiet "${SERVICE_NAME}"; then
        systemctl --user restart "${SERVICE_NAME}"
        info "Service restarted (new args applied)"
    else
        systemctl --user start "${SERVICE_NAME}" || true
        info "Service started"
    fi

    echo
    info "demos-automenu is enabled. The menu will autostart with the graphical session."
}

# ── off ────────────────────────────────────────────────────────────────────────

cmd_off() {
    section "Stopping and disabling service"
    if systemctl --user disable --now "${SERVICE_NAME}" 2>/dev/null; then
        info "Service stopped and disabled"
    else
        warn "${SERVICE_NAME} was not active or not installed"
    fi

    section "Disabling linger"
    loginctl disable-linger "$(whoami)"
    info "Linger disabled for $(whoami)"

    echo
    info "demos-automenu autostart is off."
    info "Unit file preserved at ${SERVICE_FILE} — run '$(basename "$0") on' to re-enable."
}

# ── status ─────────────────────────────────────────────────────────────────────

show_status() {
    section "demos-automenu status"

    if systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo "  service          : active (running)"
    elif systemctl --user is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo "  service          : enabled (not running)"
    elif [[ -f "${SERVICE_FILE}" ]]; then
        echo "  service          : installed but not enabled"
    else
        echo "  service          : not installed"
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        local exec_line
        exec_line="$(grep '^ExecStart=' "${SERVICE_FILE}" | sed 's/^ExecStart=//')"
        echo "  unit file        : ${SERVICE_FILE}"
        echo "  ExecStart        : ${exec_line}"
    fi

    local linger
    linger="$(loginctl show-user "$(whoami)" --property=Linger --value 2>/dev/null \
              || echo unknown)"
    echo "  linger           : ${linger}"

    if systemctl --user is-active --quiet graphical-session.target 2>/dev/null; then
        echo "  graphical-session: active"
    else
        echo "  graphical-session: inactive"
    fi
}

# ── dispatch ───────────────────────────────────────────────────────────────────

ACTION="${1:-}"
shift || true

case "${ACTION}" in
    on)     cmd_on "$@" ;;
    off)    cmd_off ;;
    status) show_status ;;
    *)      usage; exit 1 ;;
esac
