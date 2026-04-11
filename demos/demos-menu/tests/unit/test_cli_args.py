"""Unit tests for menu.py CLI argument parsing and run() setting overrides."""
import json
import pathlib
import sys
import pytest
from unittest.mock import MagicMock, patch

# Make menu.py importable so we can get its parser directly
sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))

DEMOS_ROOT = pathlib.Path(__file__).parents[3]


def _parser():
    """Import and return the argument parser from menu.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "menu", pathlib.Path(__file__).parents[3] / "menu.py"
    )
    mod = importlib.util.load_from_spec = None  # don't execute module-level code
    menu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(menu)
    return menu._make_parser()


# ---------------------------------------------------------------------------
# Argparse behaviour
# ---------------------------------------------------------------------------

class TestMenuArgparse:
    @pytest.fixture(autouse=True)
    def parser(self):
        self._parser = _parser()

    def _parse(self, argv):
        args, _ = self._parser.parse_known_args(argv)
        return args

    def test_no_args_gives_none_for_both(self):
        args = self._parse([])
        assert args.ip is None
        assert args.single_array is None

    def test_positional_ip(self):
        args = self._parse(["192.168.1.2"])
        assert args.ip == "192.168.1.2"
        assert args.single_array is None

    def test_short_flag_sets_single_array(self):
        args = self._parse(["-s"])
        assert args.single_array is True
        assert args.ip is None

    def test_long_flag_sets_single_array(self):
        args = self._parse(["--single-array"])
        assert args.single_array is True

    def test_short_flag_with_ip(self):
        args = self._parse(["-s", "192.168.1.2"])
        assert args.ip == "192.168.1.2"
        assert args.single_array is True

    def test_ip_before_flag(self):
        args = self._parse(["192.168.1.2", "-s"])
        assert args.ip == "192.168.1.2"
        assert args.single_array is True

    def test_qt_platform_arg_passes_through(self):
        # Qt args like --platform should not cause argparse to error
        args, remaining = self._parser.parse_known_args(
            ["192.168.1.2", "--platform", "offscreen"]
        )
        assert args.ip == "192.168.1.2"
        assert "--platform" in remaining


# ---------------------------------------------------------------------------
# run() setting overrides
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    """Patch QQmlApplicationEngine so no QML files are actually loaded."""
    with patch("demos_menu.QQmlApplicationEngine") as MockEngine:
        inst = MagicMock()
        inst.rootObjects.return_value = [MagicMock()]  # non-empty = success
        inst.rootContext.return_value = MagicMock()
        MockEngine.return_value = inst
        yield inst


def _run(qapp, tmp_path, mock_engine, **run_kwargs):
    """Call run() with QML mocked out, returning the settings file path."""
    settings_path = tmp_path / "settings.json"
    from demos_menu import run
    with patch.object(qapp, "exec", return_value=0):
        run(DEMOS_ROOT, settings_path=settings_path, **run_kwargs)
    return settings_path


class TestRunOverrides:
    def test_ip_arg_overrides_saved_ip(self, qapp, tmp_path, mock_engine):
        path = tmp_path / "s.json"
        path.write_text('{"ip": "10.0.0.1", "single_array": false}')
        from demos_menu import run
        with patch.object(qapp, "exec", return_value=0):
            run(DEMOS_ROOT, settings_path=path, ip="192.168.1.2")
        assert json.loads(path.read_text())["ip"] == "192.168.1.2"

    def test_single_array_arg_overrides_saved_flag(self, qapp, tmp_path, mock_engine):
        path = tmp_path / "s.json"
        path.write_text('{"ip": "10.0.0.1", "single_array": false}')
        from demos_menu import run
        with patch.object(qapp, "exec", return_value=0):
            run(DEMOS_ROOT, settings_path=path, single_array=True)
        assert json.loads(path.read_text())["single_array"] is True

    def test_no_override_leaves_saved_ip(self, qapp, tmp_path, mock_engine):
        path = tmp_path / "s.json"
        path.write_text('{"ip": "10.0.0.1", "single_array": true}')
        from demos_menu import run
        with patch.object(qapp, "exec", return_value=0):
            run(DEMOS_ROOT, settings_path=path)
        assert json.loads(path.read_text())["ip"] == "10.0.0.1"

    def test_both_args_override_both_settings(self, qapp, tmp_path, mock_engine):
        path = tmp_path / "s.json"
        path.write_text('{"ip": "10.0.0.1", "single_array": false}')
        from demos_menu import run
        with patch.object(qapp, "exec", return_value=0):
            run(DEMOS_ROOT, settings_path=path, ip="192.168.1.2", single_array=True)
        data = json.loads(path.read_text())
        assert data["ip"] == "192.168.1.2"
        assert data["single_array"] is True

    def test_ip_none_does_not_clear_saved_ip(self, qapp, tmp_path, mock_engine):
        """run(ip=None) must not overwrite the saved IP with an empty string."""
        path = tmp_path / "s.json"
        path.write_text('{"ip": "10.0.0.1", "single_array": true}')
        from demos_menu import run
        with patch.object(qapp, "exec", return_value=0):
            run(DEMOS_ROOT, settings_path=path, ip=None)
        assert json.loads(path.read_text())["ip"] == "10.0.0.1"
