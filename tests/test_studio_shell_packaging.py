"""The shell build must omit downloaded code and retain its Core imports."""

import ast
import importlib.util
from pathlib import Path
import re
import sys

from studio_module_packaging import OFFICIAL_WORKFLOW_FILES
from studio_shell_packaging import EXCLUDED_IMPLEMENTATIONS, frozen_shell_has_no_workflow_sources


ROOT = Path(__file__).resolve().parents[1]


def _build_options(kind):
    build = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    return set(re.findall(rf'--{kind} "([^"]+)"', build))


def test_build_omits_workflow_implementations_and_keeps_catalog_artwork():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    assert set(EXCLUDED_IMPLEMENTATIONS) <= _build_options("exclude-module")
    assert '--add-data "studio_builtin_workflows;studio_builtin_workflows"' not in build
    assert '--collect-submodules "studio_builtin_workflows"' not in build
    assert '--add-data "assets/studio-prompt-composer-cover.png;assets"' in build
    assert "studio_prompt_composer_host" in _build_options("hidden-import")


def test_build_retains_shared_imports_used_by_signed_workflows():
    owned = {Path(file).stem for files in OFFICIAL_WORKFLOW_FILES.values() for file in files}
    local_imports = set()
    for file in sorted({file for files in OFFICIAL_WORKFLOW_FILES.values() for file in files}):
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                local_imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                local_imports.update(alias.name.split(".")[0] for alias in node.names)
    shared = {name for name in local_imports - owned - {"main"}
              if (ROOT / f"{name}.py").is_file() or (ROOT / name).is_dir()}
    assert shared <= _build_options("hidden-import")


def test_frozen_smoke_rejects_copied_or_compiled_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    assert frozen_shell_has_no_workflow_sources()
    (tmp_path / "prompt_composer").mkdir()
    assert not frozen_shell_has_no_workflow_sources()
    (tmp_path / "prompt_composer").rmdir()
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "v3_clipart_flow" else None)
    assert not frozen_shell_has_no_workflow_sources()
