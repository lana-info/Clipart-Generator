"""Both native Mac builds must retain the current downloadable-module boundary."""
from pathlib import Path
import re

import pytest

from scripts.build_macos import FORWARDED_OPTIONS, MACOS_RUNTIME, pyinstaller_arguments
from studio_shell_packaging import EXCLUDED_IMPLEMENTATIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("architecture", ["arm64", "x86_64"])
def test_mac_core_inventory_matches_reviewed_windows_core(architecture):
    arguments = pyinstaller_arguments(ROOT, architecture)
    windows = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    for kind in FORWARDED_OPTIONS - {"add-data"}:
        expected = re.findall(rf'--{kind} "([^"]+)"', windows)
        actual = [arguments[index + 1] for index, item in enumerate(arguments) if item == "--" + kind]
        assert actual == expected
    exclusions = {arguments[index + 1] for index, item in enumerate(arguments) if item == "--exclude-module"}
    assert set(EXCLUDED_IMPLEMENTATIONS) <= exclusions
    data = [arguments[index + 1] for index, item in enumerate(arguments) if item == "--add-data"]
    assert MACOS_RUNTIME + ":" + MACOS_RUNTIME in data
    assert "assets/studio-prompt-composer-cover.png:assets" in data
    assert "release/VERSION.txt:release" in data
    assert all("windows" not in path and ";" not in path for path in data)
    assert arguments[arguments.index("--target-arch") + 1] == architecture


def test_mac_cross_compilation_and_invalid_architecture_are_rejected():
    with pytest.raises(ValueError):
        pyinstaller_arguments(ROOT, "universal2")


def test_mac_workflow_has_explicit_native_targets_and_required_artifacts():
    workflow = (ROOT / ".github/workflows/release-multi-platform.yml").read_text()
    mac = workflow.split("  build-macos:\n", 1)[1]
    assert "inputs.build_macos" in mac
    assert "runner: macos-15-intel" in mac and "runner: macos-15" in mac
    assert "target_arch: x86_64" in mac and "target_arch: arm64" in mac
    assert "--release-entrypoint-smoke" in mac
    assert "test_prompt_composer_runtime.py" in mac
    assert "build-provenance.json" in mac
    assert "if-no-files-found: error" in mac
    assert "continue-on-error: true" not in mac
    assert 'lipo "$executable" -verify_arch ${{ matrix.target_arch }}' in mac
    assert 'lipo realesrgan-ncnn-vulkan-20220424-macos/realesrgan-ncnn-vulkan -verify_arch ${{ matrix.target_arch }}' in mac
    assert "lipo -verify_arch" not in mac
    assert "if: ${{ inputs.build_windows }}" in workflow
