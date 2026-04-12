#!/usr/bin/env python3
"""Thin launcher for the ESPARGOS demos menu.

Run from the repo root or from demos/:
    python demos/menu.py
    python demos/menu.py 192.168.1.2
    python demos/menu.py -s 192.168.1.2
    python demos/menu.py --single-array 192.168.1.2
    python demos/menu.py --fullscreen
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "demos-menu"))

from demos_menu import run


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ESPARGOS demos launcher menu",
        epilog="IP and --single-array pre-fill the settings panel and are persisted.",
    )
    p.add_argument(
        "ip", nargs="?", default=None, metavar="IP",
        help="ESPARGOS board IP address",
    )
    p.add_argument(
        "-s", "--single-array", dest="single_array",
        action="store_const", const=True, default=None,
        help="Enable single-array mode",
    )
    p.add_argument(
        "--fullscreen",
        action="store_true", default=False,
        help="Start menu in fullscreen mode",
    )
    return p


if __name__ == "__main__":
    # parse_known_args: Qt may consume its own flags (--platform, --display …)
    args, _ = _make_parser().parse_known_args()
    demos_root = pathlib.Path(__file__).parent
    sys.exit(run(demos_root, ip=args.ip, single_array=args.single_array,
                 fullscreen=args.fullscreen))
