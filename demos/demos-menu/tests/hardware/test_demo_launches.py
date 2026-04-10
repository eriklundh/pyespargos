"""Hardware tests — demo process launch and ESPARGOS connection.

Each test spawns a real demo, waits for evidence of successful board
connection and calibration in the process output, then terminates it.

Two demo families are tested:
  - ESPARGOSApplication (positional hosts arg):  speedtest.py
  - CombinedArrayMixin  (-s/--single-array flag): azimuth-delay.py, camera.py

Tests pass when the expected output pattern appears within the timeout.
Tests are automatically skipped if --espargos-ip is not provided.
"""
import pathlib
import pytest

DEMOS_ROOT = pathlib.Path(__file__).parents[3]

# Pattern printed by espargos/pool.py _clusters_to_calibration()
_CALIB_PATTERN = "calibration clusters"

# Pattern printed by BacklogMixin when the CSI backlog thread starts
_BACKLOG_PATTERN = "started csi backlog thread"


@pytest.mark.hardware
def test_speedtest_connects_and_calibrates(espargos_ip, spawn_demo):
    """speedtest.py <ip> connects, calibrates, and keeps running.

    speedtest uses positional hosts (no CombinedArrayMixin), so the
    IP is passed directly as a positional argument.
    """
    lines, found = spawn_demo(
        cmd=["python", "speedtest.py", espargos_ip],
        demo_dir=DEMOS_ROOT / "speedtest",
        pattern=_CALIB_PATTERN,
        timeout=30,
    )
    assert found, (
        f"'{_CALIB_PATTERN}' not found in speedtest output within 30s:\n"
        + "\n".join(lines)
    )


@pytest.mark.hardware
def test_instantaneous_csi_connects(espargos_ip, spawn_demo):
    """instantaneous-csi.py <ip> connects and calibrates.

    Representative test for the non-CombinedArrayMixin single-board demos.
    """
    lines, found = spawn_demo(
        cmd=["python", "instantaneous-csi.py", espargos_ip],
        demo_dir=DEMOS_ROOT / "instantaneous-csi",
        pattern=_CALIB_PATTERN,
        timeout=30,
    )
    assert found, (
        f"'{_CALIB_PATTERN}' not found in instantaneous-csi output within 30s:\n"
        + "\n".join(lines)
    )


@pytest.mark.hardware
def test_azimuth_delay_connects_single_array(espargos_ip, spawn_demo):
    """azimuth-delay.py -s <ip> connects via CombinedArrayMixin -s flag."""
    lines, found = spawn_demo(
        cmd=["python", "azimuth-delay.py", "-s", espargos_ip],
        demo_dir=DEMOS_ROOT / "azimuth-delay",
        pattern=_CALIB_PATTERN,
        timeout=30,
    )
    assert found, (
        f"'{_CALIB_PATTERN}' not found in azimuth-delay output within 30s:\n"
        + "\n".join(lines)
    )


@pytest.mark.hardware
def test_azimuth_delay_backlog_starts(espargos_ip, spawn_demo):
    """azimuth-delay.py starts the CSI backlog thread after calibration."""
    lines, found = spawn_demo(
        cmd=["python", "azimuth-delay.py", "-s", espargos_ip],
        demo_dir=DEMOS_ROOT / "azimuth-delay",
        pattern=_BACKLOG_PATTERN,
        timeout=45,
    )
    assert found, (
        f"'{_BACKLOG_PATTERN}' not found in azimuth-delay output within 45s:\n"
        + "\n".join(lines)
    )


@pytest.mark.hardware
def test_wrong_ip_fails_fast(spawn_demo):
    """Demo with an unreachable IP exits with a connection error, not a hang."""
    lines, _ = spawn_demo(
        cmd=["python", "speedtest.py", "192.0.2.1"],   # TEST-NET — never routable
        demo_dir=DEMOS_ROOT / "speedtest",
        pattern="connection",
        timeout=15,
    )
    output = "\n".join(lines).lower()
    assert any(kw in output for kw in ("connection", "refused", "timeout", "error")), (
        f"Expected a connection error for unreachable IP, got:\n{output}"
    )
