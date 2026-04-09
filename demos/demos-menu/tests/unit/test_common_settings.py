"""Unit tests for CommonSettings — Qt properties, signals, and persistence."""
import json
import pytest
from PyQt6.QtTest import QSignalSpy

from demos_menu import CommonSettings


@pytest.fixture
def settings(tmp_path):
    """Fresh CommonSettings backed by an isolated temp file."""
    return CommonSettings(settings_path=tmp_path / "settings.json")


# ---------------------------------------------------------------------------
# Tests — defaults
# ---------------------------------------------------------------------------

def test_default_ip_is_empty(settings):
    assert settings.ip == ""


def test_default_single_array_is_false(settings):
    assert settings.singleArray is False


# ---------------------------------------------------------------------------
# Tests — setters and signals
# ---------------------------------------------------------------------------

def test_set_ip_updates_value(settings):
    settings.setIp("192.168.1.2")
    assert settings.ip == "192.168.1.2"


def test_set_ip_emits_signal(settings):
    spy = QSignalSpy(settings.ipChanged)
    settings.setIp("10.0.0.1")
    assert len(spy) == 1


def test_set_ip_no_signal_if_unchanged(settings):
    settings.setIp("192.168.1.2")
    spy = QSignalSpy(settings.ipChanged)
    settings.setIp("192.168.1.2")  # same value
    assert len(spy) == 0


def test_set_single_array_updates_value(settings):
    settings.setSingleArray(True)
    assert settings.singleArray is True


def test_set_single_array_emits_signal(settings):
    spy = QSignalSpy(settings.singleArrayChanged)
    settings.setSingleArray(True)
    assert len(spy) == 1


def test_set_single_array_no_signal_if_unchanged(settings):
    settings.setSingleArray(False)
    spy = QSignalSpy(settings.singleArrayChanged)
    settings.setSingleArray(False)
    assert len(spy) == 0


# ---------------------------------------------------------------------------
# Tests — persistence
# ---------------------------------------------------------------------------

def test_settings_persisted_to_json(qapp, tmp_path):
    settings_file = tmp_path / "settings.json"
    s = CommonSettings(settings_path=settings_file)
    s.setIp("192.168.1.99")
    s.setSingleArray(True)

    data = json.loads(settings_file.read_text())
    assert data["ip"] == "192.168.1.99"
    assert data["single_array"] is True


def test_settings_loaded_on_startup(qapp, tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"ip": "10.0.0.5", "single_array": True}))

    s = CommonSettings(settings_path=settings_file)
    assert s.ip == "10.0.0.5"
    assert s.singleArray is True


def test_missing_settings_file_uses_defaults(qapp, tmp_path):
    settings_file = tmp_path / "nonexistent.json"
    s = CommonSettings(settings_path=settings_file)
    assert s.ip == ""
    assert s.singleArray is False


def test_corrupt_settings_file_uses_defaults(qapp, tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("this is not json {{{")
    s = CommonSettings(settings_path=settings_file)
    assert s.ip == ""
    assert s.singleArray is False
