"""demos_menu — core logic for the ESPARGOS demos launcher menu.

DemoScanner: pure Python (no Qt), scans demos/ for demo-menuitem.yaml files.
CommonSettings: QObject, persists IP and array-mode settings.
"""
import json
import logging
import pathlib
import yaml

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)

_DEFAULT_SETTINGS_PATH = pathlib.Path.home() / ".config" / "espargos-demos" / "settings.json"

# Folders under demos/ that are never runnable demos — skip without warning.
_SCAN_EXCLUDES = {"common"}


class DemoScanner:
    """Scan a demos root directory for demo-menuitem.yaml files.

    Folders in _SCAN_EXCLUDES are silently skipped.
    Folders with hidden: true in their yaml are read but not included in items.
    Folders with no yaml emit a WARNING.

    Attributes:
        items: list of dicts with keys name, description, command, requires, demo_dir.
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
                "requires": data.get("requires", []),
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
        self._single_array = False
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
            self._single_array = bool(data.get("single_array", False))
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            pass  # use defaults

    def _save(self):
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps({"ip": self._ip, "single_array": self._single_array}, indent=2)
        )
