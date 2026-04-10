"""Unit tests for DemoScanner — pure Python, no Qt required."""
import pathlib
import shlex
import pytest
import yaml

from demos_menu import DemoScanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demos_root(tmp_path):
    """Create a minimal fake demos/ tree for isolated testing."""
    # common/ — excluded by scanner, no yaml expected
    (tmp_path / "common").mkdir()

    # A normal single-array demo
    d1 = tmp_path / "speedtest"
    d1.mkdir()
    (d1 / "demo-menuitem.yaml").write_text(
        "name: Speedtest\n"
        "description: Measure throughput\n"
        "command: python speedtest.py {single_array}\n"
    )

    # A combined-array-only demo
    d2 = tmp_path / "camera"
    d2.mkdir()
    (d2 / "demo-menuitem.yaml").write_text(
        "name: Camera Overlay\n"
        "description: Camera beamspace overlay\n"
        "command: python camera.py {single_array}\n"
        "combined_array_only: true\n"
    )

    # Hidden entry (demos-menu itself)
    d3 = tmp_path / "demos-menu"
    d3.mkdir()
    (d3 / "demo-menuitem.yaml").write_text(
        "hidden: true\n"
        "name: Demos Menu\n"
        "description: The launcher itself\n"
    )

    # A folder with no yaml — should trigger a warning
    (tmp_path / "no-yaml-demo").mkdir()

    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_finds_visible_demos(demos_root):
    scanner = DemoScanner(demos_root)
    names = [item["name"] for item in scanner.items]
    assert "Speedtest" in names
    assert "Camera Overlay" in names


def test_hidden_entry_excluded(demos_root):
    scanner = DemoScanner(demos_root)
    names = [item["name"] for item in scanner.items]
    assert "Demos Menu" not in names


def test_common_folder_excluded(demos_root):
    scanner = DemoScanner(demos_root)
    dirs = [item["demo_dir"].name for item in scanner.items]
    assert "common" not in dirs


def test_missing_yaml_emits_warning(demos_root, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        DemoScanner(demos_root)
    assert any("no-yaml-demo" in msg for msg in caplog.messages)


def test_item_fields_populated(demos_root):
    scanner = DemoScanner(demos_root)
    item = next(i for i in scanner.items if i["name"] == "Speedtest")
    assert item["description"] == "Measure throughput"
    assert item["command"] == "python speedtest.py {single_array}"
    assert item["combined_array_only"] is False
    assert item["single_array_only"] is False
    assert item["disabled"] is False
    assert isinstance(item["demo_dir"], pathlib.Path)
    assert item["demo_dir"].name == "speedtest"


def test_combined_array_only_flag_parsed(demos_root):
    scanner = DemoScanner(demos_root)
    item = next(i for i in scanner.items if i["name"] == "Camera Overlay")
    assert item["combined_array_only"] is True


def test_item_count(demos_root):
    scanner = DemoScanner(demos_root)
    # 2 visible demos (speedtest + camera), hidden and no-yaml excluded
    assert len(scanner.items) == 2


def test_real_demos_root_finds_all_demos():
    """Smoke test against the real demos/ tree — all 13 should be found."""
    real_root = pathlib.Path(__file__).parents[3]  # demos/demos-menu/tests/unit -> demos/
    scanner = DemoScanner(real_root)
    assert len(scanner.items) == 13


def test_real_demos_root_no_warnings(caplog):
    """No missing-yaml warnings against the real demos/ tree."""
    import logging
    real_root = pathlib.Path(__file__).parents[3]
    with caplog.at_level(logging.WARNING):
        DemoScanner(real_root)
    missing = [m for m in caplog.messages if "no demo-menuitem.yaml" in m]
    assert missing == [], f"Unexpected missing yamls: {missing}"


def test_all_demo_scripts_exist():
    """Every demo's command references a script that exists in its demo_dir."""
    real_root = pathlib.Path(__file__).parents[3]
    scanner = DemoScanner(real_root)
    for item in scanner.items:
        tokens = shlex.split(item["command"])
        # commands are "python <script>.py [args]"
        assert len(tokens) >= 2, f"Unexpected command format: {item['command']}"
        script = tokens[1]
        script_path = item["demo_dir"] / script
        assert script_path.exists(), (
            f"Script not found for demo '{item['name']}': {script_path}"
        )
