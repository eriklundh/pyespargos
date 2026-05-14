"""Tests for the minimal app shell — engine loads, context properties accessible."""
import pathlib
import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlApplicationEngine

from demos_menu import CommonSettings, DemoScanner, ScannerAdapter


def test_scanner_adapter_exposes_items(qapp, tmp_path):
    """ScannerAdapter.demoItems returns visible items — 15 with singleArray=True (default)."""
    demos_root = pathlib.Path(__file__).parents[3]
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(demos_root), settings)
    items = adapter.demoItems
    # singleArray defaults to True: 2 combined_array_only demos are hidden
    assert len(items) == 15
    assert all("name" in item for item in items)


def test_scanner_adapter_exposes_all_items_in_multi_array_mode(qapp, tmp_path):
    """All 17 demos visible when singleArray=False (multi-array mode)."""
    demos_root = pathlib.Path(__file__).parents[3]
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    settings.setSingleArray(False)
    adapter = ScannerAdapter(DemoScanner(demos_root), settings)
    assert len(adapter.demoItems) == 17


def test_scanner_adapter_items_are_serialisable(qapp, tmp_path):
    """demoItems must contain only JSON-serialisable types for QML consumption."""
    import json
    demos_root = pathlib.Path(__file__).parents[3]
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(demos_root), settings)
    # demo_dir is a Path — should be converted to str by the adapter
    json.dumps(adapter.demoItems)  # must not raise


def test_qml_engine_loads(qapp, tmp_path):
    """QML engine loads demos-menu.qml without errors."""
    qml_file = pathlib.Path(__file__).parents[2] / "demos-menu.qml"
    demos_root = pathlib.Path(__file__).parents[3]

    engine = QQmlApplicationEngine()

    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(demos_root), settings)
    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)

    engine.load(QUrl.fromLocalFile(str(qml_file)))
    assert engine.rootObjects(), "QML engine produced no root objects — check for QML errors"
