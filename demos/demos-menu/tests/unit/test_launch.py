"""Unit tests for demo launch via QProcess — mocked, no real processes."""
import pathlib
import sys
import pytest
from unittest.mock import patch, MagicMock, call

from demos_menu import CommonSettings, DemoScanner, ScannerAdapter, build_command


DEMOS_ROOT = pathlib.Path(__file__).parents[3]


# ---------------------------------------------------------------------------
# build_command: pure function, no Qt needed
# ---------------------------------------------------------------------------

def test_single_array_placeholder_substituted():
    cmd = build_command("python speedtest.py {single_array}", ip="192.168.1.2", single_array=True)
    assert cmd == [sys.executable, "speedtest.py", "-s", "192.168.1.2"]


def test_single_array_empty_when_not_single_mode():
    cmd = build_command("python combined-array.py {single_array}", ip="192.168.1.2", single_array=False)
    assert cmd == [sys.executable, "combined-array.py"]


def test_empty_ip_gives_empty_single_array_token():
    cmd = build_command("python speedtest.py {single_array}", ip="", single_array=True)
    assert cmd == [sys.executable, "speedtest.py"]


def test_no_placeholder_command_unchanged():
    cmd = build_command("python combined-array.py", ip="192.168.1.2", single_array=False)
    assert cmd == [sys.executable, "combined-array.py"]


def test_ip_placeholder_substituted():
    cmd = build_command("python demo.py --host {ip}", ip="10.0.0.5", single_array=False)
    assert cmd == [sys.executable, "demo.py", "--host", "10.0.0.5"]


def test_build_command_uses_sys_executable():
    """bare python/python3 must be replaced with the running interpreter."""
    cmd_py = build_command("python foo.py", ip="", single_array=False)
    cmd_py3 = build_command("python3 foo.py", ip="", single_array=False)
    assert cmd_py[0] == sys.executable
    assert cmd_py3[0] == sys.executable


def test_build_command_non_python_binary_unchanged():
    cmd = build_command("/usr/bin/node server.js", ip="", single_array=False)
    assert cmd[0] == "/usr/bin/node"


def test_build_command_fullscreen_appends_kiosk_option():
    cmd = build_command("python demo.py {single_array}", ip="192.168.1.2",
                        single_array=False, fullscreen=True)
    assert "-o" in cmd
    assert "generic.kiosk_mode=True" in cmd


def test_build_command_no_fullscreen_omits_kiosk_option():
    cmd = build_command("python demo.py {single_array}", ip="192.168.1.2",
                        single_array=False, fullscreen=False)
    assert "generic.kiosk_mode=True" not in cmd


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


def test_launch_demo_fullscreen_appends_kiosk_option(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    item = adapter.demoItems[0]
    expected_cmd = build_command(item["command"], ip="192.168.1.2", single_array=True, fullscreen=True)

    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        adapter.launchDemo(0, "192.168.1.2", True, fullscreen=True)
        mock_proc.start.assert_called_once_with(expected_cmd[0], expected_cmd[1:])
        # Confirm kiosk flag present
        all_args = [expected_cmd[0]] + expected_cmd[1:]
        assert "generic.kiosk_mode=True" in all_args


def test_launch_demo_invalid_index_does_not_crash(qapp, tmp_path):
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess"):
        adapter.launchDemo(999, "192.168.1.2", True)  # should log warning, not raise


# ---------------------------------------------------------------------------
# QProcess lifetime — Bug 1 regression tests
# ---------------------------------------------------------------------------

def test_launch_demo_process_kept_in_procs(qapp, tmp_path):
    """QProcess must remain in _procs after launchDemo returns (prevents GC kill)."""
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc
        adapter.launchDemo(0, "192.168.1.2", True)
        assert mock_proc in adapter._procs


def test_launch_demo_proc_removed_on_finished(qapp, tmp_path):
    """Calling the finished-cleanup lambda removes the proc from _procs."""
    settings = CommonSettings(settings_path=tmp_path / "s.json")
    adapter = ScannerAdapter(DemoScanner(DEMOS_ROOT), settings)
    with patch("demos_menu.QProcess") as MockQProcess:
        mock_proc = MagicMock()
        MockQProcess.return_value = mock_proc

        # Capture the cleanup lambda registered with proc.finished.connect
        cleanup_lambda = None
        def capture_connect(fn):
            nonlocal cleanup_lambda
            cleanup_lambda = fn
        mock_proc.finished.connect.side_effect = capture_connect

        adapter.launchDemo(0, "192.168.1.2", True)
        assert mock_proc in adapter._procs

        # Fire the cleanup lambda (simulates QProcess finished signal)
        if cleanup_lambda is not None:
            cleanup_lambda()
        assert mock_proc not in adapter._procs
