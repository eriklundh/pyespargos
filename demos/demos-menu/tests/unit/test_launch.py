"""Unit tests for demo launch via QProcess — mocked, no real processes."""
import pathlib
import pytest
from unittest.mock import patch, MagicMock, call

from demos_menu import CommonSettings, DemoScanner, ScannerAdapter, build_command


DEMOS_ROOT = pathlib.Path(__file__).parents[3]


# ---------------------------------------------------------------------------
# build_command: pure function, no Qt needed
# ---------------------------------------------------------------------------

def test_single_array_placeholder_substituted():
    cmd = build_command("python speedtest.py {single_array}", ip="192.168.1.2", single_array=True)
    assert cmd == ["python", "speedtest.py", "-s", "192.168.1.2"]


def test_single_array_empty_when_not_single_mode():
    cmd = build_command("python combined-array.py {single_array}", ip="192.168.1.2", single_array=False)
    assert cmd == ["python", "combined-array.py"]


def test_empty_ip_gives_empty_single_array_token():
    cmd = build_command("python speedtest.py {single_array}", ip="", single_array=True)
    assert cmd == ["python", "speedtest.py"]


def test_no_placeholder_command_unchanged():
    cmd = build_command("python combined-array.py", ip="192.168.1.2", single_array=False)
    assert cmd == ["python", "combined-array.py"]


def test_ip_placeholder_substituted():
    cmd = build_command("python demo.py --host {ip}", ip="10.0.0.5", single_array=False)
    assert cmd == ["python", "demo.py", "--host", "10.0.0.5"]


# ---------------------------------------------------------------------------
# ScannerAdapter.launchDemo — QProcess is mocked
# ---------------------------------------------------------------------------

def test_launch_demo_calls_qprocess_start(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        adapter.launchDemo(0, "192.168.1.2", True)
        assert mock_proc.start.called


def test_launch_demo_sets_working_directory(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        adapter.launchDemo(0, "192.168.1.2", True)
        mock_proc.setWorkingDirectory.assert_called_once_with(
            adapter.demoItems[0]["demo_dir"]
        )


def test_launch_demo_passes_correct_command(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    item = adapter.demoItems[0]
    expected_cmd = build_command(item["command"], ip="192.168.1.2", single_array=True)

    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        adapter.launchDemo(0, "192.168.1.2", True)
        mock_proc.start.assert_called_once_with(expected_cmd[0], expected_cmd[1:])


def test_launch_demo_invalid_index_does_not_crash(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess"):
        adapter.launchDemo(999, "192.168.1.2", True)  # should log warning, not raise
