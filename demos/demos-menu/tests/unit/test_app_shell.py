"""Tests for the minimal app shell — engine loads, context properties accessible."""
import pathlib
import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlApplicationEngine

from demos_menu import CommonSettings, ScannerAdapter


def test_scanner_adapter_exposes_items(tmp_path):
    """ScannerAdapter.demoItems returns a list of dicts from the real demos tree."""
    demos_root = pathlib.Path(__file__).parents[3]
    adapter = ScannerAdapter(demos_root)
    items = adapter.demoItems
    assert len(items) == 13
    assert all("name" in item for item in items)


def test_scanner_adapter_items_are_serialisable(tmp_path):
    """demoItems must contain only JSON-serialisable types for QML consumption."""
    import json
    demos_root = pathlib.Path(__file__).parents[3]
    adapter = ScannerAdapter(demos_root)
    # demo_dir is a Path — should be converted to str by the adapter
    json.dumps(adapter.demoItems)  # must not raise


def test_qml_engine_loads(qapp, tmp_path):
    """QML engine loads demos-menu.qml without errors."""
    qml_file = pathlib.Path(__file__).parents[2] / "demos-menu.qml"
    demos_root = pathlib.Path(__file__).parents[3]

    engine = QQmlApplicationEngine()

    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(demos_root)
    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)

    engine.load(QUrl.fromLocalFile(str(qml_file)))
    assert engine.rootObjects(), "QML engine produced no root objects — check for QML errors"
