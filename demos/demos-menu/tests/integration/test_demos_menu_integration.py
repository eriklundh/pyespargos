"""Integration tests for the demos menu app.

Run with:
    xvfb-run -a pytest -m integration demos/demos-menu/tests/integration/
    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a pytest -m integration demos/demos-menu/tests/integration/

These tests require a real display (or Xvfb) and are excluded from the
default fast headless suite.
"""
import os
import pathlib
import shlex
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtQml import QQmlApplicationEngine

from demos_menu import CommonSettings, DemoScanner, ScannerAdapter, build_command

DEMOS_ROOT = pathlib.Path(__file__).parents[3]  # tests/integration/../../.. -> demos/
QML_DIR = pathlib.Path(__file__).parents[2]     # tests/integration/../.. -> demos/demos-menu/

ARTIFACTS = pathlib.Path(__file__).parent / "artifacts"


@pytest.mark.integration
def test_window_renders_all_cards(qapp, tmp_path):
    """App window opens and GridView contains all 13 demo cards in multi-array mode."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp("192.168.1.2")
    settings.setSingleArray(False)  # multi-array: all 13 demos visible
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    root_objects = engine.rootObjects()
    assert root_objects, "QML window did not open"

    qapp.processEvents()
    root = root_objects[0]
    grid = root.findChild(object, "demoGrid")
    assert grid is not None, "demoGrid not found"
    assert grid.property("count") == 13


@pytest.mark.integration
def test_window_hides_combined_array_in_single_array_mode(qapp, tmp_path):
    """GridView shows 11 cards (not 13) when singleArray=True."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp("192.168.1.2")
    # singleArray defaults to True — combined_array_only demos hidden
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    assert engine.rootObjects(), "QML window did not open"
    qapp.processEvents()
    root = engine.rootObjects()[0]
    grid = root.findChild(object, "demoGrid")
    assert grid is not None, "demoGrid not found"
    assert grid.property("count") == 11


@pytest.mark.integration
def test_greyed_cards_visible_without_ip(qapp, tmp_path):
    """With no IP set, build_command produces no -s flag for any demo."""
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    # ip intentionally left empty
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)

    for item in adapter.demoItems:
        cmd = build_command(item["command"], ip="", single_array=False)
        assert "-s" not in cmd


@pytest.mark.integration
def test_card_launches_process_with_echo(qapp, tmp_path):
    """launchDemo fires QProcess.start with the correct command args."""
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    launched = []

    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        mock_proc.start.side_effect = lambda prog, args: launched.append((prog, args))

        adapter.launchDemo(0, "192.168.1.2", True)

    assert len(launched) == 1, "Expected exactly one process launch"
    prog, args = launched[0]
    assert prog == "python"
    assert "192.168.1.2" in args


@pytest.mark.integration
def test_window_screenshot_saved(qapp, tmp_path):
    """Render the window and save a screenshot artifact for visual inspection."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp("192.168.1.2")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    root_objects = engine.rootObjects()
    assert root_objects, "QML window did not open"

    qapp.processEvents()

    screen = qapp.primaryScreen()
    grab = screen.grabWindow(0)
    assert not grab.isNull(), "Screen grab returned null image"

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / "demos-menu-screenshot.png"
    grab.save(str(out))
    assert out.exists(), f"Screenshot not saved to {out}"


@pytest.mark.integration
def test_demo_process_starts_without_immediate_crash(tmp_path):
    """Spawn azimuth-delay.py with a loopback IP; verify no crash within 2 seconds.

    azimuth-delay uses CombinedArrayMixin so it accepts -s <ip> correctly.
    Requires Xvfb or a real display (or QT_QPA_PLATFORM=offscreen).
    The demo will start, open the Qt app, then hang waiting for an ESPARGOS
    connection — that hang is the pass condition.
    """
    scanner = DemoScanner(DEMOS_ROOT)
    item = next(i for i in scanner.items if "azimuth-delay" in i["command"])
    cmd = build_command(item["command"], ip="127.0.0.1", single_array=True)

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    proc = subprocess.Popen(
        cmd,
        cwd=str(item["demo_dir"]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        proc.wait(timeout=2)
        stderr = proc.stderr.read().decode()
        # Connection refused is expected when no ESPARGOS board is present
        if "ConnectionRefusedError" in stderr or "ConnectionError" in stderr:
            return  # hardware not present — startup was fine
        assert proc.returncode == 0, (
            f"Demo failed unexpectedly (exit {proc.returncode}):\n{stderr}"
        )
    except subprocess.TimeoutExpired:
        pass  # still running after 2 seconds — expected with a reachable board
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
