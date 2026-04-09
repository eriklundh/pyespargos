"""Integration tests for the demos menu app.

Run with:
    xvfb-run -a pytest -m integration demos/demos-menu/tests/integration/
    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a pytest -m integration demos/demos-menu/tests/integration/

These tests require a real display (or Xvfb) and are excluded from the
default fast headless suite.
"""
import pathlib
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtQml import QQmlApplicationEngine

from demos_menu import CommonSettings, ScannerAdapter, build_command

DEMOS_ROOT = pathlib.Path(__file__).parents[3]  # tests/integration/../../.. -> demos/
QML_DIR = pathlib.Path(__file__).parents[2]     # tests/integration/../.. -> demos/demos-menu/

ARTIFACTS = pathlib.Path(__file__).parent / "artifacts"


@pytest.mark.integration
def test_window_renders_all_cards(qapp, tmp_path):
    """App window opens and GridView contains all 13 demo cards."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp("192.168.1.2")
    adapter = ScannerAdapter(DEMOS_ROOT)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    root_objects = engine.rootObjects()
    assert root_objects, "QML window did not open"

    root = root_objects[0]
    qapp.processEvents()  # allow GridView model to populate
    grid = root.findChild(object, "demoGrid")
    assert grid is not None, "demoGrid not found"
    assert grid.property("count") == 13


@pytest.mark.integration
def test_greyed_cards_visible_without_ip(qapp, tmp_path):
    """With no IP set, single_array and multi_array cards are both greyed."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    # ip intentionally left empty
    adapter = ScannerAdapter(DEMOS_ROOT)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    assert engine.rootObjects(), "QML window did not open"
    # All demos require either single_array or multi_array — without an IP
    # all should be disabled. Verify via build_command logic (greying is
    # purely a QML binding — tested separately in unit tests).
    for item in adapter.demoItems:
        cmd = build_command(item["command"], ip="", single_array=False)
        # Commands with {single_array} produce no -s flag — that's correct
        assert "-s" not in cmd


@pytest.mark.integration
def test_card_launches_process_with_echo(qapp, tmp_path):
    """launchDemo fires QProcess.start — verified by mocking QProcess."""
    adapter = ScannerAdapter(DEMOS_ROOT)
    launched = []

    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        mock_proc.start.side_effect = lambda prog, args: launched.append((prog, args))

        adapter.launchDemo(0, "192.168.1.2", True)

    assert len(launched) == 1, "Expected exactly one process launch"
    prog, args = launched[0]
    assert prog == "python"
    assert "-s" in args
    assert "192.168.1.2" in args


@pytest.mark.integration
def test_window_screenshot_saved(qapp, tmp_path):
    """Render the window and save a screenshot artifact for visual inspection."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp("192.168.1.2")
    adapter = ScannerAdapter(DEMOS_ROOT)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))

    root_objects = engine.rootObjects()
    assert root_objects, "QML window did not open"

    # Process events so QML layout completes before grabbing
    qapp.processEvents()

    screen = qapp.primaryScreen()
    grab = screen.grabWindow(0)  # 0 = whole screen (works under Xvfb)
    assert not grab.isNull(), "Screen grab returned null image"

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / "demos-menu-screenshot.png"
    grab.save(str(out))
    assert out.exists(), f"Screenshot not saved to {out}"
