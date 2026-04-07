import logging
import PyQt6.QtCore
from PyQt6.QtMultimedia import QMediaDevices, QCameraDevice, QCameraFormat, QCamera, QVideoSink, QVideoFrame, QVideoFrameFormat
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


def list_all_cameras() -> list:
    """Return a flat list of dicts describing all cameras from both backends.

    Each dict has keys: index, backend, name, id.
    """
    cameras = []
    idx = 0
    for device in QMediaDevices.videoInputs():
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
            fmt = availableFormats[-1]
            self.setCameraFormat(fmt)

    def setDevice(self, device_str: str):
        device = self._find_device(device_str)
        self.setCameraDevice(device)

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

    @PyQt6.QtCore.pyqtProperty(list, constant=False)
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

        self._sink = QVideoSink(parent=self)
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

        # Select format / sensor mode
        self._apply_format(default_format)

        # QTimer drives frame capture in the Qt event loop
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture_frame)

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

        self._picam = Picamera2(selected["Num"])
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

    @PyQt6.QtCore.pyqtProperty(QVideoSink, constant=True)
    def picamera2VideoSink(self) -> QVideoSink:
        return self._sink

    @PyQt6.QtCore.pyqtSlot()
    def _capture_frame(self):
        try:
            array = self._picam.capture_array("main")
        except Exception as e:
            logging.warning("Picamera2: capture_array failed: %s", e)
            return

        h, w = array.shape[:2]
        image = QImage(array.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        frame = QVideoFrame(image)
        self._sink.setVideoFrame(frame)


class DummyVideoCamera(QCamera):
    "Dummy camera, used if camera is disabled to let UI know no camera is available."

    availableFormatsChanged = PyQt6.QtCore.pyqtSignal()

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
