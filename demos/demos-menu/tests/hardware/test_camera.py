"""Hardware tests — camera enumeration and frame delivery.

Three levels of camera testing:

1. Enumeration (no ESPARGOS needed):
   - Qt/V4L2: QMediaDevices.videoInputs() lists the Logitech C920
   - Picamera2: Picamera2.global_camera_info() lists the IMX477 (HQ Camera)
   - --list-cameras CLI: camera.py reports both devices

2. Demo launch with real ESPARGOS + camera:
   - camera.py --camera-backend qt     -s <ip> connects and starts backlog
   - camera.py --camera-backend picamera2 -s <ip> enumerates IMX477, starts backlog

3. Frame delivery (VideoCamera API directly):
   - VideoCamera (Qt backend) delivers frames to QVideoSink from Logitech C920
   - Picamera2VideoCamera delivers frames to QVideoSink from HQ Camera Module

NOTE: These tests require a real display (not offscreen) for Qt media device
enumeration and frame delivery. Run with run-tests-hardware.sh which does NOT
set QT_QPA_PLATFORM=offscreen.
"""
import os
import pathlib
import sys
import pytest
from PyQt6.QtMultimedia import QMediaCaptureSession, QVideoSink

DEMOS_ROOT = pathlib.Path(__file__).parents[3]
CAMERA_DIR = DEMOS_ROOT / "camera"

_BACKLOG_PATTERN = "started csi backlog thread"
_IMX477_PATTERN = "imx477"


def _add_videocamera_path():
    """Add demos/camera/ to sys.path so VideoCamera can be imported."""
    camera_path = str(CAMERA_DIR)
    if camera_path not in sys.path:
        sys.path.insert(0, camera_path)


# ---------------------------------------------------------------------------
# Camera enumeration — no ESPARGOS needed
# ---------------------------------------------------------------------------

@pytest.mark.hardware
def test_qt_enumerates_usb_camera(qapp):
    """QMediaDevices.videoInputs() finds at least one V4L2 device (Logitech C920).

    Requires a live display session (Wayland or X11) — Qt multimedia will not
    enumerate cameras over a bare SSH connection with no DISPLAY/WAYLAND_DISPLAY.
    Run from the touchscreen session or use a forwarded display.
    """
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip(
            "No display session (DISPLAY/WAYLAND_DISPLAY not set); "
            "Qt camera enumeration requires a live Wayland or X11 session"
        )
    from PyQt6.QtMultimedia import QMediaDevices
    devices = QMediaDevices.videoInputs()
    assert len(devices) > 0, (
        "No Qt video input devices found — is the Logitech C920 connected via USB?"
    )
    descriptions = [d.description() for d in devices]
    assert any("c920" in d.lower() or "webcam" in d.lower() or "logitech" in d.lower()
               for d in descriptions), (
        f"Logitech C920 not found in Qt device list: {descriptions}"
    )


@pytest.mark.hardware
def test_picamera2_enumerates_hq_camera():
    """Picamera2.global_camera_info() finds the IMX477 (HQ Camera Module)."""
    try:
        from picamera2 import Picamera2
    except ImportError:
        pytest.skip("picamera2 not installed (needs --system-site-packages venv)")

    cameras = Picamera2.global_camera_info()
    assert len(cameras) > 0, "No cameras found by Picamera2 — is the HQ Camera connected?"
    assert any(_IMX477_PATTERN in str(cam).lower() for cam in cameras), (
        f"IMX477 (HQ Camera) not found in Picamera2 device list: {cameras}"
    )


@pytest.mark.hardware
def test_list_cameras_reports_both(qapp, spawn_demo):
    """camera.py --list-cameras reports at least one Qt and one Picamera2 device."""
    lines, _ = spawn_demo(
        cmd=["python", "camera.py", "--list-cameras"],
        demo_dir=CAMERA_DIR,
        pattern=None,
        timeout=10,
    )
    output = "\n".join(lines).lower()
    if "unrecognized arguments: --list-cameras" in output:
        pytest.skip("camera.py --list-cameras not implemented in this checkout")
    assert "qt" in output or "v4l2" in output or "webcam" in output or "c920" in output, (
        f"No Qt/V4L2 camera listed:\n{output}"
    )
    assert "picamera2" in output or _IMX477_PATTERN in output, (
        f"No Picamera2/IMX477 camera listed:\n{output}"
    )


# ---------------------------------------------------------------------------
# Demo launch with ESPARGOS + camera
# ---------------------------------------------------------------------------

@pytest.mark.hardware
def test_camera_demo_qt_backend_connects(espargos_ip, camera_backend, spawn_demo):
    """camera.py --camera-backend qt connects to ESPARGOS and starts backlog."""
    if camera_backend == "picamera2":
        pytest.skip("--camera-backend=picamera2 selected; skipping Qt camera test")

    lines, found = spawn_demo(
        cmd=["python", "camera.py", "--camera-backend", "qt", "-s", espargos_ip],
        demo_dir=CAMERA_DIR,
        pattern=_BACKLOG_PATTERN,
        timeout=45,
    )
    assert found, (
        f"'{_BACKLOG_PATTERN}' not found in camera (Qt) output within 45s:\n"
        + "\n".join(lines)
    )


@pytest.mark.hardware
def test_camera_demo_picamera2_backend_connects(espargos_ip, camera_backend, spawn_demo):
    """camera.py --camera-backend picamera2 enumerates IMX477 and starts backlog."""
    if camera_backend == "qt":
        pytest.skip("--camera-backend=qt selected; skipping Picamera2 camera test")

    try:
        import picamera2  # noqa: F401
    except ImportError:
        pytest.skip("picamera2 not installed")

    lines, found = spawn_demo(
        cmd=["python", "camera.py", "--camera-backend", "picamera2", "-s", espargos_ip],
        demo_dir=CAMERA_DIR,
        pattern=_BACKLOG_PATTERN,
        timeout=60,
    )
    output = "\n".join(lines)
    assert _IMX477_PATTERN in output.lower(), (
        f"IMX477 not mentioned in Picamera2 camera output:\n{output}"
    )
    assert found, (
        f"'{_BACKLOG_PATTERN}' not found in camera (Picamera2) output within 60s:\n{output}"
    )


# ---------------------------------------------------------------------------
# Frame delivery — VideoCamera API directly
# ---------------------------------------------------------------------------

@pytest.mark.hardware
def test_qt_camera_delivers_frame(qapp, qtbot):
    """VideoCamera (Qt backend) delivers at least one frame to QVideoSink within 5s."""
    from PyQt6.QtMultimedia import QMediaDevices
    if QMediaDevices.defaultVideoInput().isNull():
        pytest.skip(
            "No default Qt video device — Logitech C920 not connected or "
            "no display session (DISPLAY/WAYLAND_DISPLAY not set)"
        )

    _add_videocamera_path()
    from videocamera import VideoCamera  # noqa: E402

    camera = VideoCamera()
    session = QMediaCaptureSession()
    session.setCamera(camera)
    sink = QVideoSink()
    session.setVideoSink(sink)

    camera.start()
    try:
        qtbot.waitSignal(sink.videoFrameChanged, timeout=5000, raising=True)
    finally:
        camera.stop()


@pytest.mark.hardware
def test_picamera2_camera_delivers_frame(qapp, qtbot):
    """Picamera2VideoCamera delivers at least one frame to QVideoSink within 5s."""
    try:
        import picamera2  # noqa: F401
    except ImportError:
        pytest.skip("picamera2 not installed")

    _add_videocamera_path()
    try:
        from videocamera import Picamera2VideoCamera  # noqa: E402
    except ImportError:
        pytest.skip("Picamera2VideoCamera not available in this checkout")

    try:
        camera = Picamera2VideoCamera()
    except RuntimeError as exc:
        pytest.skip(f"Picamera2VideoCamera could not be created: {exc}")

    sink = QVideoSink()
    camera.setVideoSink(sink)

    camera.start()
    try:
        qtbot.waitSignal(sink.videoFrameChanged, timeout=5000, raising=True)
    finally:
        camera.stop()
