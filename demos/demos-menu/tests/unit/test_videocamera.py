"""Unit tests for demos/camera/videocamera.py helpers and CombinedVideoCamera routing.

No ESPARGOS board or camera hardware is required.

Coverage:
  - _qt_device_is_pi_managed()  — deduplication predicate
  - _pi_model_names()           — Picamera2 model name extractor
  - list_all_cameras()          — unified camera list, no duplicate CSI cameras
  - DummyVideoCamera            — isQtBackend / isPicamera2Backend / activeQCamera stubs
  - CombinedVideoCamera         — device-string split, setDevice routing, backendChanged signal
"""
import pathlib
import sys
import pytest
import PyQt6.QtCore
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtMultimedia import QCamera
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure demos/camera/ is importable (mirrors the hardware test setup)
# ---------------------------------------------------------------------------
_CAMERA_DIR = pathlib.Path(__file__).parents[3] / "camera"
if str(_CAMERA_DIR) not in sys.path:
    sys.path.insert(0, str(_CAMERA_DIR))

import videocamera  # noqa: E402


# ---------------------------------------------------------------------------
# Fake camera classes
#
# These replace VideoCamera and Picamera2VideoCamera when testing
# CombinedVideoCamera routing.  They extend QCamera (same base as the real
# classes) so that isinstance() checks inside CombinedVideoCamera work
# correctly once VideoCamera / Picamera2VideoCamera are patched in the module.
# ---------------------------------------------------------------------------

class _FakeVideoCamera(QCamera):
    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._device = args[0] if args else ""

    def setDevice(self, s):
        self._device = s

    def setFormat(self, f):
        pass

    def setFocusMode(self, m):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def getDevice(self):
        return self._device

    def getFormat(self):
        return "fake-qt-format"

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableFormats(self):
        return ["1920x1080 @ 30.00 FPS"]


class _FakePicamera2VideoCamera(QCamera):
    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._device = args[0] if args else ""
        self._sink = None

    def setDevice(self, s):
        self._device = s

    def setFormat(self, f):
        pass

    def setFocusMode(self, m):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def setVideoSink(self, sink):
        self._sink = sink

    def getDevice(self):
        return self._device

    def getFormat(self):
        return "fake-pi-format"

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableFormats(self):
        return ["4056x3040 @ 10.00 FPS"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_qt_device(description: str, device_id: str = "/dev/video0") -> MagicMock:
    """Return a mock QCameraDevice with description() and id() configured."""
    d = MagicMock()
    d.description.return_value = description
    d.id.return_value = device_id.encode()
    return d


def _device_str(device_id: str, description: str) -> str:
    """Build the device string that CombinedVideoCamera stores internally."""
    return f"{device_id}: {description}"


# ---------------------------------------------------------------------------
# _qt_device_is_pi_managed
# ---------------------------------------------------------------------------

class TestQtDeviceIsPiManaged:

    def test_empty_pi_models_never_matches(self):
        device = _make_qt_device("HD Pro Webcam C920")
        assert not videocamera._qt_device_is_pi_managed(device, set())

    def test_exact_model_name_matches(self):
        device = _make_qt_device("imx477")
        assert videocamera._qt_device_is_pi_managed(device, {"imx477"})

    def test_case_insensitive(self):
        device = _make_qt_device("IMX477 Sensor Node")
        assert videocamera._qt_device_is_pi_managed(device, {"imx477"})

    def test_substring_in_longer_description(self):
        device = _make_qt_device("rp1-cfe imx477 capture")
        assert videocamera._qt_device_is_pi_managed(device, {"imx477"})

    def test_usb_camera_does_not_match(self):
        device = _make_qt_device("HD Pro Webcam C920")
        assert not videocamera._qt_device_is_pi_managed(device, {"imx477"})

    def test_matches_any_of_multiple_models(self):
        device = _make_qt_device("imx219 capture node")
        assert videocamera._qt_device_is_pi_managed(device, {"imx477", "imx219"})

    def test_no_match_among_multiple_models(self):
        device = _make_qt_device("HD Pro Webcam C920")
        assert not videocamera._qt_device_is_pi_managed(device, {"imx477", "imx219", "ov5647"})


# ---------------------------------------------------------------------------
# _pi_model_names
# ---------------------------------------------------------------------------

class TestPiModelNames:

    def test_returns_empty_set_when_picamera2_unavailable(self):
        with patch("videocamera.PICAMERA2_AVAILABLE", False):
            assert videocamera._pi_model_names() == set()

    def test_returns_lowercase_model_names(self):
        cam_info = [{"Model": "IMX477", "Num": 0}, {"Model": "imx219", "Num": 1}]
        with patch("videocamera.PICAMERA2_AVAILABLE", True), \
             patch.object(videocamera.Picamera2, "global_camera_info", return_value=cam_info):
            assert videocamera._pi_model_names() == {"imx477", "imx219"}

    def test_skips_entries_without_model_key(self):
        cam_info = [{"Num": 0}]
        with patch("videocamera.PICAMERA2_AVAILABLE", True), \
             patch.object(videocamera.Picamera2, "global_camera_info", return_value=cam_info):
            assert videocamera._pi_model_names() == set()

    def test_skips_entries_with_empty_model(self):
        cam_info = [{"Model": "", "Num": 0}]
        with patch("videocamera.PICAMERA2_AVAILABLE", True), \
             patch.object(videocamera.Picamera2, "global_camera_info", return_value=cam_info):
            assert videocamera._pi_model_names() == set()

    def test_returns_empty_set_on_exception(self):
        with patch("videocamera.PICAMERA2_AVAILABLE", True), \
             patch.object(videocamera.Picamera2, "global_camera_info",
                          side_effect=RuntimeError("camera not accessible")):
            assert videocamera._pi_model_names() == set()


# ---------------------------------------------------------------------------
# list_all_cameras
# ---------------------------------------------------------------------------

class TestListAllCameras:

    def _run(self, qt_devices, pi_info, pi_available=True):
        """Call list_all_cameras() with mocked Qt and Picamera2 device sources."""
        with patch("videocamera.QMediaDevices") as mock_qmd, \
             patch("videocamera.PICAMERA2_AVAILABLE", pi_available), \
             patch.object(videocamera.Picamera2, "global_camera_info", return_value=pi_info):
            mock_qmd.videoInputs.return_value = qt_devices
            return videocamera.list_all_cameras()

    def test_usb_only_camera_listed_as_qt(self):
        cameras = self._run(
            qt_devices=[_make_qt_device("HD Pro Webcam C920", "/dev/video2")],
            pi_info=[],
        )
        assert len(cameras) == 1
        assert cameras[0]["backend"] == "qt"
        assert cameras[0]["name"] == "HD Pro Webcam C920"
        assert cameras[0]["id"] == "/dev/video2"

    def test_csi_camera_appears_only_as_picamera2(self):
        """imx477 in both Qt and Pi lists → only one picamera2 entry."""
        cameras = self._run(
            qt_devices=[_make_qt_device("imx477", "/dev/video0")],
            pi_info=[{"Model": "imx477", "Num": 0}],
        )
        assert len(cameras) == 1
        assert cameras[0]["backend"] == "picamera2"
        assert cameras[0]["name"] == "imx477"
        assert cameras[0]["id"] == "0"

    def test_usb_and_csi_no_duplicates(self):
        """C920 (USB, Qt only) + imx477 (CSI, both lists) → exactly two entries."""
        cameras = self._run(
            qt_devices=[
                _make_qt_device("HD Pro Webcam C920", "/dev/video2"),
                _make_qt_device("imx477", "/dev/video0"),   # filtered out
            ],
            pi_info=[{"Model": "imx477", "Num": 0}],
        )
        assert len(cameras) == 2
        backends = [c["backend"] for c in cameras]
        assert backends.count("qt") == 1
        assert backends.count("picamera2") == 1
        names = [c["name"] for c in cameras]
        assert names.count("imx477") == 1          # not duplicated

    def test_indices_are_sequential_from_zero(self):
        cameras = self._run(
            qt_devices=[_make_qt_device("C920", "/dev/video2")],
            pi_info=[{"Model": "imx477", "Num": 0}],
        )
        assert [c["index"] for c in cameras] == [0, 1]

    def test_indices_sequential_after_csi_filter(self):
        """After filtering the CSI Qt entry, indices must still be contiguous."""
        cameras = self._run(
            qt_devices=[
                _make_qt_device("HD Pro Webcam C920", "/dev/video2"),
                _make_qt_device("imx477", "/dev/video0"),   # filtered
            ],
            pi_info=[{"Model": "imx477", "Num": 0}],
        )
        assert [c["index"] for c in cameras] == [0, 1]

    def test_picamera2_unavailable_lists_only_qt(self):
        cameras = self._run(
            qt_devices=[_make_qt_device("C920", "/dev/video2")],
            pi_info=[],
            pi_available=False,
        )
        assert len(cameras) == 1
        assert cameras[0]["backend"] == "qt"

    def test_empty_when_no_cameras_at_all(self):
        cameras = self._run(qt_devices=[], pi_info=[], pi_available=False)
        assert cameras == []

    def test_multiple_pi_cameras_all_listed(self):
        cameras = self._run(
            qt_devices=[],
            pi_info=[{"Model": "imx477", "Num": 0}, {"Model": "imx219", "Num": 1}],
        )
        assert len(cameras) == 2
        assert all(c["backend"] == "picamera2" for c in cameras)
        ids = [c["id"] for c in cameras]
        assert "0" in ids and "1" in ids


# ---------------------------------------------------------------------------
# DummyVideoCamera — backend-type stubs
# ---------------------------------------------------------------------------

class TestDummyVideoCamera:

    def test_is_not_qt_backend(self, qapp):
        d = videocamera.DummyVideoCamera()
        assert d.isQtBackend is False

    def test_is_not_picamera2_backend(self, qapp):
        d = videocamera.DummyVideoCamera()
        assert d.isPicamera2Backend is False

    def test_active_q_camera_is_none(self, qapp):
        d = videocamera.DummyVideoCamera()
        assert d.activeQCamera is None

    def test_available_devices_stub(self, qapp):
        d = videocamera.DummyVideoCamera()
        assert d.availableDevices == ["No camera available"]

    def test_available_formats_stub(self, qapp):
        d = videocamera.DummyVideoCamera()
        assert d.availableFormats == ["No format available"]

    def test_set_device_is_silent(self, qapp):
        d = videocamera.DummyVideoCamera()
        d.setDevice("anything")   # must not raise

    def test_set_format_is_silent(self, qapp):
        d = videocamera.DummyVideoCamera()
        d.setFormat("anything")   # must not raise


# ---------------------------------------------------------------------------
# CombinedVideoCamera — device-string split and routing
# ---------------------------------------------------------------------------

@pytest.fixture
def combined_env(qapp):
    """Patch all external dependencies so CombinedVideoCamera can be constructed
    without real hardware, and yield helpers for constructing it."""
    qt_dev_c920 = _make_qt_device("HD Pro Webcam C920", "/dev/video2")
    qt_dev_csi  = _make_qt_device("imx477", "/dev/video0")   # duplicate of Pi camera
    pi_info     = [{"Model": "imx477", "Num": 0}]

    with patch("videocamera.QMediaDevices") as mock_qmd, \
         patch("videocamera.PICAMERA2_AVAILABLE", True), \
         patch.object(videocamera.Picamera2, "global_camera_info", return_value=pi_info), \
         patch("videocamera.VideoCamera", _FakeVideoCamera), \
         patch("videocamera.Picamera2VideoCamera", _FakePicamera2VideoCamera):
        mock_qmd.videoInputs.return_value = [qt_dev_c920, qt_dev_csi]
        yield {
            "qt_dev_str": _device_str("/dev/video2", "HD Pro Webcam C920"),
            "pi_dev_str": "0: imx477",
        }


class TestCombinedVideoCameraDeviceStrings:
    """Verify that the internal device lists are correctly split and deduplicated."""

    def test_qt_device_strings_excludes_csi_camera(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert combined_env["qt_dev_str"] in cam._qt_device_strings
        assert combined_env["pi_dev_str"] not in cam._qt_device_strings

    def test_qt_device_strings_has_no_imx477(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert not any("imx477" in s for s in cam._qt_device_strings)

    def test_pi_device_strings_contains_csi_camera(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert combined_env["pi_dev_str"] in cam._pi_device_strings

    def test_available_devices_is_union(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert combined_env["qt_dev_str"] in cam.availableDevices
        assert combined_env["pi_dev_str"] in cam.availableDevices

    def test_no_duplicate_in_available_devices(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert len(cam.availableDevices) == len(set(cam.availableDevices))
        # specifically: imx477 appears exactly once
        assert sum(1 for s in cam.availableDevices if "imx477" in s) == 1

    def test_set_device_unknown_string_raises(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        with pytest.raises(ValueError, match="No camera device matching"):
            cam.setDevice("nonexistent-device")


class TestCombinedVideoCameraBackendRouting:
    """Verify isQtBackend / isPicamera2Backend / activeQCamera after setDevice,
    and that backendChanged fires exactly when the backend type changes."""

    def test_initial_qt_backend_active(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert cam.isQtBackend
        assert not cam.isPicamera2Backend
        assert cam.activeQCamera is not None

    def test_initial_pi_backend_active(self, combined_env):
        cam = videocamera.CombinedVideoCamera("picamera2")
        assert cam.isPicamera2Backend
        assert not cam.isQtBackend
        assert cam.activeQCamera is None

    def test_switch_qt_to_pi_emits_backend_changed(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        spy = QSignalSpy(cam.backendChanged)

        cam.setDevice(combined_env["pi_dev_str"])

        assert len(spy) == 1
        assert cam.isPicamera2Backend
        assert not cam.isQtBackend
        assert cam.activeQCamera is None

    def test_switch_pi_to_qt_emits_backend_changed(self, combined_env):
        cam = videocamera.CombinedVideoCamera("picamera2")
        spy = QSignalSpy(cam.backendChanged)

        cam.setDevice(combined_env["qt_dev_str"])

        assert len(spy) == 1
        assert cam.isQtBackend
        assert not cam.isPicamera2Backend
        assert cam.activeQCamera is not None

    def test_same_backend_setdevice_does_not_emit_backend_changed(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        spy = QSignalSpy(cam.backendChanged)

        # setDevice to same Qt device — same backend
        cam.setDevice(combined_env["qt_dev_str"])

        assert len(spy) == 0

    def test_round_trip_qt_pi_qt_emits_twice(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        spy = QSignalSpy(cam.backendChanged)

        cam.setDevice(combined_env["pi_dev_str"])   # Qt → Pi
        cam.setDevice(combined_env["qt_dev_str"])   # Pi → Qt

        assert len(spy) == 2

    def test_active_q_camera_is_same_object_after_round_trip(self, combined_env):
        """After Qt → Pi → Qt, activeQCamera is the same VideoCamera instance."""
        cam = videocamera.CombinedVideoCamera("qt")
        first_qt_cam = cam.activeQCamera

        cam.setDevice(combined_env["pi_dev_str"])
        cam.setDevice(combined_env["qt_dev_str"])

        assert cam.activeQCamera is first_qt_cam

    def test_set_video_sink_forwarded_to_pi_camera(self, combined_env):
        """setVideoSink() is forwarded to the Picamera2 camera when Pi backend is active."""
        cam = videocamera.CombinedVideoCamera("picamera2")
        from PyQt6.QtMultimedia import QVideoSink
        sink = QVideoSink()
        cam.setVideoSink(sink)
        assert cam._pi_cam._sink is sink

    def test_get_device_reflects_current_backend(self, combined_env):
        cam = videocamera.CombinedVideoCamera("qt")
        assert combined_env["qt_dev_str"] in cam.getDevice() or cam.getDevice() != ""

        cam.setDevice(combined_env["pi_dev_str"])
        assert cam.getDevice() == combined_env["pi_dev_str"]
