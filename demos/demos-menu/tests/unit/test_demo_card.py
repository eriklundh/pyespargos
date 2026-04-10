"""Unit tests for DemoCard greying logic and GridView population."""
import pathlib
import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlApplicationEngine, QQmlComponent
from PyQt6.QtTest import QSignalSpy

from demos_menu import CommonSettings, DemoScanner, ScannerAdapter

QML_DIR = pathlib.Path(__file__).parents[2]


def _make_engine(tmp_path, ip="", single_array=False, items=None):
    """Helper: build an engine with settings and scanner wired up."""
    engine = QQmlApplicationEngine()
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setIp(ip)
    settings.setSingleArray(single_array)

    if items is None:
        demos_root = pathlib.Path(__file__).parents[3]
        adapter = ScannerAdapter(DemoScanner(demos_root), settings)
    else:
        # Inject a fake adapter for controlled testing
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.demoItems = items

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    return engine, settings, adapter


# ---------------------------------------------------------------------------
# GridView population
# ---------------------------------------------------------------------------

def test_grid_loads_without_error(qapp, tmp_path):
    engine, *_ = _make_engine(tmp_path)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))
    assert engine.rootObjects(), "QML failed to load"


def test_grid_model_count_matches_scanner(qapp, tmp_path):
    engine, _, adapter = _make_engine(tmp_path)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "demos-menu.qml")))
    qapp.processEvents()
    root = engine.rootObjects()[0]
    grid = root.findChild(object, "demoGrid")
    assert grid is not None, "demoGrid objectName not found"
    assert grid.property("count") == len(adapter.demoItems)


# ---------------------------------------------------------------------------
# Requirements / greying logic
# Tests probe the meetsRequirements logic via a Python helper that mirrors
# the QML property — kept in sync with DemoCard.qml manually.
# ---------------------------------------------------------------------------

def _meets_requirements(singleArrayOnly: bool, disabled: bool, ip: str, single_array: bool) -> bool:
    """Mirror of DemoCard.qml meetsRequirements property."""
    if disabled:
        return False
    if singleArrayOnly and not single_array:
        return False
    if not ip:
        return False
    return True


def test_no_ip_always_gray():
    assert _meets_requirements(singleArrayOnly=False, disabled=False, ip="", single_array=False) is False


def test_with_ip_enabled():
    assert _meets_requirements(singleArrayOnly=False, disabled=False, ip="192.168.1.2", single_array=False) is True


def test_disabled_always_gray():
    assert _meets_requirements(singleArrayOnly=False, disabled=True, ip="192.168.1.2", single_array=True) is False


def test_single_array_only_gray_in_multi_array_mode():
    assert _meets_requirements(singleArrayOnly=True, disabled=False, ip="192.168.1.2", single_array=False) is False


def test_single_array_only_enabled_in_single_array_mode():
    assert _meets_requirements(singleArrayOnly=True, disabled=False, ip="192.168.1.2", single_array=True) is True


def test_no_flags_enabled_with_ip():
    assert _meets_requirements(singleArrayOnly=False, disabled=False, ip="192.168.1.2", single_array=True) is True
