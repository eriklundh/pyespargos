#!/usr/bin/env python3
"""Thin launcher for the ESPARGOS demos menu.

Run from the repo root or from demos/:
    python demos/menu.py
    cd demos && python menu.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "demos-menu"))

from demos_menu import run

demos_root = pathlib.Path(__file__).parent
sys.exit(run(demos_root))
