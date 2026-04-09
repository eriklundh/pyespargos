"""demos_menu — core logic for the ESPARGOS demos launcher menu.

DemoScanner: pure Python (no Qt), scans demos/ for demo-menuitem.yaml files.
CommonSettings: QObject, persists IP and array-mode settings.
"""
import logging
import pathlib
import yaml

log = logging.getLogger(__name__)

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
