import logging
import PyQt6.QtCore
from PyQt6.QtMultimedia import QMediaDevices, QCameraDevice, QCameraFormat, QCamera, QVideoSink, QVideoFrame
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImage

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False


def _detect_backend() -> str:
    """Return 'picamera2' if running on a Raspberry Pi with picamera2 available, else 'qt'."""
    try:
        model = open("/proc/device-tree/model", "r").read()
        if "Raspberry Pi" in model and PICAMERA2_AVAILABLE:
            return "picamera2"
    except OSError:
        pass
    return "qt"


def _pi_model_names() -> set[str]:
    """Return lowercase sensor model names for all cameras known to Picamera2.

    Used to filter Qt/V4L2 device list: on Raspberry Pi the same CSI camera
    appears in both QMediaDevices.videoInputs() (as a non-functional V4L2 node)
    and in Picamera2.global_camera_info().  We keep only the Picamera2 entry.
    """
    if not PICAMERA2_AVAILABLE:
        return set()
    try:
        return {info["Model"].lower() for info in Picamera2.global_camera_info() if info.get("Model")}
    except Exception:
        return set()


def _qt_device_is_pi_managed(device: QCameraDevice, pi_models: set[str]) -> bool:
    """Return True if this Qt/V4L2 device is the same physical camera as a Picamera2 device.

    On Raspberry Pi, CSI cameras (e.g. imx477) appear both as non-functional
    V4L2 capture nodes (enumerated by Qt) and as Picamera2 cameras.  Matching
    is done case-insensitively against the Qt device description.
    """
    if not pi_models:
        return False
    desc = device.description().lower()
    return any(model in desc for model in pi_models)


def list_all_cameras() -> list:
    """Return a flat list of dicts describing all cameras from both backends.

    CSI cameras that appear in both Qt's V4L2 list and Picamera2's list are
    included only once, under the picamera2 backend.

    Each dict has keys: index, backend, name, id.
    """
    cameras = []
    idx = 0
    pi_models = _pi_model_names()
    for device in QMediaDevices.videoInputs():
        if _qt_device_is_pi_managed(device, pi_models):
            continue  # skip: this CSI camera is listed under picamera2 below
        cameras.append({
            "index": idx,
            "backend": "qt",
            "name": device.description(),
            "id": bytes(device.id()).decode("utf-8"),
        })
        idx += 1
    if PICAMERA2_AVAILABLE:
        for info in Picamera2.global_camera_info():
            cameras.append({
                "index": idx,
                "backend": "picamera2",
                "name": info.get("Model", "Unknown"),
                "id": str(info.get("Num", "")),
            })
            idx += 1
    return cameras

log = logging.getLogger(__name__)


class VideoCamera(QCamera):
    "QCamera which exposes relevant properties for QML."

    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self, default_device: str | None = None, default_format: str | None = None):
        if default_device is not None:
            videoDevice = self._find_device(default_device)
        else:
            videoDevice = QMediaDevices.defaultVideoInput()

        super().__init__(videoDevice)

        if default_format is not None:
            fmt = self._find_format(default_format)
            self.setCameraFormat(fmt)
        else:
            availableFormats = videoDevice.videoFormats()
            if availableFormats:
                fmt = availableFormats[-1]
                self.setCameraFormat(fmt)
            else:
                log.warning("VideoCamera: no formats available for device '%s'",
                            videoDevice.description())

    def setDevice(self, device_str: str):
        device = self._find_device(device_str)
        was_active = self.isActive()
        if was_active:
            self.stop()
        self.setCameraDevice(device)
        # Apply the last format of the new device (V4L2 must be reconfigured)
        formats = device.videoFormats()
        if formats:
            self.setCameraFormat(formats[-1])
        else:
            logging.warning("VideoCamera.setDevice: no formats for '%s'", device.description())
        if was_active:
            self.start()
        # Notify that available formats may have changed
        self.availableFormatsChanged.emit()

    def setFormat(self, format_str: str):
        fmt = self._find_format(format_str)
        self.setCameraFormat(fmt)

    def getDevice(self) -> str:
        return self._device_to_string(self.cameraDevice())

    def getFormat(self) -> str:
        return self._format_to_string(self.cameraFormat())

    def _device_to_string(self, device: QCameraDevice) -> str:
        return bytes(device.id()).decode("utf-8") + ": " + device.description()

    def _format_to_string(self, fmt: QCameraFormat) -> str:
        return f"{fmt.resolution().width()}x{fmt.resolution().height()} @ {fmt.maxFrameRate():.2f} FPS"

    def _find_device(self, device_str: str) -> QCameraDevice:
        """
        Find a QCameraDevice by its string representation.
        Returns the first matching QCameraDevice.
        A match is found if device_str is *contained* (no exact match required) in the string "<id>: <description>".
        Raises ValueError if no matching device is found.
        """
        devices = QMediaDevices.videoInputs()
        for device in devices:
            if device_str in self._device_to_string(device):
                return device
        raise ValueError(f"No camera device matching '{device_str}' found")

    def _find_format(self, format_str: str) -> QCameraFormat:
        """
        Find a QCameraFormat by its string representation.
        Returns the first matching QCameraFormat.
        A match is found if format_str is *contained* (no exact match required) in the string "<resolution> @ <framerate>".
        Raises ValueError if no matching format is found.
        """
        formats = self.cameraDevice().videoFormats()
        for fmt in formats:
            if format_str in self._format_to_string(fmt):
                return fmt
        raise ValueError(f"No camera format matching '{format_str}' found")

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableDevices(self) -> list:
        devices = QMediaDevices.videoInputs()
        return [self._device_to_string(device) for device in devices]

    @PyQt6.QtCore.pyqtProperty(list, notify=availableFormatsChanged)
    def availableFormats(self) -> list[str]:
        formats = self.cameraDevice().videoFormats()
        return [self._format_to_string(fmt) for fmt in formats]


class Picamera2VideoCamera(QCamera):
    """QCamera subclass that delivers frames from a Raspberry Pi CSI camera via Picamera2.

    The Qt multimedia backend is never used — this class is a QObject carrier only.
    Frames are captured on a QTimer tick and pushed into a QVideoSink, which QML's
    VideoOutput can consume by binding its videoSink property.
    """

    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self, default_device: str | None = None, default_format: str | None = None):
        # No device passed — parent is a QObject carrier only, not a real camera session.
        super().__init__()

        self._output_sink = None  # set by QML via setVideoSink() once VideoOutput is ready
        self._picam = None
        self._current_device_str = None
        self._current_format_str = None

        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("picamera2 is not installed")

        # Select device
        camera_info = Picamera2.global_camera_info()
        if not camera_info:
            raise RuntimeError("No Picamera2 cameras found")

        if default_device is not None:
            selected = None
            for info in camera_info:
                candidate = f"{info['Num']}: {info['Model']}"
                if default_device in candidate:
                    selected = info
                    break
            if selected is None:
                logging.warning("Picamera2: no device matching '%s', using first camera", default_device)
                selected = camera_info[0]
        else:
            selected = camera_info[0]

        self._current_device_str = f"{selected['Num']}: {selected['Model']}"
        self._picam = Picamera2(selected["Num"])

        # QTimer drives frame capture in the Qt event loop — must exist before _apply_format()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture_frame)

        # Select format / sensor mode (sets timer interval)
        self._apply_format(default_format)

    def _apply_format(self, format_str: str | None):
        """Configure the Picamera2 instance for the given format string (or the last mode)."""
        modes = self._picam.sensor_modes
        if not modes:
            logging.warning("Picamera2: no sensor modes available")
            self._current_format_str = "unknown"
            return

        selected_mode = None
        if format_str is not None:
            for mode in modes:
                fps = mode.get("fps", 0)
                w = mode["size"][0]
                h = mode["size"][1]
                candidate = f"{w}x{h} @ {fps:.2f} FPS"
                if format_str in candidate:
                    selected_mode = mode
                    break
            if selected_mode is None:
                logging.warning("Picamera2: no mode matching '%s', using last mode", format_str)

        if selected_mode is None:
            selected_mode = modes[-1]

        fps = selected_mode.get("fps", 0)
        w = selected_mode["size"][0]
        h = selected_mode["size"][1]
        self._current_format_str = f"{w}x{h} @ {fps:.2f} FPS"

        config = self._picam.create_video_configuration(
            main={"size": (w, h), "format": "RGB888"},
        )
        self._picam.configure(config)

        if fps > 0:
            interval_ms = max(1, int(1000 / fps))
        else:
            interval_ms = 33  # ~30 FPS fallback
        self._timer.setInterval(interval_ms)

    def start(self):
        self._picam.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._picam.stop()

    def setFocusMode(self, mode):
        logging.warning("Picamera2VideoCamera: setFocusMode() is a no-op on CSI cameras")

    def setDevice(self, device_str: str):
        camera_info = Picamera2.global_camera_info()
        selected = None
        for info in camera_info:
            candidate = f"{info['Num']}: {info['Model']}"
            if device_str in candidate:
                selected = info
                break
        if selected is None:
            raise ValueError(f"No Picamera2 device matching '{device_str}'")

        was_running = self._timer.isActive()
        if was_running:
            self.stop()

        old_picam = self._picam
        self._picam = Picamera2(selected["Num"])
        old_picam.close()
        self._current_device_str = f"{selected['Num']}: {selected['Model']}"
        self._apply_format(None)

        if was_running:
            self.start()

        self.availableFormatsChanged.emit()

    def setFormat(self, format_str: str):
        was_running = self._timer.isActive()
        if was_running:
            self._timer.stop()
            self._picam.stop()

        self._apply_format(format_str)

        if was_running:
            self._picam.start()
            self._timer.start()

        self.availableFormatsChanged.emit()

    def getDevice(self) -> str:
        return self._current_device_str

    def getFormat(self) -> str:
        return self._current_format_str

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableDevices(self) -> list:
        return [f"{info['Num']}: {info['Model']}" for info in Picamera2.global_camera_info()]

    @PyQt6.QtCore.pyqtProperty(list, constant=False, notify=availableFormatsChanged)
    def availableFormats(self) -> list:
        modes = self._picam.sensor_modes
        result = []
        for mode in modes:
            fps = mode.get("fps", 0)
            w = mode["size"][0]
            h = mode["size"][1]
            result.append(f"{w}x{h} @ {fps:.2f} FPS")
        return result

    @PyQt6.QtCore.pyqtSlot(QVideoSink)
    def setVideoSink(self, sink: QVideoSink):
        """Called by QML (Component.onCompleted) to hand us the VideoOutput's internal sink."""
        self._output_sink = sink

    @PyQt6.QtCore.pyqtSlot()
    def _capture_frame(self):
        if self._output_sink is None:
            return
        try:
            array = self._picam.capture_array("main")
        except Exception as e:
            logging.warning("Picamera2: capture_array failed: %s", e)
            return

        h, w = array.shape[:2]
        image = QImage(array.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        frame = QVideoFrame(image)
        self._output_sink.setVideoFrame(frame)


class DummyVideoCamera(QCamera):
    "Dummy camera, used if camera is disabled to let UI know no camera is available."

    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()
    backendChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

    def setDevice(self, device_str: str):
        pass

    def setFormat(self, format_str: str):
        pass

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableDevices(self) -> list[str]:
        return ["No camera available"]

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableFormats(self) -> list[str]:
        return ["No format available"]

    @PyQt6.QtCore.pyqtProperty(bool, notify=backendChanged)
    def isQtBackend(self) -> bool:
        return False

    @PyQt6.QtCore.pyqtProperty(bool, notify=backendChanged)
    def isPicamera2Backend(self) -> bool:
        return False

    @PyQt6.QtCore.pyqtProperty(QCamera, notify=backendChanged)
    def activeQCamera(self):
        return None


class CombinedVideoCamera(PyQt6.QtCore.QObject):
    """Unified camera that wraps both Qt/V4L2 and Picamera2 backends.

    Exposes a single availableDevices list across all connected cameras.
    setDevice() transparently switches backends when necessary, and emits
    backendChanged so that QML can rewire CaptureSession and VideoSink.
    """

    backendChanged = PyQt6.QtCore.pyqtSignal()
    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

    def __init__(self, initial_backend: str = "auto", initial_device: str | None = None, initial_format: str | None = None):
        super().__init__()

        self._qt_cam: VideoCamera | None = None
        self._pi_cam: Picamera2VideoCamera | None = None
        self._active: VideoCamera | Picamera2VideoCamera | None = None
        self._output_sink = None
        self._is_running = False

        # Build unified device string lists at startup (immutable after __init__).
        # CSI cameras that appear in both Qt's V4L2 list and Picamera2's list are
        # excluded from the Qt list to avoid duplicates in availableDevices.
        pi_models = _pi_model_names()
        self._qt_device_strings: list[str] = [
            bytes(d.id()).decode("utf-8") + ": " + d.description()
            for d in QMediaDevices.videoInputs()
            if not _qt_device_is_pi_managed(d, pi_models)
        ]
        self._pi_device_strings: list[str] = []
        if PICAMERA2_AVAILABLE:
            self._pi_device_strings = [
                f"{info['Num']}: {info['Model']}"
                for info in Picamera2.global_camera_info()
            ]
        self._all_device_strings = self._qt_device_strings + self._pi_device_strings

        # Activate initial device/backend
        if initial_device and initial_device in self._qt_device_strings:
            self._activate_qt(initial_device, initial_format)
        elif initial_device and initial_device in self._pi_device_strings:
            self._activate_pi(initial_device, initial_format)
        else:
            # No matching device in config — pick by backend preference
            if initial_backend == "auto":
                backend = _detect_backend()
            else:
                backend = initial_backend
            if backend == "picamera2" and self._pi_device_strings:
                self._activate_pi(self._pi_device_strings[0], initial_format)
            elif self._qt_device_strings:
                self._activate_qt(self._qt_device_strings[0], initial_format)
            elif self._pi_device_strings:
                self._activate_pi(self._pi_device_strings[0], initial_format)
            # else: no cameras at all — _active stays None

    # ------------------------------------------------------------------
    # Internal backend activation helpers
    # ------------------------------------------------------------------

    def _activate_qt(self, device_str: str, fmt: str | None):
        """Switch active backend to Qt/V4L2, creating camera if needed."""
        was_pi_active = (self._active is self._pi_cam and self._pi_cam is not None)

        if was_pi_active and self._is_running:
            self._pi_cam.stop()

        if self._qt_cam is None:
            self._qt_cam = VideoCamera(device_str, fmt)
            self._qt_cam.availableFormatsChanged.connect(self.availableFormatsChanged)
        else:
            self._qt_cam.setDevice(device_str)
            if fmt:
                self._qt_cam.setFormat(fmt)

        prev_active = self._active
        self._active = self._qt_cam

        if prev_active is not self._active:
            self.backendChanged.emit()

        if self._is_running:
            self._qt_cam.start()

    def _activate_pi(self, device_str: str, fmt: str | None):
        """Switch active backend to Picamera2, creating camera if needed."""
        was_qt_active = (self._active is self._qt_cam and self._qt_cam is not None)

        if was_qt_active and self._is_running:
            self._qt_cam.stop()

        if self._pi_cam is None:
            self._pi_cam = Picamera2VideoCamera(device_str, fmt)
            self._pi_cam.availableFormatsChanged.connect(self.availableFormatsChanged)
        else:
            self._pi_cam.setDevice(device_str)
            if fmt:
                self._pi_cam.setFormat(fmt)

        prev_active = self._active
        self._active = self._pi_cam

        if prev_active is not self._active:
            # Pass any already-stored sink to the Pi cam (handles switching back to Pi
            # after having been on Qt — QML's Connections.onBackendChanged will also
            # call setVideoSink() synchronously during backendChanged.emit() below,
            # but setting it here first is a safe fallback)
            if self._output_sink is not None:
                self._pi_cam.setVideoSink(self._output_sink)
            self.backendChanged.emit()

        if self._is_running:
            self._pi_cam.start()

    # ------------------------------------------------------------------
    # Public API (mirrors VideoCamera / Picamera2VideoCamera interface)
    # ------------------------------------------------------------------

    def start(self):
        self._is_running = True
        if self._active is not None:
            self._active.start()

    def stop(self):
        if self._active is not None:
            self._active.stop()
        self._is_running = False

    def setDevice(self, device_str: str):
        if device_str in self._qt_device_strings:
            if self._active is self._qt_cam:
                # Same backend — delegate; VideoCamera.setDevice handles stop/start
                self._qt_cam.setDevice(device_str)
            else:
                self._activate_qt(device_str, None)
        elif device_str in self._pi_device_strings:
            if self._active is self._pi_cam:
                self._pi_cam.setDevice(device_str)
            else:
                self._activate_pi(device_str, None)
        else:
            raise ValueError(f"No camera device matching '{device_str}'")

    def setFormat(self, format_str: str):
        if self._active is not None:
            self._active.setFormat(format_str)

    def setFocusMode(self, mode):
        if self._active is not None:
            self._active.setFocusMode(mode)

    def getDevice(self) -> str:
        return self._active.getDevice() if self._active is not None else ""

    def getFormat(self) -> str:
        return self._active.getFormat() if self._active is not None else ""

    @PyQt6.QtCore.pyqtSlot(QVideoSink)
    def setVideoSink(self, sink: QVideoSink):
        """Called by QML to hand the VideoOutput's internal sink to the Pi backend."""
        self._output_sink = sink
        if self._active is self._pi_cam and self._pi_cam is not None:
            self._pi_cam.setVideoSink(sink)

    # ------------------------------------------------------------------
    # QML-facing properties
    # ------------------------------------------------------------------

    @PyQt6.QtCore.pyqtProperty(list, constant=True)
    def availableDevices(self) -> list:
        return self._all_device_strings

    @PyQt6.QtCore.pyqtProperty(list, notify=availableFormatsChanged)
    def availableFormats(self) -> list:
        if self._active is None:
            return []
        return list(self._active.availableFormats)

    @PyQt6.QtCore.pyqtProperty(bool, notify=backendChanged)
    def isQtBackend(self) -> bool:
        return isinstance(self._active, VideoCamera)

    @PyQt6.QtCore.pyqtProperty(bool, notify=backendChanged)
    def isPicamera2Backend(self) -> bool:
        return isinstance(self._active, Picamera2VideoCamera)

    @PyQt6.QtCore.pyqtProperty(QCamera, notify=backendChanged)
    def activeQCamera(self):
        """Return the active VideoCamera (a QCamera subclass) when Qt backend is active.

        Returns None when Picamera2 is active — QML sees this as null, which sets
        CaptureSession.camera = null and stops the Qt multimedia pipeline.
        """
        return self._qt_cam if isinstance(self._active, VideoCamera) else None


def make_video_camera(backend: str, device: str | None, fmt: str | None) -> QCamera:
    """Factory for VideoCamera / Picamera2VideoCamera.

    backend: "qt" | "picamera2" | "auto"
      - "auto" calls _detect_backend() to pick based on hardware.
    Raises RuntimeError if the requested backend is unavailable.
    """
    if backend == "auto":
        backend = _detect_backend()

    if backend == "picamera2":
        if not PICAMERA2_AVAILABLE:
            logging.warning("picamera2 not available, falling back to Qt backend")
            backend = "qt"
        else:
            return Picamera2VideoCamera(device, fmt)

    return VideoCamera(device, fmt)
