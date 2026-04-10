"""Hardware test suite — requires real ESPARGOS board and cameras connected.

Run with:
    ./run-tests-hardware.sh <espargos-ip>
    ./run-tests-hardware.sh <espargos-ip> --camera-backend picamera2

Or directly:
    QT_QPA_PLATFORM=offscreen pytest -m hardware \\
        --espargos-ip 192.168.x.x demos/demos-menu/tests/hardware/

Tests are skipped (not failed) if --espargos-ip is omitted or the board is
unreachable, so running the full suite without hardware still exits 0.
"""
import os
import queue
import subprocess
import threading
import time

import pytest


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--espargos-ip",
        default=None,
        help="IP address of the connected ESPARGOS board",
    )
    parser.addoption(
        "--camera-backend",
        default="auto",
        choices=["qt", "picamera2", "auto"],
        help="Camera backend(s) to exercise in camera tests (default: auto = both)",
    )


# ---------------------------------------------------------------------------
# Session-scoped hardware fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def espargos_ip(request):
    """IP of the connected ESPARGOS board.  Skips the test if not supplied."""
    ip = request.config.getoption("--espargos-ip")
    if not ip:
        pytest.skip("--espargos-ip not provided; skipping hardware test")
    return ip


@pytest.fixture(scope="session")
def camera_backend(request):
    return request.config.getoption("--camera-backend")


@pytest.fixture(scope="session")
def espargos_board(espargos_ip):
    """Connected espargos.Board.  Skips if the board is unreachable."""
    import espargos
    try:
        board = espargos.Board(espargos_ip)
    except Exception as exc:
        pytest.skip(f"Cannot connect to ESPARGOS at {espargos_ip}: {exc}")
    return board


@pytest.fixture(scope="session")
def calibrated_pool(espargos_board):
    """Pool that has completed one calibration pass.

    Session-scoped so calibration runs only once per pytest invocation.
    """
    import espargos
    pool = espargos.Pool([espargos_board])
    pool.start()
    try:
        pool.calibrate(per_board=True, duration=3)
    except Exception as exc:
        pool.stop()
        pytest.skip(f"Calibration failed: {exc}")
    yield pool
    pool.stop()


# ---------------------------------------------------------------------------
# Demo-process helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def spawn_demo():
    """Fixture that provides a callable for launching demo processes.

    Usage::

        def test_foo(spawn_demo, espargos_ip):
            lines, found = spawn_demo(
                cmd=["python", "speedtest.py", espargos_ip],
                demo_dir=DEMOS_ROOT / "speedtest",
                pattern="calibration clusters",
                timeout=30,
            )
            assert found, f"Pattern not found in output:\\n" + "\\n".join(lines)

    All spawned processes are terminated automatically when the test ends.
    """
    _procs = []

    def _spawn(cmd, demo_dir, pattern=None, timeout=30, env_extras=None):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        if env_extras:
            env.update(env_extras)

        proc = subprocess.Popen(
            cmd,
            cwd=str(demo_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        _procs.append(proc)

        output_lines = []
        found = False
        q = queue.Queue()

        def _reader(stream, q):
            for line in iter(stream.readline, ""):
                q.put(line)
            q.put(None)

        t = threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True)
        t.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = q.get(timeout=0.25)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            output_lines.append(line.rstrip())
            if pattern and pattern.lower() in line.lower():
                found = True
                break

        return output_lines, found

    yield _spawn

    for proc in _procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
