"""demos_menu — core logic for the ESPARGOS demos launcher menu.

DemoScanner: pure Python (no Qt), scans demos/ for demo-menuitem.yaml files.
CommonSettings: QObject, persists IP and array-mode settings.
"""
import json
import logging
import pathlib
import sys
import yaml

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot, QProcess
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl

log = logging.getLogger(__name__)

_DEFAULT_SETTINGS_PATH = pathlib.Path.home() / ".config" / "espargos-demos" / "settings.json"

# Folders under demos/ that are never runnable demos — skip without warning.
_SCAN_EXCLUDES = {"common"}


def build_command(command_template: str, ip: str, single_array: bool) -> list[str]:
    """Resolve placeholder tokens in a command template and split into a list.

    Tokens:
        {single_array} → "-s <ip>" when single_array is True and ip is non-empty;
                         empty string otherwise (token removed from arg list).
        {ip}           → the raw ip string.
    """
    single_array_value = f"-s {ip}" if (single_array and ip) else ""
    resolved = command_template.format_map({
        "single_array": single_array_value,
        "ip": ip,
    })
    # Split and discard empty tokens (from collapsed {single_array} placeholders)
    cmd = [part for part in resolved.split() if part]
    # Replace bare "python"/"python3" with the running interpreter so demos use
    # the same venv as the menu regardless of what is on PATH.
    if cmd and cmd[0] in ("python", "python3"):
        cmd[0] = sys.executable
    return cmd


class DemoScanner:
    """Scan a demos root directory for demo-menuitem.yaml files.

    Folders in _SCAN_EXCLUDES are silently skipped.
    Folders with hidden: true in their yaml are read but not included in items.
    Folders with no yaml emit a WARNING.

    Attributes:
        items: list of dicts with keys:
            name, description, command, demo_dir,
            combined_array_only, single_array_only, disabled.
    """

    def __init__(self, demos_root: pathlib.Path):
        self._demos_root = pathlib.Path(demos_root)
        self.items: list[dict] = []
        self._scan()

    def _scan(self):
        for folder in sorted(self._demos_root.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name in _SCAN_EXCLUDES:
                continue
            if folder.name.startswith(".") or folder.name.startswith("_"):
                continue

            yaml_path = folder / "demo-menuitem.yaml"
            if not yaml_path.exists():
                log.warning("%s has no demo-menuitem.yaml — skipping", folder.name)
                continue

            with yaml_path.open() as f:
                data = yaml.safe_load(f)

            if data.get("hidden", False):
                continue

            self.items.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "command": data.get("command", ""),
                "combined_array_only": bool(data.get("combined_array_only", False)),
                "single_array_only":   bool(data.get("single_array_only", False)),
                "disabled":            bool(data.get("disabled", False)),
                "demo_dir": folder,
            })


class CommonSettings(QObject):
    """Persisted common settings: ESPARGOS IP address and single-array mode.

    Saved to a JSON file on every change. Loaded on construction.
    Exposed as Qt properties so QML can bind to them directly.
    """

    ipChanged = pyqtSignal()
    singleArrayChanged = pyqtSignal()

    def __init__(self, settings_path: pathlib.Path = None, parent=None):
        super().__init__(parent)
        self._settings_path = pathlib.Path(settings_path) if settings_path else _DEFAULT_SETTINGS_PATH
        self._ip = ""
        self._single_array = True   # default: single-array mode (most users have one device)
        self._load()

    # ------------------------------------------------------------------
    # Qt properties
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=ipChanged)
    def ip(self) -> str:
        return self._ip

    @pyqtProperty(bool, notify=singleArrayChanged)
    def singleArray(self) -> bool:
        return self._single_array

    # ------------------------------------------------------------------
    # Slots (callable from QML)
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def setIp(self, value: str):
        if value == self._ip:
            return
        self._ip = value
        self._save()
        self.ipChanged.emit()

    @pyqtSlot(bool)
    def setSingleArray(self, value: bool):
        if value == self._single_array:
            return
        self._single_array = value
        self._save()
        self.singleArrayChanged.emit()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            data = json.loads(self._settings_path.read_text())
            self._ip = data.get("ip", "")
            self._single_array = bool(data.get("single_array", True))
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            pass  # use defaults

    def _save(self):
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps({"ip": self._ip, "single_array": self._single_array}, indent=2)
        )


class ScannerAdapter(QObject):
    """Qt/QML adapter around DemoScanner.

    Filters combined_array_only items out of demoItems when single-array mode
    is active. Converts Path objects to strings so demoItems is JSON-serialisable.

    The demoItems property is dynamic: it re-evaluates when singleArray changes.
    """

    demoItemsChanged = pyqtSignal()

    def __init__(self, scanner: DemoScanner, settings: CommonSettings, parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._settings = settings
        self._procs: list[QProcess] = []   # keep references so GC cannot kill child processes
        settings.singleArrayChanged.connect(self.demoItemsChanged)

    @pyqtProperty(list, notify=demoItemsChanged)
    def demoItems(self) -> list:
        result = []
        for item in self._scanner.items:
            if item["combined_array_only"] and self._settings.singleArray:
                continue   # hide combined-array-only demos in single-array mode
            d = dict(item)
            d["demo_dir"] = str(d["demo_dir"])
            result.append(d)
        return result

    @pyqtSlot(int, str, bool)
    def launchDemo(self, index: int, ip: str, single_array: bool):
        items = self.demoItems
        if index < 0 or index >= len(items):
            log.warning("launchDemo: index %d out of range (have %d items)", index, len(items))
            return
        item = items[index]
        cmd = build_command(item["command"], ip=ip, single_array=single_array)
        if not cmd:
            log.warning("launchDemo: empty command for '%s'", item["name"])
            return
        proc = QProcess(self)   # parent=self keeps it alive even if _procs is cleared
        proc.setWorkingDirectory(item["demo_dir"])

        name = item["name"]
        proc.readyReadStandardOutput.connect(
            lambda: log.info("[%s] %s", name,
                             proc.readAllStandardOutput().data().decode(errors="replace").rstrip()))
        proc.readyReadStandardError.connect(
            lambda: log.warning("[%s] %s", name,
                                proc.readAllStandardError().data().decode(errors="replace").rstrip()))
        proc.finished.connect(
            lambda code, _status: log.info("'%s' exited (code=%d)", name, code))
        proc.finished.connect(
            lambda: self._procs.remove(proc) if proc in self._procs else None)

        self._procs.append(proc)
        proc.start(cmd[0], cmd[1:])
        log.info("Launched '%s': %s (cwd=%s)", name, cmd, item["demo_dir"])


def run(demos_root: pathlib.Path, settings_path: pathlib.Path = None,
        ip: str = None, single_array: bool = None, fullscreen: bool = False):
    """Entry point: create QApplication, load QML, exec event loop.

    ip and single_array, when not None, override the persisted settings and
    re-persist them — equivalent to the user typing them in the settings panel.
    fullscreen, when True, starts the window in fullscreen mode.
    """
    import sys
    app = QApplication.instance() or QApplication(sys.argv)

    engine = QQmlApplicationEngine()

    settings = CommonSettings(settings_path=settings_path)

    # CLI overrides take precedence over persisted settings (and re-persist).
    if ip is not None:
        settings.setIp(ip)
    if single_array is not None:
        settings.setSingleArray(single_array)

    scanner = DemoScanner(demos_root)
    adapter = ScannerAdapter(scanner, settings)

    engine.rootContext().setContextProperty("settings", settings)
    engine.rootContext().setContextProperty("scanner", adapter)
    engine.rootContext().setContextProperty("backend_fullscreen", bool(fullscreen))

    qml_file = pathlib.Path(__file__).parent / "demos-menu.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        log.error("Failed to load QML — check demos-menu.qml for errors")
        return 1

    return app.exec()
