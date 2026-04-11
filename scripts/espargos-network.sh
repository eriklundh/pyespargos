#!/usr/bin/env bash
# scripts/espargos-network.sh — ESPARGOS network configuration for Raspberry Pi 5
#
# Manages two persistent network capabilities between the Pi5 and an ESPARGOS
# device connected via Ethernet:
#
#   Step 1 — Internet forwarding: NAT masquerade so ESPARGOS can reach the
#             internet via the Pi's WiFi connection (e.g. for firmware updates).
#
#   Step 2 — Web proxy: nginx on the Pi proxies the ESPARGOS web interface so
#             it is reachable from the WiFi network without VPN or extra routing.
#
# Usage:
#   sudo ./scripts/espargos-network.sh on      # enable both features
#   sudo ./scripts/espargos-network.sh off     # disable both features
#   sudo ./scripts/espargos-network.sh status  # show current state
#
# Topology assumed:
#   Internet ←→ wlan0 (192.168.2.x/24, DHCP)
#                 Pi5
#               eth0 (192.168.1.1/24, static — managed by NetworkManager)
#                 ↕
#             ESPARGOS (192.168.1.2, default gateway 192.168.1.1)
#
# See scripts/espargos-network.md for full documentation.

set -euo pipefail

# ── Constants ──────────────────────────────────────────────────────────────────
ETH_IFACE="eth0"
WIFI_IFACE="wlan0"
EXPECTED_ETH_IP="192.168.1.1/24"
ESPARGOS_NET="192.168.1.0/24"

SYSCTL_FILE="/etc/sysctl.d/90-espargos-forwarding.conf"
NFT_DIR="/etc/nftables.d"
NFT_FILE="${NFT_DIR}/espargos-nat.nft"
NFT_SERVICE="/etc/systemd/system/espargos-nat.service"

NGINX_AVAILABLE="/etc/nginx/sites-available/espargos"
NGINX_ENABLED="/etc/nginx/sites-enabled/espargos"

# ── Helpers ────────────────────────────────────────────────────────────────────
require_root() {
    [[ $EUID -eq 0 ]] || {
        echo "ERROR: '$(basename "$0") $1' must run as root."
        echo "       Re-run with: sudo $(basename "$0") $1"
        exit 1
    }
}

info()    { echo "  [+] $*"; }
warn()    { echo "  [!] $*" >&2; }
section() { echo; echo "── $* ──"; }

wifi_ip() {
    ip -4 -brief address show dev "${WIFI_IFACE}" 2>/dev/null \
        | awk '{print $3}' | cut -d/ -f1
}

# ── Step 1a — verify eth0 static IP ───────────────────────────────────────────
step_eth0_verify() {
    section "Step 1a — eth0 static IP"
    local current
    current=$(ip -brief address show dev "${ETH_IFACE}" 2>/dev/null | awk '{print $3}')
    if [[ "${current}" == "${EXPECTED_ETH_IP}" ]]; then
        info "eth0 has ${EXPECTED_ETH_IP} — OK (managed by NetworkManager)"
    else
        warn "eth0 address is '${current:-not found}', expected ${EXPECTED_ETH_IP}"
        warn "NetworkManager profile 'netplan-eth0' may need manual correction."
        warn "Continuing anyway — internet forwarding will not work until fixed."
    fi
}

# ── Step 1b — IP forwarding (sysctl) ──────────────────────────────────────────
step_ipforward_on() {
    section "Step 1b — IP forwarding (persistent via sysctl.d)"
    cat > "${SYSCTL_FILE}" <<EOF
# Managed by espargos-network.sh — do not edit by hand.
# Enables IPv4 forwarding so ESPARGOS can reach the internet via wlan0 NAT.
net.ipv4.ip_forward = 1
EOF
    sysctl -q -p "${SYSCTL_FILE}"
    info "ip_forward = 1 applied now and persistent across reboots"
    info "  File: ${SYSCTL_FILE}"
}

step_ipforward_off() {
    rm -f "${SYSCTL_FILE}"
    sysctl -q -w net.ipv4.ip_forward=0
    info "ip_forward = 0 (file ${SYSCTL_FILE} removed)"
}

# ── Step 1c — NAT masquerade (nftables + systemd unit) ────────────────────────
step_nat_on() {
    section "Step 1c — NAT masquerade (nftables)"
    mkdir -p "${NFT_DIR}"

    # nftables rule file
    cat > "${NFT_FILE}" <<EOF
# Managed by espargos-network.sh — do not edit by hand.
# Masquerades outbound traffic from ESPARGOS (${ESPARGOS_NET}) via ${WIFI_IFACE}.
table ip espargos_nat {
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr ${ESPARGOS_NET} oifname "${WIFI_IFACE}" masquerade
    }
}
EOF

    # Dedicated systemd unit for boot persistence (avoids modifying /etc/nftables.conf)
    cat > "${NFT_SERVICE}" <<'UNIT'
[Unit]
Description=ESPARGOS NAT masquerade rules
Documentation=file:///home/eriklundh/pyespargos/scripts/espargos-network.md
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/nft -f /etc/nftables.d/espargos-nat.nft
ExecStop=/usr/sbin/nft delete table ip espargos_nat
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

    # Apply rules immediately (delete first for idempotent reload)
    /usr/sbin/nft delete table ip espargos_nat 2>/dev/null || true
    /usr/sbin/nft -f "${NFT_FILE}"

    systemctl daemon-reload
    systemctl enable espargos-nat
    info "NAT masquerade active: ${ESPARGOS_NET} → ${WIFI_IFACE} (masquerade)"
    info "espargos-nat.service enabled (auto-starts on reboot)"
}

step_nat_off() {
    # Delete live rule immediately
    /usr/sbin/nft delete table ip espargos_nat 2>/dev/null || true
    # Disable and remove service (prevent boot re-application)
    systemctl disable espargos-nat 2>/dev/null || true
    rm -f "${NFT_FILE}" "${NFT_SERVICE}"
    systemctl daemon-reload
    info "NAT masquerade removed; espargos-nat.service disabled"
}

# ── Step 2 — nginx reverse proxy ──────────────────────────────────────────────
step_proxy_on() {
    section "Step 2 — nginx reverse proxy (port 80)"

    if ! command -v nginx &>/dev/null; then
        echo "  Installing nginx..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
    fi

    mkdir -p "$(dirname "${NGINX_AVAILABLE}")"

    # Write nginx site config (single-quoted heredoc preserves $nginx_vars)
    cat > "${NGINX_AVAILABLE}" <<'NGINX'
# ESPARGOS reverse proxy — managed by espargos-network.sh
# Proxies http://<pi-wifi-ip>/ to the ESPARGOS web interface at http://192.168.1.2/.
server {
    listen 80 default_server;
    server_name _;

    # WebSocket support for ESPARGOS live data streams
    proxy_http_version 1.1;
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host            192.168.1.2;
    proxy_set_header X-Real-IP       $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    proxy_read_timeout    120s;
    proxy_connect_timeout  10s;
    proxy_send_timeout    120s;

    location / {
        proxy_pass http://192.168.1.2/;
    }
}
NGINX

    # Remove default nginx site to avoid port 80 conflict
    rm -f /etc/nginx/sites-enabled/default

    ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
    nginx -t

    systemctl enable nginx
    systemctl restart nginx

    local ip
    ip=$(wifi_ip)
    info "nginx proxy active: http://${ip:-<pi-wifi-ip>}/ → http://192.168.1.2/"
    info "nginx.service enabled (auto-starts on reboot)"
}

step_proxy_off() {
    rm -f "${NGINX_ENABLED}"

    if command -v nginx &>/dev/null; then
        local remaining
        remaining=$(ls /etc/nginx/sites-enabled/ 2>/dev/null | wc -l)
        if [[ "${remaining}" -eq 0 ]]; then
            systemctl stop nginx 2>/dev/null || true
            info "nginx stopped (no other sites remain)"
        else
            nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
            info "nginx reloaded (${remaining} other site(s) still active)"
        fi
    fi
    info "ESPARGOS nginx site disabled"
}

# ── configure_on ───────────────────────────────────────────────────────────────
configure_on() {
    echo "=== ESPARGOS network: enabling ==="
    step_eth0_verify
    step_ipforward_on
    step_nat_on
    step_proxy_on
    echo
    echo "=== ESPARGOS network is ON ==="
    echo
    echo "  Internet forwarding : ${ESPARGOS_NET} → ${WIFI_IFACE} (NAT masquerade)"
    local ip
    ip=$(wifi_ip)
    echo "  Web proxy           : http://${ip:-<pi-wifi-ip>}/ → http://192.168.1.2/"
    echo
    echo "  NOTE: The ESPARGOS unit must have its default gateway set to 192.168.1.1"
    echo "        for internet forwarding to work. This is the ESPARGOS factory default."
}

# ── configure_off ──────────────────────────────────────────────────────────────
configure_off() {
    echo "=== ESPARGOS network: disabling ==="
    step_proxy_off
    step_nat_off
    step_ipforward_off
    echo
    echo "=== ESPARGOS network is OFF ==="
    echo
    echo "  eth0 (${EXPECTED_ETH_IP}) preserved — direct Pi↔ESPARGOS comms unchanged."
}

# ── show_status ────────────────────────────────────────────────────────────────
show_status() {
    echo "=== ESPARGOS network status ==="
    echo

    # eth0 IP
    local eth_ip
    eth_ip=$(ip -brief address show dev "${ETH_IFACE}" 2>/dev/null | awk '{print $3}')
    if [[ "${eth_ip}" == "${EXPECTED_ETH_IP}" ]]; then
        printf "  %-20s %s  ✓\n" "eth0 IP:" "${eth_ip}"
    else
        printf "  %-20s %s  ✗  (expected %s)\n" "eth0 IP:" "${eth_ip:-not found}" "${EXPECTED_ETH_IP}"
    fi

    # ip_forward
    local fwd
    fwd=$(cat /proc/sys/net/ipv4/ip_forward)
    if [[ "${fwd}" == "1" ]]; then
        printf "  %-20s %s\n" "ip_forward:" "1 (enabled)  ✓"
    else
        printf "  %-20s %s\n" "ip_forward:" "0 (disabled)"
    fi
    if [[ -f "${SYSCTL_FILE}" ]]; then
        printf "  %-20s %s\n" "  sysctl file:" "${SYSCTL_FILE} (persistent)"
    else
        printf "  %-20s %s\n" "  sysctl file:" "absent (not persistent across reboot)"
    fi

    echo

    # nftables NAT
    if systemctl is-active espargos-nat &>/dev/null 2>&1; then
        printf "  %-20s %s\n" "espargos-nat:" "active  ✓"
    elif systemctl is-enabled espargos-nat &>/dev/null 2>&1; then
        printf "  %-20s %s\n" "espargos-nat:" "inactive (enabled for boot)"
    else
        printf "  %-20s %s\n" "espargos-nat:" "not configured"
    fi
    if /usr/sbin/nft list table ip espargos_nat &>/dev/null 2>&1; then
        printf "  %-20s %s\n" "  nft table:" "present  ✓"
    else
        printf "  %-20s %s\n" "  nft table:" "absent"
    fi

    echo

    # nginx
    if ! command -v nginx &>/dev/null; then
        printf "  %-20s %s\n" "nginx:" "not installed"
    else
        local ng_status
        ng_status=$(systemctl is-active nginx 2>/dev/null || echo "inactive")
        if [[ "${ng_status}" == "active" ]]; then
            printf "  %-20s %s\n" "nginx:" "active  ✓"
        else
            printf "  %-20s %s\n" "nginx:" "${ng_status}"
        fi
        if [[ -L "${NGINX_ENABLED}" ]]; then
            printf "  %-20s %s\n" "  espargos site:" "enabled  ✓"
        else
            printf "  %-20s %s\n" "  espargos site:" "disabled"
        fi
    fi

    echo
}

# ── Entry point ────────────────────────────────────────────────────────────────
case "${1:-}" in
    on)
        require_root on
        configure_on
        ;;
    off)
        require_root off
        configure_off
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: sudo $(basename "$0") {on|off|status}"
        echo
        echo "  on      Enable internet forwarding for ESPARGOS + nginx web proxy"
        echo "  off     Disable both features (eth0 static IP is preserved)"
        echo "  status  Show current state of each component (no root required)"
        echo
        echo "See scripts/espargos-network.md for full documentation."
        exit 1
        ;;
esac
