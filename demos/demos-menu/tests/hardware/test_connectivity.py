"""Hardware tests — ESPARGOS board connectivity and calibration.

Verifies:
  - Board HTTP identify succeeds (espargos.Board() completes)
  - Board exposes expected hardware attributes
  - Pool starts and stops cleanly
  - pool.calibrate() completes and produces a non-None calibration object
  - No NaN values in calibration data (proper cluster reception)
"""
import pytest
import espargos


@pytest.mark.hardware
def test_board_http_identify(espargos_ip):
    """espargos.Board() connects synchronously; raises if board unreachable."""
    board = espargos.Board(espargos_ip)
    assert board.host == espargos_ip


@pytest.mark.hardware
def test_board_has_revision(espargos_board):
    """Board exposes an integer hardware revision after connect."""
    assert espargos_board.revision is not None
    assert isinstance(espargos_board.revision, int)


@pytest.mark.hardware
def test_board_has_api_version(espargos_board):
    """Board exposes a non-empty API version string."""
    assert espargos_board.api_version


@pytest.mark.hardware
def test_pool_start_stop(espargos_ip):
    """Pool starts and stops without error."""
    board = espargos.Board(espargos_ip)
    pool = espargos.Pool([board])
    pool.start()
    pool.stop()


@pytest.mark.hardware
def test_calibration_completes(espargos_ip):
    """pool.calibrate() returns without raising — at least 5 clusters received."""
    board = espargos.Board(espargos_ip)
    pool = espargos.Pool([board])
    pool.start()
    try:
        pool.calibrate(per_board=True, duration=3)
        cal = pool.get_calibration()
        assert cal is not None, "Calibration returned None after calibrate()"
    finally:
        pool.stop()


@pytest.mark.hardware
def test_calibration_no_nan(calibrated_pool):
    """Calibration data contains no NaN values (sufficient clusters received)."""
    import numpy as np
    cal = calibrated_pool.get_calibration()
    assert cal is not None
    # Check HT40 calibration values — the primary format used by demos
    if hasattr(cal, "calibration_values_ht40"):
        assert not np.any(np.isnan(cal.calibration_values_ht40)), (
            "NaN in HT40 calibration — too few complete clusters received"
        )


@pytest.mark.hardware
def test_pool_shape(calibrated_pool):
    """Pool reports a valid antenna array shape after calibration."""
    shape = calibrated_pool.get_shape()
    assert shape is not None
    # Shape should be (n_boards * rows, cols) or similar — just check non-zero
    assert all(dim > 0 for dim in shape), f"Unexpected pool shape: {shape}"
