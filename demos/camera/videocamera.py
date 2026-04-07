import logging
import PyQt6.QtCore
from PyQt6.QtMultimedia import QMediaDevices, QCameraDevice, QCameraFormat, QCamera

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
