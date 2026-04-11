# ESPARGOS Network Configuration for Raspberry Pi 5

Configures two network features between a Raspberry Pi 5 and an ESPARGOS unit
connected via the Pi's Ethernet jack. Both features are toggled together with a
single script and survive reboots.

## Network topology

```
        Internet
           │
     ┌─────▼──────┐
     │  Router    │  192.168.2.1
     │  (WiFi AP) │
     └─────┬──────┘
           │ wlan0  192.168.2.78  (DHCP)
     ┌─────▼──────┐
     │  Pi 5      │  eth0  192.168.1.1  (static)
     └─────┬──────┘
           │
     ┌─────▼──────┐
     │  ESPARGOS  │  192.168.1.2  (static, gateway 192.168.1.1)
     └────────────┘
```

- **Feature 1 — Internet forwarding**: packets from 192.168.1.2 are NAT-masqueraded
  out of `wlan0` so ESPARGOS can fetch firmware updates without a direct WiFi connection.
- **Feature 2 — Web proxy**: nginx on the Pi forwards HTTP requests arriving on
  `wlan0` (port 80) to the ESPARGOS web interface at `http://192.168.1.2/`.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Raspberry Pi OS Bookworm/Trixie (Debian 12/13) | Tested on Trixie (Debian 13) |
| NetworkManager managing both interfaces | Confirmed: `nmcli device status` |
| `nftables` package installed | `sudo apt-get install nftables` |
| `nginx` | Installed automatically by the script if missing |
| Root / sudo | `on` and `off` require root; `status` does not |

The `eth0` interface must already have a static IP of `192.168.1.1/24` managed by
NetworkManager. On a fresh Raspberry Pi OS Trixie install this is set up via a
`netplan-eth0` profile — the script does **not** modify it.

## Quick start

```bash
# Enable both features
sudo ./scripts/espargos-network.sh on

# Check state at any time (no sudo needed)
./scripts/espargos-network.sh status

# Disable both features
sudo ./scripts/espargos-network.sh off
```

After `on`:
- ESPARGOS can reach the internet through the Pi's WiFi.
- The ESPARGOS web interface is accessible at `http://192.168.2.78/` (the Pi's
  WiFi IP — check with `ip -brief address show wlan0`).

## ESPARGOS gateway requirement

For internet forwarding to work the ESPARGOS unit must use the Pi as its default
gateway. The ESPARGOS factory default is `192.168.1.1`, which matches the Pi's
`eth0` IP. If your unit was reconfigured, set the gateway back to `192.168.1.1`
via the ESPARGOS web interface before running the script.

## What the script does

### `on`

**Step 1a — eth0 IP verification**

Checks that `eth0` has address `192.168.1.1/24`. Prints a warning if not; the
NetworkManager `netplan-eth0` profile is never modified by the script.

**Step 1b — IP forwarding (sysctl)**

Creates `/etc/sysctl.d/90-espargos-forwarding.conf`:

```
net.ipv4.ip_forward = 1
```

Applies it immediately with `sysctl -p`. The file is loaded automatically by
`systemd-sysctl.service` on every subsequent boot.

**Step 1c — NAT masquerade (nftables)**

Creates two files:

- `/etc/nftables.d/espargos-nat.nft` — the nftables rule:
  ```nft
  table ip espargos_nat {
      chain postrouting {
          type nat hook postrouting priority srcnat;
          ip saddr 192.168.1.0/24 oifname "wlan0" masquerade
      }
  }
  ```

- `/etc/systemd/system/espargos-nat.service` — a oneshot systemd unit whose
  `ExecStart` loads the rule file and `ExecStop` deletes the table.

The rule is applied immediately with `nft -f`. The service is `systemctl enable`d
so it loads the rule at every boot. The main `/etc/nftables.conf` is **not**
modified, avoiding conflicts with Raspberry Pi OS tooling.

**Step 2 — nginx reverse proxy**

Installs nginx if not present (`apt-get install -y nginx`), writes
`/etc/nginx/sites-available/espargos`, and enables it:

```nginx
server {
    listen 80 default_server;
    location / { proxy_pass http://192.168.1.2/; }
    # + proxy headers and WebSocket support
}
```

The default nginx site (`sites-enabled/default`) is removed to avoid a port 80
conflict. nginx is `systemctl enable`d and restarted.

### `off`

Reverses all changes in reverse order:

1. Removes the nginx site symlink; reloads or stops nginx depending on whether
   other sites remain.
2. Deletes the live nftables table (`nft delete table ip espargos_nat`), disables
   and removes `espargos-nat.service`.
3. Removes the sysctl file and sets `ip_forward = 0` immediately.

The `eth0` static IP and its NetworkManager profile are **never touched** by `off`.
Direct Pi↔ESPARGOS communication on 192.168.1.x continues to work after `off`.

### `status`

Prints a concise table — does not require `sudo`:

```
=== ESPARGOS network status ===

  eth0 IP:             192.168.1.1/24  ✓
  ip_forward:          1 (enabled)  ✓
    sysctl file:       /etc/sysctl.d/90-espargos-forwarding.conf (persistent)

  espargos-nat:        active  ✓
    nft table:         present  ✓

  nginx:               active  ✓
    espargos site:     enabled  ✓
```

## Persistence summary

| Component | Persistence mechanism |
|-----------|----------------------|
| eth0 static IP | NetworkManager `netplan-eth0` profile (pre-existing) |
| ip_forward | `/etc/sysctl.d/90-espargos-forwarding.conf` via `systemd-sysctl` |
| NAT masquerade | `/etc/systemd/system/espargos-nat.service` (enabled unit) |
| nginx proxy | `systemctl enable nginx` + site symlink in `sites-enabled/` |

## Verification

```bash
# After: sudo ./scripts/espargos-network.sh on

# Step 1 — IP forwarding
cat /proc/sys/net/ipv4/ip_forward          # 1
systemctl status espargos-nat              # active (running)
nft list table ip espargos_nat             # shows masquerade rule

# Step 2 — nginx proxy
systemctl status nginx                     # active (running)
curl -o /dev/null -w "%{http_code}\n" http://192.168.2.78/
# 200 (or a redirect from the ESPARGOS web app)

# Test internet access from the ESPARGOS unit (if SSH is available):
# ssh root@192.168.1.2 'curl -s --max-time 5 http://neverssl.com | head -1'
# Should return an HTTP response, not a connection timeout.

# After: sudo ./scripts/espargos-network.sh off
cat /proc/sys/net/ipv4/ip_forward          # 0
nft list tables                            # espargos_nat absent
systemctl is-active espargos-nat           # inactive
ping -c 1 192.168.1.2                      # still reachable (eth0 intact)
```

## Troubleshooting

**`eth0` shows the wrong IP**

Check the active NetworkManager connection:
```bash
nmcli connection show netplan-eth0
nmcli device show eth0
```
If the IP is wrong, edit the connection:
```bash
sudo nmcli connection modify netplan-eth0 \
    ipv4.method manual \
    ipv4.addresses 192.168.1.1/24 \
    ipv4.never-default yes \
    connection.autoconnect yes
sudo nmcli connection up netplan-eth0
```

**ESPARGOS cannot reach the internet after `on`**

1. Verify `ip_forward = 1`: `cat /proc/sys/net/ipv4/ip_forward`
2. Verify the nftables rule is loaded: `sudo nft list table ip espargos_nat`
3. Check that `wlan0` has a default route: `ip route show default`
4. Confirm the ESPARGOS gateway is `192.168.1.1` (ESPARGOS web UI → Network settings)

**nginx config test fails**

```bash
sudo nginx -t    # shows the exact error
sudo journalctl -u nginx -n 30    # recent nginx log
```

If port 80 is already in use:
```bash
sudo ss -tlnp | grep ':80'    # which process holds port 80
```

**Changes did not survive reboot**

Check the relevant services:
```bash
systemctl is-enabled espargos-nat    # should print "enabled"
systemctl is-enabled nginx           # should print "enabled"
ls /etc/sysctl.d/90-espargos-forwarding.conf    # should exist
```

Re-run `sudo ./scripts/espargos-network.sh on` to restore all state.
