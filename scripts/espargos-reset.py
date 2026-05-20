#!/usr/bin/env python
"""Reset an ESPARGOS controller to a known-good state.

After an unclean demo exit — for example pressing Ctrl-C while a demo is
calibrating — the array's RF switch can be left in REFERENCE or ANTENNA_L
mode. In that state the array no longer receives normal CSI, so the next
demo run fails to calibrate or shows no signal. Until now the only fix was
to power-cycle the controller.

This script restores the RF switch to ANTENNA_RANDOM (normal operation)
and prints the current WiFi configuration so the board state can be
verified at a glance.

Usage:
    python scripts/espargos-reset.py [host]

    host    ESPARGOS controller hostname or IP (default: 192.168.1.2)
"""
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).absolute().parents[1]))

import espargos
import espargos.csi


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.2"

    board = espargos.Board(host)

    before = board.get_rfswitch()
    board.set_rfswitch(espargos.csi.rfswitch_state_t.SENSOR_RFSWITCH_ANTENNA_RANDOM)
    after = board.get_rfswitch()
    print(f"RF switch: {before.name} -> {after.name}")

    wificonf = board.get_wificonf()
    print("WiFi configuration:")
    for key in ("channel-primary", "channel-secondary", "country-code"):
        print(f"  {key}: {wificonf.get(key)}")


if __name__ == "__main__":
    main()
