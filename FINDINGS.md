# Codebase Findings

## `VideoCamera` class (`demos/camera/videocamera.py`)

Inherits `QCamera`. Has:

- **Signal**: `availableFormatsChanged` — emitted by `setDevice()` so the UI can refresh its format list.
- **Qt properties**: `availableDevices` (constant list), `availableFormats` (non-constant list, backed by `cameraDevice().videoFormats()`).
- **Custom methods**: `setDevice(str)`, `setFormat(str)`, `getDevice() → str`, `getFormat() → str`.
- **Internal helpers**: `_device_to_string()`, `_format_to_string()`, `_find_device()`, `_find_format()` — all use substring matching, not exact match.
- **`DummyVideoCamera`**: same interface, all no-ops, returns `["No camera available"]` from properties. Used when `--no-camera` is passed.

There is **no `frame_ready` signal** today.

---

## How `camera.py` consumes `VideoCamera`

1. **Construction** (`camera.py:117`): `VideoCamera(device, format)` where both args come from `appconfig.get("camera", ...)` — can be `None` on first run.
2. **Read-back** (`camera.py:122`): calls `getDevice()`/`getFormat()` to push the actually-selected values back into `appconfig`.
3. **QML wiring** (`camera.py:151`): passes `self.videocamera` as `"WebCam"` context property to QML.
4. **`exec()`** (`camera.py:158`): calls `videocamera.setFocusMode(Manual)` and `videocamera.start()` — both native `QCamera` methods.
5. **`onAboutToQuit()`** (`camera.py:550`): calls `videocamera.stop()`.
6. **Config updates** (`camera.py:566`): calls `setDevice()` / `setFormat()` whenever the appconfig's camera section changes (e.g. user picks a new device in the settings drawer).

---

## How QML uses `WebCam` (`CameraOverlay.qml`)

```qml
CaptureSession {
    id: captureSession
    camera: backend.cameraEnabled ? WebCam : null
    videoOutput: videoOutput
}
VideoOutput { id: videoOutput; anchors.fill: parent }
```

The `VideoOutput` feeds a `ShaderEffect` as a `ShaderEffectSource` — that is the composited camera + beamspace overlay. The settings drawer also reads `WebCam.availableDevices` and `WebCam.availableFormats` directly.

Frame delivery pipeline: **`QCamera` → `CaptureSession` → `VideoOutput` → `ShaderEffect`** — entirely inside Qt Multimedia. Picamera2 frames do not flow through this path.

---

## Common argparse/config framework (`demos/common/`)

- `ESPARGOSApplication` adds `-c/--config` (YAML file) and `-o KEY=VALUE` overrides. Mixins add their own args via `_add_argparse_arguments()` / `_process_args()` hooks.
- `DEFAULT_CONFIG` on the subclass lands in `appconfig` (a `ConfigManager`). The `ConfigManager` is bidirectional: UI → app via `updateAppState(dict)`, app → UI via `updateUIState(json)`.
- `appconfig.get("camera", "device")` etc. is how `camera.py` reads its config throughout.
- Camera-specific config lives under the `"camera"` key: `enable`, `flip`, `format`, `device`, `fov_azimuth`, `fov_elevation`.

---

## Implementation plan (approved)

### `videocamera.py`

**New imports (guarded):**
```python
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
```
Plus `QVideoSink`, `QVideoFrame`, `QVideoFrameFormat`, `QTimer`, `QImage` from PyQt6.

**New `_detect_backend()`** — returns `"picamera2"` if both `/proc/device-tree/model` contains "Raspberry Pi" AND `PICAMERA2_AVAILABLE` is True; otherwise returns `"qt"`.

**New `Picamera2VideoCamera(QCamera)` class:**
- `availableFormatsChanged = pyqtSignal()` — same signal name as `VideoCamera`.
- `__init__(default_device=None, default_format=None)`: calls `super().__init__()` (bare `QCamera`, no device — Qt multimedia backend never used), creates `self._sink = QVideoSink(parent=self)`, selects device from `Picamera2.global_camera_info()`, constructs a `Picamera2` instance, configures its format, sets up `self._timer = QTimer(self)` connected to `_capture_frame()`.
- `start()`: configures + starts the `Picamera2` instance, starts the QTimer.
- `stop()`: stops the QTimer, stops the `Picamera2` instance.
- `setFocusMode(mode)`: `logging.warning(...)`, no-op — does **not** call `super().setFocusMode()`.
- `setDevice(device_str)` / `setFormat(format_str)`: substring match against Picamera2 device/mode lists (same pattern as `_find_device()`), reconfigure `self._picam`, emit `availableFormatsChanged`.
- `getDevice()` / `getFormat()`: return current device/format strings.
- `availableDevices` — `@pyqtProperty(list, constant=True)`: from `Picamera2.global_camera_info()`, formatted as `"{Num}: {Model}"`.
- `availableFormats` — `@pyqtProperty(list, constant=False)`: from `self._picam.sensor_modes`, formatted as `"{width}x{height} @ {fps:.2f} FPS"`.
- `picamera2VideoSink` — `@pyqtProperty(QVideoSink, constant=True)`: returns `self._sink`.
- `_capture_frame()` slot: `self._picam.capture_array()` → `QImage(Format_RGB888)` → `QVideoFrame` → `self._sink.setVideoFrame(frame)`.

**New `list_all_cameras()`** — returns a flat list of dicts with `index`, `backend`, `name`, `id` fields, enumerating both Qt (`QMediaDevices.videoInputs()`) and Picamera2 (`Picamera2.global_camera_info()`) cameras.

**New `make_video_camera(backend, device, fmt)`** — `"auto"` calls `_detect_backend()` first; dispatches to `VideoCamera(device, fmt)` or `Picamera2VideoCamera(device, fmt)`.

`VideoCamera`, `DummyVideoCamera`, and all existing code are untouched.

---

### `camera.py`

**Argparse** (in the local `parser` block, before `super().__init__()`):
- `--camera-backend` with `choices=["qt", "picamera2", "auto"]`, default `"auto"`.
- `--list-cameras` as `store_true`.

**After `super().__init__()`**, before `initialize_pool()`:
- If `self.args.list_cameras`: call `videocamera.list_all_cameras()`, print each entry, `sys.exit(0)`. Works because `QApplication.__init__()` has already run inside `super().__init__()`, so `QMediaDevices` is available.

**`DEFAULT_CONFIG`** — add `"backend": "auto"` to the existing `"camera"` section.

**Camera construction** (~line 117) — replace direct `VideoCamera(...)` with:
```python
self.videocamera = videocamera.make_video_camera(
    self.args.camera_backend,
    self.appconfig.get("camera", "device"),
    self.appconfig.get("camera", "format"),
)
```

**Two new Qt properties** (constant — backend is fixed at startup):
```python
@pyqtProperty(bool, constant=True)
def isQtCamera(self):
    return isinstance(self.videocamera, videocamera.VideoCamera)

@pyqtProperty(bool, constant=True)
def isPicamera2(self):
    return isinstance(self.videocamera, videocamera.Picamera2VideoCamera)
```
When `--no-camera` is active, `self.videocamera` is a `DummyVideoCamera` so both return `False` — correct, since `cameraEnabled` is already `False`.

**`exec()`**: the `setFocusMode(Manual)` call stays as-is — `Picamera2VideoCamera` overrides it as a no-op, so no conditional needed.

No other changes to `camera.py`.

---

### `CameraOverlay.qml`

Only the `CaptureSession` + `VideoOutput` block (lines 9–18). Replace:

```qml
CaptureSession {
    id: captureSession
    camera: backend.cameraEnabled ? WebCam : null
    videoOutput: videoOutput
}
VideoOutput {
    id: videoOutput
    anchors.fill: parent
}
```

with:

```qml
CaptureSession {
    id: captureSession
    camera: backend.isQtCamera && backend.cameraEnabled ? WebCam : null
    videoOutput: backend.isQtCamera ? videoOutput : null
}
VideoOutput {
    id: videoOutput
    anchors.fill: parent
    videoSink: backend.isPicamera2 ? WebCam.picamera2VideoSink : null
}
```

- **Qt path**: `CaptureSession` owns `videoOutput`; `VideoOutput.videoSink` stays `null` — existing path unchanged.
- **Picamera2 path**: `CaptureSession.videoOutput` is `null` (no conflict); `VideoOutput.videoSink` is set to the Python-side `QVideoSink`; frames pushed from the QTimer flow into `videoOutput` exactly as before from the ShaderEffect's perspective.
- **No-camera path**: `cameraEnabled` is `False` and `isQtCamera`/`isPicamera2` are both `False`; `CaptureSession.camera` and `VideoOutput.videoSink` are both `null`.

Everything from line 20 onward (ShaderEffect, Canvas elements, statistics, timers, Connections) is **not touched**.
